import os
import sqlite3
import unittest
from contextlib import ExitStack
from datetime import date
from unittest import mock

from backend.implementations.extras import (komga_sync, metron, releases,
                                            requests_, store, upgrades)

DDL = """
CREATE TABLE volumes(id INTEGER PRIMARY KEY, comicvine_id INT, title TEXT, year INT, monitored BOOL DEFAULT 1);
CREATE TABLE issues(id INTEGER PRIMARY KEY, volume_id INT, issue_number TEXT, calculated_issue_number FLOAT, date TEXT, monitored BOOL DEFAULT 1);
CREATE TABLE files(id INTEGER PRIMARY KEY, filepath TEXT, size INT);
CREATE TABLE issues_files(file_id INT, issue_id INT);
CREATE TABLE download_queue(id INTEGER PRIMARY KEY, volume_id INT);
"""


def make_db():
    db = sqlite3.connect(":memory:")
    db.executescript(DDL)
    return db


def patched(db, *modules):
    stack = ExitStack()
    for m in modules:
        stack.enter_context(mock.patch.object(m, "get_db", return_value=db))
        if hasattr(m, "commit"):
            stack.enter_context(mock.patch.object(m, "commit"))
    stack.enter_context(mock.patch("backend.internals.db.get_db", return_value=db))
    store._ready = False
    return stack


class WeekAndWatchlistTests(unittest.TestCase):
    def test_week_runs_monday_to_sunday(self):
        self.assertEqual(releases.week_bounds(date(2026, 11, 5)),
                         (date(2026, 11, 2), date(2026, 11, 8)))
        self.assertEqual(releases.week_bounds(date(2026, 11, 2))[0], date(2026, 11, 2))
        self.assertEqual(releases.week_bounds(date(2026, 11, 8))[1], date(2026, 11, 8))

    def test_watchlist_rules(self):
        e = {"title": "Absolute Batman", "publisher": "DC Comics"}
        self.assertTrue(releases.matches_watchlist(e, [("publisher", "dc comics")]))
        self.assertFalse(releases.matches_watchlist(e, [("publisher", "DC")]))
        self.assertTrue(releases.matches_watchlist(e, [("keyword", "batman")]))
        self.assertFalse(releases.matches_watchlist(e, [("keyword", "saga")]))
        self.assertFalse(releases.matches_watchlist(e, [("keyword", "  ")]))
        self.assertFalse(releases.matches_watchlist({"title": None, "publisher": None}, [("keyword", "x")]))


class LibraryReleasesTests(unittest.TestCase):
    def test_only_the_week_and_with_state(self):
        db = make_db()
        db.executescript("""
            INSERT INTO volumes VALUES (1, 100, 'Saga', 2012, 1);
            INSERT INTO issues VALUES (1, 1, '5', 5, '2026-11-04', 1), (2, 1, '6', 6, '2026-11-11', 1), (3, 1, '4', 4, '2026-11-03', 0);
            INSERT INTO files VALUES (1, '/c/saga4.cbz', 1); INSERT INTO issues_files VALUES (1, 3);
        """)
        with patched(db, releases, store):
            rows = releases.library_releases(date(2026, 11, 2), date(2026, 11, 8))
        self.assertEqual([r["issue_number"] for r in rows], ["4", "5"])
        self.assertTrue(rows[0]["has_file"] and not rows[0]["monitored"])
        self.assertFalse(rows[1]["has_file"])


class FollowTests(unittest.TestCase):
    ENTRIES = [
        {"comicvine_id": 1, "title": "Absolute Batman", "publisher": "DC Comics", "in_library": False},
        {"comicvine_id": 2, "title": "Saga", "publisher": "Image", "in_library": False},
        {"comicvine_id": 3, "title": "Batman Again", "publisher": "DC Comics", "in_library": True},
    ]

    def run_follow(self, db, watch, added):
        db.executescript("CREATE TABLE IF NOT EXISTS volumes_dummy(x);")
        with patched(db, releases, store):
            store.ensure_tables()
            for kind, value in watch:
                db.execute("INSERT INTO fork_watchlist(kind, value) VALUES (?, ?)", (kind, value))
            with mock.patch.object(releases, "first_issues", return_value=(self.ENTRIES, "ComicVine")):
                return releases.follow_new_series(date(2026, 11, 2), date(2026, 11, 8), add_volume=added.append)

    def test_nothing_is_added_without_a_watchlist(self):
        added = []
        self.assertEqual(self.run_follow(make_db(), [], added), [])
        self.assertEqual(added, [])

    def test_matching_new_series_are_added_once(self):
        db, added = make_db(), []
        out = self.run_follow(db, [("keyword", "batman")], added)
        self.assertEqual(added, [1])  # 3 is already in the library, 2 does not match
        self.assertEqual([e["title"] for e in out], ["Absolute Batman"])
        with patched(db, releases, store):
            with mock.patch.object(releases, "first_issues", return_value=(self.ENTRIES, "x")):
                self.assertEqual(releases.follow_new_series(date(2026, 11, 2), date(2026, 11, 8), add_volume=added.append), [])
        self.assertEqual(added, [1])

    def test_a_failing_add_does_not_stop_the_rest(self):
        def add(cv):
            if cv == 1:
                raise RuntimeError
        db = make_db()
        with patched(db, releases, store):
            store.ensure_tables()
            db.execute("INSERT INTO fork_watchlist(kind, value) VALUES ('publisher', 'Image')")
            db.execute("INSERT INTO fork_watchlist(kind, value) VALUES ('keyword', 'batman')")
            with mock.patch.object(releases, "first_issues", return_value=(self.ENTRIES, "x")):
                out = releases.follow_new_series(date(2026, 11, 2), date(2026, 11, 8), add_volume=add)
        self.assertEqual([e["comicvine_id"] for e in out], [2])


class RequestTests(unittest.TestCase):
    def test_status_words(self):
        self.assertEqual(requests_.status_of(5, 5, 0), "Complete")
        self.assertEqual(requests_.status_of(5, 2, 1), "Downloading")
        self.assertEqual(requests_.status_of(5, 2, 0), "Partly there")
        self.assertEqual(requests_.status_of(5, 0, 0), "Searching")
        self.assertEqual(requests_.status_of(0, 0, 0), "Searching")

    def test_request_adds_then_lists(self):
        db = make_db()
        def adder(cv):
            db.execute("INSERT INTO volumes VALUES (7, ?, 'Saga', 2012, 1)", (cv,))
            db.execute("INSERT INTO issues VALUES (1, 7, '1', 1, '2012-03-14', 1), (2, 7, '2', 2, '2012-04-11', 1)")
            db.execute("INSERT INTO files VALUES (1, '/c/1.cbz', 1)")
            db.execute("INSERT INTO issues_files VALUES (1, 1)")
            return 7
        with patched(db, requests_, store):
            made = requests_.request_series("Ana", 100, volume_adder=adder)
            again = requests_.request_series("Ben", 100, volume_adder=adder)
            rows = requests_.list_requests()
        self.assertFalse(made["already_in_library"])
        self.assertTrue(again["already_in_library"])
        self.assertEqual([r["requester"] for r in rows], ["Ben", "Ana"])
        self.assertEqual((rows[0]["downloaded"], rows[0]["issues"], rows[0]["status"]), (1, 2, "Partly there"))


class UpgradeTests(unittest.TestCase):
    PREF = ["cbz", "cbr", "pdf"]

    def test_rank(self):
        self.assertEqual(upgrades.format_rank("CBZ", self.PREF), 0)
        self.assertEqual(upgrades.format_rank(".pdf", self.PREF), 2)
        self.assertEqual(upgrades.format_rank("epub", self.PREF), 3)

    def test_result_format_and_upgrade(self):
        self.assertEqual(upgrades.result_format({"display_title": "Saga 001 (2012).cbz"}), "cbz")
        self.assertEqual(upgrades.result_format({"display_title": "Saga 001 [PDF]"}), "pdf")
        self.assertEqual(upgrades.result_format({"display_title": "Saga 001", "link": "http://x/a.cbr?dl=1"}), "cbr")
        self.assertEqual(upgrades.result_format({"display_title": "Saga 001"}), "")
        better = upgrades.better_results(
            [{"display_title": "a.cbz"}, {"display_title": "b.pdf"}, {"display_title": "c"}], "pdf", self.PREF)
        self.assertEqual([r["display_title"] for r in better], ["a.cbz"])
        self.assertEqual(upgrades.better_results([{"display_title": "a.cbz"}], "cbz", self.PREF), [])

    def test_candidates(self):
        db = make_db()
        db.executescript("""
            INSERT INTO volumes VALUES (1, 1, 'Saga', 2012, 1);
            INSERT INTO issues VALUES (1, 1, '1', 1, 'x', 1), (2, 1, '2', 2, 'x', 1), (3, 1, '3', 3, 'x', 1);
            INSERT INTO files VALUES (1, '/c/1.pdf', 1), (2, '/c/2.cbz', 1), (3, '/c/3.pdf', 1), (4, '/c/3.cbz', 1);
            INSERT INTO issues_files VALUES (1, 1), (2, 2), (3, 3), (4, 3);
        """)
        with patched(db):
            found = upgrades.candidates(self.PREF)
            self.assertEqual([(c["issue_id"], c["format"]) for c in found], [(1, "pdf")])
            self.assertEqual(upgrades.candidates([]), [])

    def test_old_files_stay_unless_switched_on(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(upgrades.remove_superseded(3, self.PREF), 0)

    def test_old_file_is_removed_when_switched_on(self):
        db = make_db()
        db.executescript("""
            INSERT INTO files VALUES (3, '/c/3.pdf', 1), (4, '/c/3.cbz', 1), (5, '/c/3.cbr', 1);
            INSERT INTO issues_files VALUES (3, 3), (4, 3), (5, 3);
        """)
        deleted = []
        with patched(db), mock.patch.dict(os.environ, {"KAPOWARR_UPGRADE_REMOVE_OLD": "1"}), \
                mock.patch("backend.implementations.volumes.delete_issue_file", side_effect=deleted.append):
            n = upgrades.remove_superseded(3, self.PREF)
        self.assertEqual((n, sorted(deleted)), (2, [3, 5]))

    def test_nothing_is_removed_if_the_best_file_is_not_wanted(self):
        db = make_db()
        db.executescript("INSERT INTO files VALUES (1,'/c/a.epub',1),(2,'/c/a.zip',1); INSERT INTO issues_files VALUES (1,9),(2,9);")
        with patched(db), mock.patch.dict(os.environ, {"KAPOWARR_UPGRADE_REMOVE_OLD": "1"}):
            self.assertEqual(upgrades.remove_superseded(9, self.PREF), 0)


class KomgaTests(unittest.TestCase):
    SERIES = [{"name": "Saga", "url": "/comics/Saga (2012)", "booksCount": 10, "booksReadCount": 10, "booksUnreadCount": 0, "booksInProgressCount": 0},
              {"name": "Saga", "url": "/comics/Saga (2000)", "booksCount": 3, "booksReadCount": 0, "booksUnreadCount": 3, "booksInProgressCount": 0}]

    def test_names_are_compared_loosely(self):
        self.assertEqual(komga_sync.normalize("Ms. Marvel: Vol 2!"), "ms marvel vol 2")

    def test_match_by_name_and_year(self):
        self.assertEqual(komga_sync.match_series("saga", 2012, self.SERIES)["booksCount"], 10)
        self.assertEqual(komga_sync.match_series("Saga", 2000, self.SERIES)["booksCount"], 3)
        self.assertEqual(komga_sync.match_series("Nope", 2000, self.SERIES), {})

    def test_caught_up(self):
        done = komga_sync.progress({"volume_id": 1}, self.SERIES[0])
        self.assertTrue(done["caught_up"])
        todo = komga_sync.progress({"volume_id": 2}, self.SERIES[1])
        self.assertFalse(todo["caught_up"])
        unread_none = komga_sync.progress({}, {"booksCount": 4, "booksReadCount": 0, "booksUnreadCount": 0})
        self.assertFalse(unread_none["caught_up"])  # nothing read yet is not "caught up"
        reading = komga_sync.progress({}, {"booksCount": 4, "booksReadCount": 3, "booksUnreadCount": 0, "booksInProgressCount": 1})
        self.assertFalse(reading["caught_up"])

    def test_not_set_up_means_empty(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(komga_sync.fetch_series(), [])
            self.assertEqual(komga_sync.overview(), [])


class MetronTests(unittest.TestCase):
    BODY = {"count": 3, "results": [
        {"id": 10, "publisher": {"name": "Image"}, "series": {"id": 5, "name": "Saga", "year_began": 2012, "cv_id": 18166},
         "number": "1", "store_date": "2026-11-04"},
        {"id": 11, "publisher": "DC", "series": {"id": 6, "name": "Batman"}, "number": "2"},
        {"id": 12, "series": None, "number": "1"},
        "junk"]}

    def test_only_number_ones_with_a_name(self):
        found = metron.parse_issues(self.BODY)
        self.assertEqual([f["title"] for f in found], ["Saga"])
        self.assertEqual((found[0]["publisher"], found[0]["comicvine_id"], found[0]["start_year"]), ("Image", 18166, 2012))

    def test_odd_answers(self):
        for body in (None, "x", {"results": "no"}, {}):
            self.assertEqual(metron.parse_issues(body), [])

    def test_off_without_an_account(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertFalse(metron.enabled())
            self.assertEqual(metron.first_issues(date(2026, 1, 1), date(2026, 1, 7)), [])

    def test_a_failing_call_gives_nothing(self):
        env = {"KAPOWARR_METRON_USER": "u", "KAPOWARR_METRON_PASSWORD": "p"}
        with mock.patch.dict(os.environ, env), mock.patch("requests.get", side_effect=RuntimeError):
            self.assertTrue(metron.enabled())
            self.assertEqual(metron.first_issues(date(2026, 1, 1), date(2026, 1, 7)), [])

    def test_comicvine_failure_falls_back_to_metron(self):
        db = make_db()
        env = {"KAPOWARR_METRON_USER": "u", "KAPOWARR_METRON_PASSWORD": "p"}
        with patched(db, releases, store), mock.patch.dict(os.environ, env), \
                mock.patch.object(releases, "_comicvine_first_issues", side_effect=RuntimeError("rate limit")), \
                mock.patch.object(metron, "first_issues", return_value=[{"comicvine_id": 9, "title": "Saga"}]):
            found, source = releases.first_issues(date(2026, 11, 2), date(2026, 11, 8))
        self.assertEqual((source, found[0]["in_library"]), ("Metron", False))

    def test_no_fallback_without_metron(self):
        with mock.patch.dict(os.environ, {}, clear=True), \
                mock.patch.object(releases, "_comicvine_first_issues", side_effect=RuntimeError):
            self.assertEqual(releases.first_issues(date(2026, 11, 2), date(2026, 11, 8)), ([], "none"))


if __name__ == "__main__":
    unittest.main()
