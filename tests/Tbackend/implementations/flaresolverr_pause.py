import unittest
from unittest import mock

from backend.implementations.flaresolverr import FSBlocklist


class PauseTests(unittest.TestCase):
    def setUp(self):
        FSBlocklist.until.clear()

    def test_unknown_host_is_not_paused(self):
        self.assertFalse(FSBlocklist.is_paused("https://a.example/x"))

    def test_a_host_is_paused_for_all_its_urls(self):
        FSBlocklist.pause("https://fs2.comicfiles.ru/2024/a.cbz")
        self.assertTrue(FSBlocklist.is_paused("https://fs2.comicfiles.ru/other/b.cbz"))
        self.assertFalse(FSBlocklist.is_paused("https://getcomics.org/x"))

    def test_the_pause_ends(self):
        with mock.patch("backend.implementations.flaresolverr.time", return_value=1000.0):
            FSBlocklist.pause("https://h.example/x")
        with mock.patch("backend.implementations.flaresolverr.time", return_value=1000.0 + FSBlocklist.PAUSE - 1):
            self.assertTrue(FSBlocklist.is_paused("https://h.example/y"))
        with mock.patch("backend.implementations.flaresolverr.time", return_value=1000.0 + FSBlocklist.PAUSE + 1):
            self.assertFalse(FSBlocklist.is_paused("https://h.example/y"))
