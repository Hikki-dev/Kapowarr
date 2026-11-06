import os
import stat
import tempfile
import unittest
from unittest import mock
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from backend.base import safe_archive as sa
from backend.base.safe_archive import UnsafeArchive


def make_zip(path, members):
    "members: {name: bytes} or {name: ZipInfo-with-data tuple}"
    with ZipFile(path, "w", ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


class NamesTests(unittest.TestCase):
    def test_safe_names_are_split(self):
        self.assertEqual(sa.clean_member_name("a/b/c.cbz"), ["a", "b", "c.cbz"])
        self.assertEqual(sa.clean_member_name("./a//b.pdf"), ["a", "b.pdf"])
        self.assertEqual(sa.clean_member_name("a\\b.cbr"), ["a", "b.cbr"])

    def test_dangerous_names_are_refused(self):
        for name in ("../x.cbz", "a/../../x.cbz", "/etc/x.cbz", "C:/x.cbz",
                     "C:\\x.cbz", "a\\..\\..\\x.cbz", "a\x00.cbz"):
            with self.assertRaises(UnsafeArchive, msg=name):
                sa.clean_member_name(name)

    def test_junk(self):
        self.assertTrue(sa.is_junk(["__MACOSX", "a.cbz"]))
        self.assertTrue(sa.is_junk(["x", "._a.cbz"]))
        self.assertTrue(sa.is_junk([".DS_Store"]))
        self.assertTrue(sa.is_junk(["Thumbs.db"]))
        self.assertTrue(sa.is_junk([]))
        self.assertFalse(sa.is_junk(["Batman", "Batman 01.cbz"]))

    def test_issue_files(self):
        for name in ("a.cbz", "a.CBR", "a.pdf", "a.PDF", "a.zip"):
            self.assertTrue(sa.is_issue_file(name), name)
        for name in ("a.jpg", "a.xml", "a.txt", "cbz"):
            self.assertFalse(sa.is_issue_file(name), name)


class ZipTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.out = os.path.join(self.dir, "out")

    def tearDown(self):
        self.tmp.cleanup()

    def zip(self, members):
        return make_zip(os.path.join(self.dir, "a.zip"), members)

    def test_issues_are_extracted_and_the_rest_skipped(self):
        z = self.zip({
            "Kingdom Come/Kingdom Come 01.cbr": b"one",
            "Kingdom Come/Kingdom Come 02.cbz": b"two",
            "Kingdom Come/extra.pdf": b"pdf",
            "Kingdom Come/cover.jpg": b"img",
            "Kingdom Come/notes.txt": b"txt",
            "__MACOSX/Kingdom Come/._Kingdom Come 01.cbr": b"junk",
            "Kingdom Come/.DS_Store": b"junk",
        })
        got = sorted(os.path.relpath(f, self.out) for f in sa.extract_zip(z, self.out))
        self.assertEqual(got, [
            os.path.join("Kingdom Come", "Kingdom Come 01.cbr"),
            os.path.join("Kingdom Come", "Kingdom Come 02.cbz"),
            os.path.join("Kingdom Come", "extra.pdf"),
        ])
        with open(os.path.join(self.out, "Kingdom Come", "Kingdom Come 01.cbr"), "rb") as f:
            self.assertEqual(f.read(), b"one")

    def test_path_climbing_is_refused_and_nothing_escapes(self):
        z = self.zip({"../../evil.cbz": b"x", "ok.cbz": b"y"})
        with self.assertRaises(UnsafeArchive):
            sa.extract_zip(z, self.out)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "evil.cbz")))
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(self.dir), "evil.cbz")))

    def test_absolute_path_is_refused(self):
        z = self.zip({"/tmp/evil.cbz": b"x"})
        with self.assertRaises(UnsafeArchive):
            sa.extract_zip(z, self.out)

    def test_a_link_inside_is_refused(self):
        path = os.path.join(self.dir, "a.zip")
        with ZipFile(path, "w") as zf:
            info = ZipInfo("link.cbz")
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(info, "/etc/passwd")
        with self.assertRaises(UnsafeArchive):
            sa.extract_zip(path, self.out)

    def test_password_protected_is_refused(self):
        path = self.zip({"a.cbz": b"x"})
        data = bytearray(open(path, "rb").read())
        data[data.find(b"PK\x01\x02") + 8] |= 0x1  # "encrypted" in the central header
        open(path, "wb").write(data)
        with self.assertRaises(UnsafeArchive):
            sa.extract_zip(path, self.out)

    def test_nothing_to_extract(self):
        z = self.zip({"readme.txt": b"x", "cover.jpg": b"y"})
        with self.assertRaises(UnsafeArchive):
            sa.extract_zip(z, self.out)

    def test_too_many_files(self):
        z = self.zip({f"{i}.cbz": b"x" for i in range(6)})
        with mock.patch.dict(os.environ, {"KAPOWARR_EXTRACT_MAX_FILES": "5"}):
            with self.assertRaises(UnsafeArchive):
                sa.extract_zip(z, self.out)

    def test_too_big(self):
        z = self.zip({"a.cbz": b"x" * 4096})
        with mock.patch.dict(os.environ, {"KAPOWARR_EXTRACT_MAX_GB": "0.000001"}):
            with self.assertRaises(UnsafeArchive):
                sa.extract_zip(z, self.out)

    def test_zip_bomb_ratio(self):
        z = self.zip({"a.cbz": b"\x00" * (150 * 1024 * 1024)})
        with self.assertRaises(UnsafeArchive) as ctx:
            sa.extract_zip(z, self.out)
        self.assertIn("zip bomb", str(ctx.exception))

    def test_lying_header_is_caught_while_writing(self):
        z = self.zip({"a.cbz": b"x" * (3 * 1024 * 1024)})
        real_infolist = ZipFile.infolist

        def liar(self_):
            infos = real_infolist(self_)
            for i in infos:
                i.file_size = 1000  # Says tiny, is 3 MB
            return infos

        from zipfile import BadZipFile
        with mock.patch.object(ZipFile, "infolist", liar):
            # Either our own count or the zip library's checksum stops it
            with self.assertRaises((UnsafeArchive, BadZipFile)):
                sa.extract_zip(z, self.out)

    def test_not_enough_free_space(self):
        z = self.zip({"a.cbz": b"x" * 1000})
        fake = mock.Mock(free=100)
        with mock.patch.object(sa, "disk_usage", return_value=fake):
            with self.assertRaises(UnsafeArchive):
                sa.extract_zip(z, self.out)

    def test_broken_zip(self):
        path = os.path.join(self.dir, "a.zip")
        with open(path, "wb") as f:
            f.write(b"not a zip at all")
        from zipfile import BadZipFile
        with self.assertRaises(BadZipFile):
            sa.extract_zip(path, self.out)


class PruneTests(unittest.TestCase):
    def test_only_issue_files_are_kept(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("a/one.cbr", "a/cover.jpg", "a/._one.cbr", "b/two.pdf", "x.txt"):
                p = os.path.join(d, name)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, "wb").write(b"data")
            kept = sorted(os.path.relpath(f, d) for f in sa.prune_to_issue_files(d))
            self.assertEqual(kept, [os.path.join("a", "one.cbr"), os.path.join("b", "two.pdf")])
            self.assertFalse(os.path.exists(os.path.join(d, "a", "cover.jpg")))

    def test_links_are_removed(self):
        with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as outside:
            secret = os.path.join(outside, "secret.cbz")
            open(secret, "wb").write(b"secret")
            os.symlink(secret, os.path.join(d, "link.cbz"))
            os.symlink(outside, os.path.join(d, "linkdir"))
            open(os.path.join(d, "real.cbz"), "wb").write(b"real")
            kept = sa.prune_to_issue_files(d)
            self.assertEqual([os.path.basename(k) for k in kept], ["real.cbz"])
            self.assertTrue(os.path.exists(secret))  # Never touched
            self.assertFalse(os.path.islink(os.path.join(d, "link.cbz")))
            self.assertFalse(os.path.islink(os.path.join(d, "linkdir")))

    def test_nothing_left_is_an_error(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "a.jpg"), "wb").write(b"x")
            with self.assertRaises(UnsafeArchive):
                sa.prune_to_issue_files(d)


class RarListTests(unittest.TestCase):
    def listing(self, names, code=0):
        return mock.Mock(returncode=code, stdout="\n".join(names) + "\n")

    def test_good_listing(self):
        with mock.patch.object(sa, "run_rar", return_value=self.listing(["a/one.cbr", "a/two.cbz", "a/c.jpg"])):
            self.assertEqual(sa.check_rar("x.rar"), 2)

    def test_dangerous_listing(self):
        with mock.patch.object(sa, "run_rar", return_value=self.listing(["../evil.cbz"])):
            with self.assertRaises(UnsafeArchive):
                sa.check_rar("x.rar")

    def test_unreadable_rar(self):
        with mock.patch.object(sa, "run_rar", return_value=self.listing([], code=2)):
            with self.assertRaises(UnsafeArchive):
                sa.check_rar("x.rar")

    def test_no_issues_inside(self):
        with mock.patch.object(sa, "run_rar", return_value=self.listing(["readme.txt"])):
            with self.assertRaises(UnsafeArchive):
                sa.check_rar("x.rar")
