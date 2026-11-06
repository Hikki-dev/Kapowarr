import os
import tempfile
import unittest
from unittest import mock
from zipfile import ZIP_DEFLATED, ZipFile

from backend.base import file_safety as fs
from backend.base.file_safety import UnsafeFile

ZIP_BYTES = b'PK\x03\x04' + b'\x00' * 40
EXE_BYTES = b'MZ\x90\x00' + b'\x00' * 100


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name, data=b'x' * 10):
        path = os.path.join(self.dir, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'wb') as f:
            f.write(data)
        return path

    def zip(self, name, members):
        path = os.path.join(self.dir, name)
        with ZipFile(path, 'w', ZIP_DEFLATED) as zf:
            for member, data in members.items():
                zf.writestr(member, data)
        return path


class ProgramsTests(Base):
    def test_programs_by_name(self):
        for name in ('a.exe', 'a.bat', 'a.cmd', 'a.scr', 'a.vbs', 'a.ps1', 'a.sh',
                     'a.jar', 'a.msi', 'a.lnk', 'a.dll', 'a.apk', 'a.js', 'A.EXE',
                     'comic.cbz.exe', 'comic.pdf.scr', 'comic.cbr.bat', 'x.exe '):
            with self.assertRaises(UnsafeFile, msg=name):
                fs.check_file(self.write(name, b'data data data'))

    def test_programs_by_content_whatever_the_name(self):
        for data in (EXE_BYTES, b'\x7fELF\x02\x01', b'#!/bin/sh\nrm -rf ~',
                     b'\xcf\xfa\xed\xfe\x07', b'\xca\xfe\xba\xbe\x00'):
            for name in ('x.cbz', 'x.cbr', 'x.pdf', 'x.zip', 'x'):
                with self.assertRaises(UnsafeFile, msg=f'{name} {data[:4]!r}'):
                    fs.check_file(self.write(name, data))

    def test_empty_file(self):
        with self.assertRaises(UnsafeFile):
            fs.check_file(self.write('a.cbz', b''))

    def test_link_is_refused(self):
        target = self.write('real.cbz', ZIP_BYTES)
        link = os.path.join(self.dir, 'link.cbz')
        os.symlink(target, link)
        with self.assertRaises(UnsafeFile):
            fs.check_file(link)


class ArchiveTests(Base):
    def test_good_cbz(self):
        fs.check_file(self.zip('a.cbz', {'1.jpg': b'x', '2.jpg': b'y', 'ComicInfo.xml': b'<x/>'}))

    def test_cbz_with_a_program_inside(self):
        for member in ('setup.exe', 'run.bat', 'sub/dir/a.ps1', 'autorun.inf',
                       'page.jpg.exe', 'x.JS', 'a\\b\\c.cmd'):
            with self.assertRaises(UnsafeFile, msg=member):
                fs.check_file(self.zip('a.cbz', {'1.jpg': b'x', member: b'z'}))

    def test_cbz_that_is_not_a_zip(self):
        with self.assertRaises(UnsafeFile):
            fs.check_file(self.write('a.cbz', b'just some text, not a zip file'))

    def test_broken_zip(self):
        with self.assertRaises(UnsafeFile):
            fs.check_file(self.write('a.cbz', b'PK\x03\x04' + b'\xff' * 50))

    def test_cbr_that_is_a_zip(self):
        with self.assertRaises(UnsafeFile):
            fs.check_file(self.write('a.cbr', ZIP_BYTES))

    def test_rar_listing_is_checked(self):
        path = self.write('a.cbr', b'Rar!\x1a\x07\x00' + b'\x00' * 40)
        ok = mock.Mock(returncode=0, stdout='1.jpg\n2.jpg\n')
        bad = mock.Mock(returncode=0, stdout='1.jpg\nsetup.exe\n')
        broken = mock.Mock(returncode=2, stdout='')
        with mock.patch.object(fs, 'run_rar', return_value=ok):
            fs.check_file(path)
        with mock.patch.object(fs, 'run_rar', return_value=bad):
            with self.assertRaises(UnsafeFile):
                fs.check_file(path)
        with mock.patch.object(fs, 'run_rar', return_value=broken):
            with self.assertRaises(UnsafeFile):
                fs.check_file(path)

    def test_seven_zip_signature(self):
        fs.check_file(self.write('a.cb7', b"7z\xbc\xaf'\x1c" + b'\x00' * 20))
        with self.assertRaises(UnsafeFile):
            fs.check_file(self.write('b.cb7', ZIP_BYTES))

    def test_too_many_names(self):
        with self.assertRaises(UnsafeFile):
            fs.check_names([f'{i}.jpg' for i in range(fs.MAX_NAMES + 1)])


class PdfTests(Base):
    def test_good_pdf(self):
        fs.check_file(self.write('a.pdf', b'%PDF-1.7\n1 0 obj\n<< /Type /Catalog /OpenAction [3 0 R /Fit] >>\nendobj\n'))

    def test_not_a_pdf(self):
        with self.assertRaises(UnsafeFile):
            fs.check_file(self.write('a.pdf', b'<html>hello</html>'))

    def test_pdf_that_launches_or_runs_code(self):
        for risk in (b'/Launch', b'/JavaScript', b'/EmbeddedFile'):
            with self.assertRaises(UnsafeFile, msg=risk):
                fs.check_file(self.write('a.pdf', b'%PDF-1.7\n<< ' + risk + b' (x) >>'))

    def test_risk_split_over_two_reads_is_found(self):
        data = b'%PDF-1.7\n' + b'a' * (1024 * 1024 - 12) + b'/Launch' + b'b' * 100
        with self.assertRaises(UnsafeFile):
            fs.check_file(self.write('a.pdf', data))


class DownloadTests(Base):
    def test_good_single_file(self):
        self.assertIsNone(fs.problem_with([self.zip('a.cbz', {'1.jpg': b'x'})]))

    def test_bad_single_file(self):
        self.assertIn('program', fs.problem_with([self.write('a.exe', b'zzz')]))

    def test_missing_file_is_not_a_problem_here(self):
        self.assertIsNone(fs.problem_with([os.path.join(self.dir, 'gone.cbz')]))

    def test_torrent_folder_with_good_issues_and_junk(self):
        self.zip('t/One 01.cbz', {'1.jpg': b'x'})
        self.write('t/readme.txt', b'hi')
        self.write('t/cover.jpg', b'\xff\xd8\xff')
        self.assertIsNone(fs.problem_with([os.path.join(self.dir, 't')]))

    def test_program_next_to_issues_is_ignored_not_imported(self):
        # only issue files can reach the library, so a stray program is just left behind
        self.zip('t/One 01.cbz', {'1.jpg': b'x'})
        self.write('t/crack.exe', EXE_BYTES)
        self.assertIsNone(fs.problem_with([os.path.join(self.dir, 't')]))
        self.assertTrue(os.path.exists(os.path.join(self.dir, 't', 'crack.exe')))

    def test_torrent_folder_with_a_bad_issue(self):
        self.zip('t/One 01.cbz', {'1.jpg': b'x'})
        self.write('t/sub/Two.cbz', EXE_BYTES)
        self.assertIn('Two.cbz', fs.problem_with([os.path.join(self.dir, 't')]))

    def test_torrent_folder_with_a_program_inside_an_issue(self):
        self.zip('t/One 01.cbz', {'1.jpg': b'x', 'install.exe': b'z'})
        self.assertIsNotNone(fs.problem_with([os.path.join(self.dir, 't')]))

    def test_linked_folder_is_not_followed(self):
        outside = tempfile.TemporaryDirectory()
        try:
            with open(os.path.join(outside.name, 'evil.cbz'), 'wb') as f:
                f.write(EXE_BYTES)
            os.makedirs(os.path.join(self.dir, 't'))
            os.symlink(outside.name, os.path.join(self.dir, 't', 'link'))
            self.zip('t/One.cbz', {'1.jpg': b'x'})
            self.assertIsNone(fs.problem_with([os.path.join(self.dir, 't')]))
        finally:
            outside.cleanup()
