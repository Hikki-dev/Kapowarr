import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

from backend.base import files
from backend.features.search_full import SearchCoordinator, is_dead_torrent
from backend.implementations import metrics, notifications
from backend.implementations.indexer_clients.torrent import Prowlarr as P


class LooserQueryTests(unittest.TestCase):
    def test_drops_year_volume_and_issue(self):
        self.assertEqual(P.looser_query("Batman (2016) #12"), "Batman")
        self.assertEqual(P.looser_query("Saga v3 003"), "Saga 003")
        self.assertEqual(P.looser_query("Saga 2012"), "Saga")

    def test_nothing_to_loosen(self):
        self.assertEqual(P.looser_query("Batman: Year One"), "")
        self.assertEqual(P.looser_query("(2016)"), "")


class FakeProwlarr(P.ProwlarrIndexer):
    "A Prowlarr whose answers come from a list, with no network or database"

    def __init__(self, answers):
        self._id, self._title, self.answers, self.asked = 1, "P", answers, []

    async def _ProwlarrIndexer__request(self, params):
        self.asked.append(params["query"])
        return self.answers.get(params["query"])


def torrent(title, seeders=3):
    return {"protocol": "torrent", "title": title, "seeders": seeders,
            "magnetUrl": "magnet:?xt=urn:btih:" + title.replace(" ", ""), "size": 1}


class ProwlarrSearchTests(unittest.TestCase):
    def setUp(self):
        P._cache.clear()
        for k in P.STATS:
            P.STATS[k] = 0

    def search(self, p, q):
        return asyncio.run(p.search({"query": q}))

    def test_same_search_is_answered_from_the_cache(self):
        p = FakeProwlarr({"Saga": [torrent("Saga 001")]})
        self.search(p, "Saga")
        self.search(p, "Saga")
        self.assertEqual(p.asked, ["Saga"])
        self.assertEqual(P.STATS["cache_hits"], 1)

    def test_an_empty_answer_tries_a_looser_query(self):
        p = FakeProwlarr({"Saga (2012) #1": [], "Saga": [torrent("Saga 001")]})
        found = self.search(p, "Saga (2012) #1")
        self.assertEqual(p.asked, ["Saga (2012) #1", "Saga"])
        self.assertEqual(len(found.results), 1)
        self.assertEqual(P.STATS["fallback_searches"], 1)

    def test_a_failed_search_is_not_cached(self):
        p = FakeProwlarr({})
        self.search(p, "Saga")
        self.search(p, "Saga")
        self.assertEqual(p.asked.count("Saga"), 2)
        self.assertEqual(P.STATS["failures"], 2)


class RankingTests(unittest.TestCase):
    def rank(self, result):
        c = object.__new__(SearchCoordinator)
        c.volume_data = SimpleNamespace(title="Saga", volume_number=1, year=2012)
        base = {"match": True, "series": "Saga", "volume_number": 1,
                "year": 2012, "issue_number": 1.0, "special_version": None}
        return c._rank_search_result({**base, **result}, 2012, 1.0)

    def test_dead_torrent_goes_last(self):
        self.assertTrue(is_dead_torrent({"seeders": 0}))
        self.assertFalse(is_dead_torrent({"seeders": None}))
        self.assertFalse(is_dead_torrent({}))
        self.assertGreater(self.rank({"seeders": 0}), self.rank({"seeders": 1}))
        self.assertGreater(self.rank({"seeders": 0}), self.rank({"seeders": None}))

    def test_more_seeders_wins_between_equals(self):
        self.assertLess(self.rank({"seeders": 50}), self.rank({"seeders": 2}))

    def test_a_worse_match_still_loses_to_a_better_match_with_fewer_seeders(self):
        self.assertLess(self.rank({"seeders": 1}),
                        self.rank({"seeders": 900, "match": False}))


class HardlinkTests(unittest.TestCase):
    def test_hardlink_shares_the_file(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "a.cbz"), os.path.join(d, "b.cbz")
            with open(src, "w") as f:
                f.write("x")
            files.link_or_copy(src, dst)
            self.assertEqual(os.stat(src).st_ino, os.stat(dst).st_ino)

    def test_falls_back_to_a_copy_when_linking_is_impossible(self):
        with tempfile.TemporaryDirectory() as d:
            src, dst = os.path.join(d, "a.cbz"), os.path.join(d, "b.cbz")
            with open(src, "w") as f:
                f.write("x")
            with mock.patch.object(files, "link", side_effect=OSError):
                files.link_or_copy(src, dst)
            with open(dst) as f:
                self.assertEqual(f.read(), "x")
            self.assertNotEqual(os.stat(src).st_ino, os.stat(dst).st_ino)

    def test_a_folder_is_linked_file_by_file(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(os.path.join(d, "t", "sub"))
            with open(os.path.join(d, "t", "sub", "1.cbz"), "w") as f:
                f.write("x")
            files.copy_directory(os.path.join(d, "t"), os.path.join(d, "out"))
            self.assertEqual(
                os.stat(os.path.join(d, "t", "sub", "1.cbz")).st_ino,
                os.stat(os.path.join(d, "out", "sub", "1.cbz")).st_ino)

    def test_the_switch_turns_it_off(self):
        with mock.patch.dict(os.environ, {"KAPOWARR_HARDLINK": "0"}):
            self.assertIs(files.copy_function_for_import(), files.copy)
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KAPOWARR_HARDLINK", None)
            self.assertIs(files.copy_function_for_import(), files.link_or_copy)


class NotificationTests(unittest.TestCase):
    def test_discord_ntfy_and_plain(self):
        _, k = notifications.build_notification("https://discord.com/api/webhooks/1/x", "T", "M")
        self.assertEqual(k["json"]["embeds"][0]["color"], notifications.COLORS["info"])
        _, k = notifications.build_notification("https://discord.com/api/webhooks/1/x", "T", "M", "failed")
        self.assertEqual(k["json"]["embeds"][0]["color"], notifications.COLORS["failed"])
        self.assertEqual(k["json"]["embeds"][0]["title"], "T")
        _, k = notifications.build_notification("https://ntfy.sh/mytopic", "Imported", "Saga 1")
        self.assertEqual(k["data"], b"Saga 1")
        _, k = notifications.build_notification("https://example.com/hook", "T", "M")
        self.assertEqual(k["json"], {"title": "T", "message": "M"})

    def test_a_title_with_odd_letters_cannot_break_the_header(self):
        _, k = notifications.build_notification("https://ntfy.sh/x", "Cómic ☃", "m")
        k["headers"]["Title"].encode("latin-1")

    def test_nothing_happens_when_not_set_up(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(notifications, "post") as post:
                notifications.notify("T", "M")
                notifications.scan_komga()
                post.assert_not_called()
            self.assertIsNone(notifications.komga_auth())

    def test_komga_sign_in(self):
        env = {"KAPOWARR_KOMGA_URL": "http://k:25600", "KAPOWARR_KOMGA_API_KEY": "abc"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(notifications.komga_auth(), {"headers": {"X-API-Key": "abc"}})
        env = {"KAPOWARR_KOMGA_URL": "http://k", "KAPOWARR_KOMGA_USER": "u", "KAPOWARR_KOMGA_PASSWORD": "p"}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(notifications.komga_auth(), {"auth": ("u", "p")})

    def test_errors_never_escape(self):
        env = {"KAPOWARR_NOTIFY_URL": "http://127.0.0.1:9/x"}
        with mock.patch.dict(os.environ, env, clear=True):
            with mock.patch.object(notifications, "post", side_effect=RuntimeError):
                with mock.patch.object(notifications, "_in_background", side_effect=lambda f: f()):
                    notifications.notify("T", "M")
        self.assertGreaterEqual(notifications.COUNTERS["notifications_failed"], 1)


class MetricsTests(unittest.TestCase):
    def test_text_format(self):
        text = metrics.render([("queue", "Downloads", 3), ("seconds", "Time", 1.5)])
        self.assertIn("kapowarr_queue 3\n", text)
        self.assertIn("kapowarr_seconds 1.5\n", text)
        self.assertIn("# TYPE kapowarr_queue gauge", text)
