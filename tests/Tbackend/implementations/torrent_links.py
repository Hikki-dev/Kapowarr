import unittest
from unittest.mock import MagicMock, patch

from bencoding import bencode

from backend.implementations import torrent_links as tl


def torrent_bytes() -> bytes:
    return bencode({b'announce': b'http://t.example/a', b'info': {
        b'name': b'Some Comic 001', b'piece length': 16384,
        b'pieces': b'x' * 20, b'length': 1}})


def response(body=b'', content_type=None, ok=True, location=None,
             length=None):
    r = MagicMock()
    r.ok = ok
    headers = {}
    if content_type:
        headers['Content-Type'] = content_type
    if location:
        headers['Location'] = location
    if length is not None:
        headers['Content-Length'] = str(length)
    r.headers = headers
    r.iter_content = lambda size: iter(
        [body[i:i + size] for i in range(0, len(body), size)])
    return r


def resolve(resp):
    session = MagicMock()
    session.get.return_value = resp
    session.__enter__.return_value = session
    with patch.object(tl, 'Session', return_value=session):
        return tl.resolve_to_magnet('http://prowlarr.local/dl?id=1')


class TorrentFileToMagnetTests(unittest.TestCase):
    def test_valid(self):
        m = tl.torrent_file_to_magnet(torrent_bytes())
        self.assertTrue(m.startswith('magnet:?xt=urn:btih:'))
        self.assertTrue(m.endswith('&dn=Some%20Comic%20001'))

    def test_garbage(self):
        self.assertIsNone(tl.torrent_file_to_magnet(b'not bencoded'))
        self.assertIsNone(tl.torrent_file_to_magnet(b''))


class ResolveToMagnetTests(unittest.TestCase):
    def test_magnet_passes_through(self):
        self.assertEqual(tl.resolve_to_magnet('magnet:?xt=urn:btih:abc'),
                         'magnet:?xt=urn:btih:abc')

    def test_redirect_to_magnet(self):
        self.assertEqual(
            resolve(response(location='magnet:?xt=urn:btih:abc')),
            'magnet:?xt=urn:btih:abc')

    def test_torrent_file_with_any_real_world_label(self):
        for label in ('application/x-bittorrent',
                      'application/x-bittorrent; charset=binary',
                      'Application/X-BitTorrent', 'application/octet-stream'):
            m = resolve(response(torrent_bytes(), label))
            self.assertTrue(m and m.startswith('magnet:'), label)

    def test_not_a_torrent(self):
        self.assertIsNone(resolve(response(b'<html></html>', 'text/html')))
        self.assertIsNone(resolve(response(b'nope', 'application/octet-stream')))
        self.assertIsNone(resolve(response(torrent_bytes(), None)))
        self.assertIsNone(resolve(response(b'', 'application/x-bittorrent', ok=False)))

    def test_too_large_even_when_the_size_is_hidden(self):
        big = b'0' * (tl.MAX_TORRENT_FILE_SIZE + 1)
        self.assertIsNone(resolve(response(big, 'application/x-bittorrent')))
        self.assertIsNone(resolve(response(
            b'x', 'application/x-bittorrent',
            length=tl.MAX_TORRENT_FILE_SIZE + 1)))

    def test_connection_failure(self):
        from requests import ConnectionError as CE
        session = MagicMock()
        session.__enter__.return_value = session
        session.get.side_effect = CE('down')
        with patch.object(tl, 'Session', return_value=session):
            self.assertIsNone(tl.resolve_to_magnet('http://x/1'))


if __name__ == '__main__':
    unittest.main()
