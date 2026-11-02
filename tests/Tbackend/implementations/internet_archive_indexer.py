import unittest

from backend.implementations.indexer_clients.ddl.InternetArchive import (
    escape_query, files_to_results)

BASE = 'https://archive.org'


class EscapeQueryTests(unittest.TestCase):
    def test_special_characters_are_escaped(self):
        self.assertEqual(
            escape_query('Batman: Year One (2005) [HC]'),
            r'Batman\: Year One \(2005\) \[HC\]')

    def test_plain_title_and_spaces_untouched(self):
        self.assertEqual(escape_query('  Saga 01 '), 'Saga 01')

    def test_all_operators(self):
        for c in '+-&|!(){}[]^"~*?:\\/':
            self.assertEqual(escape_query(c), '\\' + c)


class FilesToResultsTests(unittest.TestCase):
    def test_comic_files_only(self):
        meta = {'files': [
            {'name': 'Good Comic 01.cbz', 'size': '100'},
            {'name': 'dir/Real 02.CBR'},
            {'name': 'readme.txt'}]}
        r = files_to_results(BASE, 'abc', meta, 3, 'Internet Archive')
        self.assertEqual([x['display_title'] for x in r], ['Good Comic 01', 'Real 02'])
        self.assertEqual(r[0]['link'], f'{BASE}/download/abc/Good%20Comic%2001.cbz')
        self.assertEqual((r[0]['size'], r[1]['size']), (100, -1))
        self.assertEqual((r[0]['indexer_id'], r[0]['seeders']), (3, None))

    def test_files_made_by_archive_org_itself_are_skipped(self):
        meta = {'files': [
            {'name': 'Detective 01_jp2.zip'}, {'name': 'Detective 01_text.zip'},
            {'name': 'Detective 01_hocr.zip'},
            {'name': 'Detective 01.cbz', 'format': 'Comic Book ZIP'},
            {'name': 'Pages.zip', 'format': 'Single Page Processed JP2 ZIP'}]}
        r = files_to_results(BASE, 'a', meta, 1, 'IA')
        self.assertEqual([x['display_title'] for x in r], ['Detective 01'])

    def test_odd_metadata(self):
        for meta in (None, [], 'x', {'files': 'x'}, {'files': [None, 'x', {'name': 5}]}):
            self.assertEqual(files_to_results(BASE, 'a', meta, 1, 'IA'), [])


if __name__ == '__main__':
    unittest.main()
