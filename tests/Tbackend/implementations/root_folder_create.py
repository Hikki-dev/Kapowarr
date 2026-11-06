import os
import tempfile
import unittest

from backend.base.custom_exceptions import FolderNotFound
from backend.implementations.root_folders import make_missing_folder


class MakeMissingFolderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_creates_one_new_folder(self):
        new = os.path.join(self.base, "Manga 18+")
        make_missing_folder(new)
        self.assertTrue(os.path.isdir(new))

    def test_trailing_slash_is_fine(self):
        new = os.path.join(self.base, "Comics 2") + os.sep
        make_missing_folder(new)
        self.assertTrue(os.path.isdir(os.path.join(self.base, "Comics 2")))

    def test_missing_parent_is_refused_and_nothing_is_built(self):
        with self.assertRaises(FolderNotFound):
            make_missing_folder(os.path.join(self.base, "typo", "Manga"))
        self.assertFalse(os.path.exists(os.path.join(self.base, "typo")))

    def test_climbing_out_is_resolved_not_followed(self):
        # abspath collapses the dots: this asks for "<base>/../evil" -> a sibling of base,
        # whose parent exists, so it is the same as asking for that plain folder
        target = os.path.join(self.base, "..", "kapowarr-rf-test-evil")
        try:
            make_missing_folder(target)
            self.assertTrue(os.path.isdir(os.path.abspath(target)))
        finally:
            if os.path.isdir(os.path.abspath(target)):
                os.rmdir(os.path.abspath(target))

    def test_hidden_and_dotted_names_are_refused(self):
        for name in (".hidden", "trailing."):
            with self.assertRaises(FolderNotFound, msg=name):
                make_missing_folder(os.path.join(self.base, name))
            self.assertFalse(os.path.exists(os.path.join(self.base, name)))

    def test_root_and_empty_are_refused(self):
        for path in ("/", ""):
            with self.assertRaises(FolderNotFound, msg=path):
                make_missing_folder(path)

    def test_null_byte_is_refused(self):
        with self.assertRaises(FolderNotFound):
            make_missing_folder(os.path.join(self.base, "a\x00b"))

    def test_existing_folder_is_left_alone(self):
        existing = os.path.join(self.base, "there")
        os.mkdir(existing)
        with self.assertRaises(FileExistsError):
            make_missing_folder(existing)
