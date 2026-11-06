import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from backend.base.safe_archive import UnsafeArchive
from backend.implementations import converters as C


class SelectTests(unittest.TestCase):
    def pick(self, filepath, contains, convert, extract, only):
        settings = SimpleNamespace(
            extract_issue_ranges=extract, convert=convert, format_preference=["cbz", "cbr"]
        )
        fake = mock.Mock()
        fake.get_settings.return_value = settings
        with mock.patch.object(C, "Settings", return_value=fake), \
                mock.patch.object(C, "archive_contains_issues", return_value=contains):
            return C.ConvertersManager.select_converter(filepath, only)

    def test_extract_only_takes_issues_out_of_a_zip(self):
        p = self.pick("/c/a.zip", True, convert=False, extract=True, only=True)
        self.assertEqual(p.target_format, "folder")

    def test_extract_only_never_changes_a_format(self):
        self.assertIsNone(self.pick("/c/a.cbr", False, convert=False, extract=True, only=True))
        self.assertIsNone(self.pick("/c/a.cbz", False, convert=False, extract=True, only=True))
        self.assertIsNone(self.pick("/c/a.zip", False, convert=False, extract=True, only=True))

    def test_extract_off_means_no_extraction(self):
        p = self.pick("/c/a.zip", True, convert=False, extract=False, only=True)
        self.assertIsNone(p)

    def test_normal_conversion_still_works(self):
        p = self.pick("/c/a.cbr", False, convert=True, extract=False, only=False)
        self.assertEqual(p.target_format, "cbz")


class LibraryExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.vol = os.path.join(self.tmp.name, "Volume 01")
        os.makedirs(self.vol)
        self.archive = os.path.join(self.vol, "pack.zip")
        open(self.archive, "wb").write(b"zip")
        self.patches = [
            mock.patch.object(C, "Volume", return_value=SimpleNamespace(vd=SimpleNamespace(folder=self.vol))),
            mock.patch.object(C, "scan_files"),
            mock.patch.object(C, "mass_rename", side_effect=lambda v, filepath_filter: filepath_filter),
            mock.patch.object(C, "commit"),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        mock.patch.stopall()
        self.tmp.cleanup()

    def test_unsafe_archive_is_left_alone(self):
        def bad(file, folder):
            os.makedirs(folder)
            open(os.path.join(folder, "half.cbz"), "wb").write(b"x")
            raise UnsafeArchive("nope")
        out = C._extract_archive_to_library(self.archive, 1, bad)
        self.assertEqual(out, [self.archive])
        self.assertTrue(os.path.exists(self.archive))
        self.assertEqual(os.listdir(self.vol), ["pack.zip"])  # No leftover extraction folder

    def test_unreadable_archive_is_left_alone(self):
        def bad(file, folder):
            raise OSError("disk trouble")
        self.assertEqual(C._extract_archive_to_library(self.archive, 1, bad), [self.archive])
        self.assertTrue(os.path.exists(self.archive))

    def test_nothing_reaching_the_library_keeps_the_archive(self):
        def ok(file, folder):
            os.makedirs(folder)
            open(os.path.join(folder, "a.cbz"), "wb").write(b"x")
        with mock.patch.object(C, "extract_files_from_folder", return_value=[]):
            out = C._extract_archive_to_library(self.archive, 1, ok)
        self.assertEqual(out, [self.archive])
        self.assertTrue(os.path.exists(self.archive))

    def test_an_empty_result_file_keeps_the_archive(self):
        empty = os.path.join(self.vol, "a.cbz")
        open(empty, "wb").close()

        def ok(file, folder):
            os.makedirs(folder)
        with mock.patch.object(C, "extract_files_from_folder", return_value=[empty]):
            out = C._extract_archive_to_library(self.archive, 1, ok)
        self.assertEqual(out, [self.archive])
        self.assertTrue(os.path.exists(self.archive))

    def test_success_deletes_only_the_archive(self):
        issue = os.path.join(self.vol, "Issue 1.cbr")
        open(issue, "wb").write(b"real issue")

        def ok(file, folder):
            os.makedirs(folder)
        with mock.patch.object(C, "extract_files_from_folder", return_value=[issue]):
            out = C._extract_archive_to_library(self.archive, 1, ok)
        self.assertEqual(out, [issue])
        self.assertFalse(os.path.exists(self.archive))
        self.assertTrue(os.path.exists(issue))
        self.assertEqual(os.listdir(self.vol), ["Issue 1.cbr"])


class NoOverwriteTests(unittest.TestCase):
    def run_extract(self, existing_content, incoming_content, overwrite):
        with tempfile.TemporaryDirectory() as d:
            vol = os.path.join(d, "vol")
            src = os.path.join(d, "src")
            os.makedirs(vol)
            os.makedirs(src)
            dest = os.path.join(vol, "Issue 1.cbr")
            open(dest, "wb").write(existing_content)
            open(os.path.join(src, "Issue 1.cbr"), "wb").write(incoming_content)
            volume = mock.Mock()
            volume.get_data.return_value = SimpleNamespace(folder=vol, year=1996)
            volume.get_issues.return_value = []
            volume.get_ending_year.return_value = None
            with mock.patch.object(C, "Volume", return_value=volume), \
                    mock.patch.object(C, "folder_extraction_filter", return_value=True), \
                    mock.patch.object(C, "set_detected_extension", side_effect=lambda f: f), \
                    mock.patch.object(C, "extract_filename_data", return_value={}):
                result = C.extract_files_from_folder(src, 1, overwrite=overwrite)
            names = sorted(os.listdir(vol))
            kept = {n: open(os.path.join(vol, n), "rb").read() for n in names}
            return result, names, kept, vol

    def test_a_different_file_never_replaces_yours(self):
        result, names, kept, vol = self.run_extract(b"mine", b"theirs!", overwrite=False)
        self.assertEqual(names, ["Issue 1 (2).cbr", "Issue 1.cbr"])
        self.assertEqual(kept["Issue 1.cbr"], b"mine")
        self.assertEqual(kept["Issue 1 (2).cbr"], b"theirs!")
        self.assertEqual([os.path.basename(r) for r in result], ["Issue 1 (2).cbr"])

    def test_an_identical_file_is_kept_once(self):
        result, names, kept, vol = self.run_extract(b"same", b"same", overwrite=False)
        self.assertEqual(names, ["Issue 1.cbr"])
        self.assertEqual([os.path.basename(r) for r in result], ["Issue 1.cbr"])

    def test_default_still_replaces(self):
        result, names, kept, vol = self.run_extract(b"old", b"newer", overwrite=True)
        self.assertEqual(names, ["Issue 1.cbr"])
        self.assertEqual(kept["Issue 1.cbr"], b"newer")
