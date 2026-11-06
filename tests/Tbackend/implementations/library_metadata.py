import os
import tempfile
import unittest
from unittest import mock
from xml.etree.ElementTree import fromstring
from zipfile import ZipFile

from backend.base.definitions import IssueData, VolumeData
from backend.implementations import library_metadata as lm


def volume(**kw):
    base = dict(
        id=1, comicvine_id=123, title='Absolute Wonder Woman', alt_title=None,
        year=2024, volume_number=1, description='<p>Diana &amp; friends.<br/>Second line.</p>',
        site_url='https://comicvine.gamespot.com/x/4050-123/', publisher='DC Comics',
        monitored=True, monitor_new_issues=True, root_folder=1,
        folder='/library/Comics/Absolute Wonder Woman', custom_folder=False,
        special_version=None, special_version_locked=False, last_cv_fetch=0
    )
    base.update(kw)
    return VolumeData(**base)


def issue(**kw):
    base = dict(
        id=5, volume_id=1, comicvine_id=9, issue_number='12',
        calculated_issue_number=12.0, title='The Lasso', date='2025-03-19',
        description='<p>Issue text</p>', monitored=True, files=[]
    )
    base.update(kw)
    return IssueData(**base)


def make_cbz(path, members=None):
    with ZipFile(path, 'w') as zf:
        for name, data in (members or {'001.jpg': b'a' * 100, '002.jpg': b'b' * 100}).items():
            zf.writestr(name, data)
    return path


class XmlTests(unittest.TestCase):
    def test_issue_xml(self):
        root = fromstring(lm.comicinfo_xml(volume(), issue(), 20))
        get = lambda t: root.findtext(t)
        self.assertEqual(get('Series'), 'Absolute Wonder Woman')
        self.assertEqual(get('Number'), '12')
        self.assertEqual(get('Title'), 'The Lasso')
        self.assertEqual(get('Volume'), '1')
        self.assertEqual((get('Year'), get('Month'), get('Day')), ('2025', '3', '19'))
        self.assertEqual(get('Publisher'), 'DC Comics')
        self.assertEqual(get('Count'), '20')
        self.assertEqual(get('Summary'), 'Issue text')
        self.assertIn(lm.MARKER, get('Notes'))

    def test_falls_back_to_the_series_summary(self):
        root = fromstring(lm.comicinfo_xml(volume(), issue(description=''), 0))
        self.assertEqual(root.findtext('Summary'), 'Diana & friends.\nSecond line.')
        self.assertIsNone(root.find('Count'))

    def test_special_characters_are_escaped(self):
        xml = lm.comicinfo_xml(volume(title='Tom & <Jerry>'), issue(title='A "quote" & more'), 1)
        root = fromstring(xml)
        self.assertEqual(root.findtext('Series'), 'Tom & <Jerry>')

    def test_odd_dates(self):
        for date in (None, '', 'soon', '2025', '2025-07'):
            fromstring(lm.comicinfo_xml(volume(), issue(date=date), 1))
        root = fromstring(lm.comicinfo_xml(volume(), issue(date='2025'), 1))
        self.assertEqual(root.findtext('Year'), '2025')
        self.assertIsNone(root.find('Month'))

    def test_plain_text(self):
        self.assertEqual(lm.plain_text(None), '')
        self.assertEqual(lm.plain_text('<b>x</b>&nbsp;y'), 'x\xa0y')
        self.assertEqual(len(lm.plain_text('a' * 10000)), lm.MAX_SUMMARY)


class EmbedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.xml = lm.comicinfo_xml(volume(), issue(), 5)

    def tearDown(self):
        self.tmp.cleanup()

    def test_adds_comicinfo_and_keeps_pages_and_date(self):
        cbz = make_cbz(os.path.join(self.dir, 'a.cbz'))
        os.utime(cbz, (1_600_000_000, 1_600_000_000))
        self.assertTrue(lm.embed_comicinfo(cbz, self.xml))
        with ZipFile(cbz) as zf:
            self.assertEqual(sorted(zf.namelist()), ['001.jpg', '002.jpg', 'ComicInfo.xml'])
            self.assertEqual(zf.read('001.jpg'), b'a' * 100)
            self.assertEqual(zf.read('ComicInfo.xml'), self.xml)
            self.assertIsNone(zf.testzip())
        self.assertEqual(int(os.stat(cbz).st_mtime), 1_600_000_000)
        self.assertEqual([f for f in os.listdir(self.dir)], ['a.cbz'])  # no temp file left

    def test_second_run_changes_nothing(self):
        cbz = make_cbz(os.path.join(self.dir, 'a.cbz'))
        self.assertTrue(lm.embed_comicinfo(cbz, self.xml))
        self.assertFalse(lm.embed_comicinfo(cbz, self.xml))

    def test_our_old_info_is_updated(self):
        cbz = make_cbz(os.path.join(self.dir, 'a.cbz'))
        lm.embed_comicinfo(cbz, lm.comicinfo_xml(volume(), issue(title='Old'), 5))
        self.assertTrue(lm.embed_comicinfo(cbz, self.xml))
        with ZipFile(cbz) as zf:
            self.assertEqual(zf.namelist().count('ComicInfo.xml'), 1)
            self.assertIn(b'The Lasso', zf.read('ComicInfo.xml'))

    def test_foreign_comicinfo_is_respected(self):
        foreign = b'<ComicInfo><Series>Mine</Series></ComicInfo>'
        cbz = make_cbz(os.path.join(self.dir, 'a.cbz'), {'1.jpg': b'x', 'ComicInfo.xml': foreign})
        self.assertFalse(lm.embed_comicinfo(cbz, self.xml))
        with ZipFile(cbz) as zf:
            self.assertEqual(zf.read('ComicInfo.xml'), foreign)

    def test_other_formats_and_broken_files_are_left_alone(self):
        for name, data in (('a.cbr', b'Rar!\x1a\x07\x00xx'), ('a.pdf', b'%PDF-1.7'), ('b.cbz', b'not a zip')):
            path = os.path.join(self.dir, name)
            with open(path, 'wb') as f:
                f.write(data)
            self.assertFalse(lm.embed_comicinfo(path, self.xml), name)
            with open(path, 'rb') as f:
                self.assertEqual(f.read(), data)

    def test_no_space_means_no_change(self):
        cbz = make_cbz(os.path.join(self.dir, 'a.cbz'))
        before = open(cbz, 'rb').read()
        with mock.patch.object(lm, 'disk_usage', return_value=mock.Mock(free=10)):
            self.assertFalse(lm.embed_comicinfo(cbz, self.xml))
        self.assertEqual(open(cbz, 'rb').read(), before)

    def test_failure_while_copying_leaves_the_original(self):
        cbz = make_cbz(os.path.join(self.dir, 'a.cbz'))
        before = open(cbz, 'rb').read()
        with mock.patch.object(lm, 'replace', side_effect=OSError('disk')):
            self.assertFalse(lm.embed_comicinfo(cbz, self.xml))
        self.assertEqual(open(cbz, 'rb').read(), before)
        self.assertEqual(os.listdir(self.dir), ['a.cbz'])


class SeriesFilesTests(unittest.TestCase):
    JPEG = b'\xff\xd8\xff\xe0' + b'0' * 50

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_writes_series_json_and_cover(self):
        lm.write_series_files(self.dir, volume(), self.JPEG, 20)
        self.assertTrue(os.path.exists(os.path.join(self.dir, 'cover.jpg')))
        import json
        meta = json.load(open(os.path.join(self.dir, 'series.json'), encoding='utf-8'))['metadata']
        self.assertEqual(meta['name'], 'Absolute Wonder Woman')
        self.assertEqual(meta['comicid'], 123)
        self.assertEqual(meta['total_issues'], 20)
        self.assertEqual(meta['description_text'], 'Diana & friends.\nSecond line.')
        self.assertEqual(meta['comic_image'], 'cover.jpg')

    def test_existing_files_are_never_replaced(self):
        for name in ('cover.png', 'series.json'):
            with open(os.path.join(self.dir, name), 'wb') as f:
                f.write(b'mine')
        lm.write_series_files(self.dir, volume(), self.JPEG, 20)
        self.assertEqual(sorted(os.listdir(self.dir)), ['cover.png', 'series.json'])
        self.assertEqual(open(os.path.join(self.dir, 'series.json'), 'rb').read(), b'mine')

    def test_unknown_image_is_not_written(self):
        lm.write_series_files(self.dir, volume(), b'<html>', 3)
        self.assertFalse(os.path.exists(os.path.join(self.dir, 'cover.jpg')))
        self.assertTrue(os.path.exists(os.path.join(self.dir, 'series.json')))

    def test_missing_folder_is_ignored(self):
        lm.write_series_files(os.path.join(self.dir, 'nope'), volume(), self.JPEG, 1)

    def test_series_folder_is_the_first_folder_below_the_root(self):
        self.assertEqual(lm.series_folder_of('/r/Comics/', '/r/Comics/Batman/Volume 01 (2020)'), '/r/Comics/Batman')
        self.assertEqual(lm.series_folder_of('/r/Comics/', '/r/Comics/Batman'), '/r/Comics/Batman')
