import unittest
from unittest.mock import patch

from magnet2torrent import FailedToFetchException

from backend.implementations.download_clients import Torrent as T


class FakeDownload:
    def __init__(self, link):
        self._download_link = link


def fetch(link, raises=None, result=None):
    class FakeM2T:
        def __init__(self, *a, **k):
            pass

        async def retrieve_torrent(self):
            if raises:
                raise raises
            return result

    with patch.object(T, 'Magnet2Torrent', FakeM2T):
        import asyncio
        return asyncio.run(T.TorrentDownload._fetch_torrent_name(FakeDownload(link)))


class FetchTorrentNameTests(unittest.TestCase):
    def test_a_library_crash_falls_back_to_the_name_in_the_magnet(self):
        self.assertEqual(
            fetch('magnet:?xt=urn:btih:abc&dn=Some+Comic+001', raises=KeyError(b'complete')),
            'Some Comic 001')

    def test_a_library_crash_without_a_name_is_a_broken_link(self):
        self.assertIsNone(fetch('magnet:?xt=urn:btih:abc', raises=KeyError(b'complete')))
        self.assertIsNone(fetch('magnet:?xt=urn:btih:abc&dn=', raises=ValueError('x')))

    def test_no_peers_found_stays_a_broken_link(self):
        self.assertIsNone(fetch('magnet:?xt=urn:btih:abc&dn=X', raises=FailedToFetchException('none')))


if __name__ == '__main__':
    unittest.main()
