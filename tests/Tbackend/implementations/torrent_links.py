import unittest
from unittest.mock import MagicMock, patch

from bencoding import bencode

from backend.implementations import torrent_links as tl


def torrent_bytes() -> bytes:
    return bencode({b'announce': b'http://t.example/a', b'info': {
        b'name': b'Some Comic 001', b'piece length': 16384,
        b'pieces': b'x' * 20, b'length': 1}})


def response(body=b'', content_type=None, ok=True, location=None,
             length=None, status=None):
    r = MagicMock()
    r.ok = ok
    r.status_code = status or (200 if ok else 404)
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


def resolve_chain(*responses):
    session = MagicMock()
    session.get.side_effect = list(responses)
    session.__enter__.return_value = session
    with patch.object(tl, 'Session', return_value=session):
        return tl.resolve_to_magnet('http://site.example/dl?id=1'), session


class RedirectTests(unittest.TestCase):
    def test_http_redirect_to_the_torrent_file(self):
        magnet, session = resolve_chain(
            response(status=302, location='https://other.example/f.torrent', ok=False),
            response(torrent_bytes(), 'application/x-bittorrent'))
        self.assertTrue(magnet.startswith('magnet:?xt='))
        self.assertEqual(session.get.call_args_list[1].args[0], 'https://other.example/f.torrent')

    def test_relative_redirect(self):
        magnet, session = resolve_chain(
            response(status=301, location='/real.torrent', ok=False),
            response(torrent_bytes(), 'application/octet-stream'))
        self.assertTrue(magnet)
        self.assertEqual(session.get.call_args_list[1].args[0], 'http://site.example/real.torrent')

    def test_redirect_chain_ending_in_a_magnet(self):
        magnet, _ = resolve_chain(
            response(status=302, location='http://b.example/x', ok=False),
            response(status=302, location='magnet:?xt=urn:btih:abc', ok=False))
        self.assertEqual(magnet, 'magnet:?xt=urn:btih:abc')

    def test_a_redirect_loop_gives_up(self):
        loop = [response(status=302, location='http://site.example/dl?id=1', ok=False)
                for _ in range(tl.MAX_REDIRECTS + 2)]
        magnet, session = resolve_chain(*loop)
        self.assertIsNone(magnet)
        self.assertLessEqual(session.get.call_count, tl.MAX_REDIRECTS + 1)

    def test_redirect_to_something_that_is_not_http(self):
        magnet, _ = resolve_chain(response(status=302, location='ftp://x/y', ok=False))
        self.assertIsNone(magnet)


class TorrentFileToMagnetTests(unittest.TestCase):
    def test_valid(self):
        from urllib.parse import parse_qs, urlparse
        m = tl.torrent_file_to_magnet(torrent_bytes())
        self.assertTrue(m.startswith('magnet:?xt='))
        q = parse_qs(urlparse(m).query)
        self.assertEqual(q['dn'], ['Some Comic 001'])
        self.assertEqual(len(q['xt'][0]), len('urn:btih:') + 40)
        self.assertIn('http://t.example/a', q['tr'])       # the torrent's own tracker
        self.assertGreater(len(q['tr']), 5)                # plus the usual list

    def test_announce_list_trackers_are_added_once(self):
        from urllib.parse import parse_qs, urlparse
        data = bencode({b'announce': b'http://t.example/a',
                        b'announce-list': [[b'http://t.example/a'], [b'udp://u.example:1/x', b'junk']],
                        b'info': {b'name': b'N', b'piece length': 16384, b'pieces': b'x' * 20, b'length': 1}})
        trackers = parse_qs(urlparse(tl.torrent_file_to_magnet(data)).query)['tr']
        self.assertEqual(trackers.count('http://t.example/a'), 1)
        self.assertIn('udp://u.example:1/x', trackers)
        self.assertNotIn('junk', trackers)

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
