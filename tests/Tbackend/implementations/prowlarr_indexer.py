import unittest

from backend.implementations.indexer_clients.torrent.Prowlarr import \
    parse_results


def result(**kw):
    base = {'protocol': 'torrent', 'title': 'Batman 003 (2020)',
            'magnetUrl': 'magnet:?xt=urn:btih:abc', 'size': 1234,
            'seeders': 5, 'leechers': 2}
    base.update(kw)
    return base


class ParseResultsTests(unittest.TestCase):
    def test_a_good_result(self):
        r, = parse_results([result()], 7, 'Prowlarr')
        self.assertEqual(r['link'], 'magnet:?xt=urn:btih:abc')
        self.assertEqual((r['size'], r['seeders'], r['leechers']), (1234, 5, 2))
        self.assertEqual((r['indexer_id'], r['indexer_title']), (7, 'Prowlarr'))
        self.assertEqual(r['display_title'], 'Batman 003 (2020)')

    def test_only_torrents(self):
        self.assertEqual(parse_results([result(protocol='usenet')], 1, 'P'), [])

    def test_download_url_when_no_magnet(self):
        r, = parse_results(
            [result(magnetUrl=None, downloadUrl='http://prowlarr/dl/1')], 1, 'P')
        self.assertEqual(r['link'], 'http://prowlarr/dl/1')

    def test_missing_size_and_peers(self):
        r, = parse_results([result(size=None, seeders='x', leechers=None)], 1, 'P')
        self.assertEqual((r['size'], r['seeders'], r['leechers']), (-1, None, None))

    def test_an_error_object_instead_of_a_list(self):
        for body in ({'message': 'Unauthorized'}, 'oops', 5, None):
            self.assertEqual(parse_results(body, 1, 'P'), [])

    def test_odd_items_are_skipped_and_good_ones_kept(self):
        body = [None, 'text', 7, [],
                result(title=None), result(magnetUrl=5, downloadUrl=None),
                result(title='Good 001')]
        self.assertEqual(
            [r['display_title'] for r in parse_results(body, 1, 'P')],
            ['Good 001'])


class SearchCategoryTests(unittest.IsolatedAsyncioTestCase):
    async def _search(self, answer):
        from backend.implementations.indexer_clients.torrent.Prowlarr import \
            ProwlarrIndexer
        indexer = object.__new__(ProwlarrIndexer)
        indexer._id, indexer._title = 1, 'P'
        calls = []

        async def fake_request(params):
            calls.append(dict(params))
            return answer

        indexer._ProwlarrIndexer__request = fake_request
        found = await indexer.search({'query': 'Saga', 'page': 1,
                                      'total_available_variations': 1})
        return found, calls

    async def test_only_the_comics_category_is_searched_once(self):
        found, calls = await self._search([result(title='Saga 001')])
        self.assertEqual(len(found.results), 1)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]['categories'], 7030)

    async def test_nothing_found_does_not_trigger_a_slow_second_search(self):
        for answer in ([], None):
            found, calls = await self._search(answer)
            self.assertEqual(found.results, [])
            self.assertEqual(len(calls), 1)


if __name__ == '__main__':
    unittest.main()
