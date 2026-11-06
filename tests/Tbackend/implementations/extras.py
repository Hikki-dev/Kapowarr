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
        absolute = {"title": "Absolute Batman (2024)", "publisher": "DC"}
        self.assertTrue(releases.matches_watchlist(absolute, [("series", "absolute batman")]))
        self.assertFalse(releases.matches_watchlist({"title": "Batman", "publisher": "DC"}, [("series", "Absolute Batman")]))
        self.assertFalse(releases.matches_watchlist({"title": "Absolute Batman Special"}, [("series", "Absolute Batman")]))
        self.assertFalse(releases.matches_watchlist({"title": None, "publisher": None}, [("series", "x")]))
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


class CalendarViewTests(unittest.TestCase):
    "Day, week, month and year: the edges of dates."

    def test_bounds_of_each_view(self):
        d = date(2026, 11, 5)  # a Thursday
        self.assertEqual(releases.view_bounds("day", d), (d, d))
        self.assertEqual(releases.view_bounds("week", d), (date(2026, 11, 2), date(2026, 11, 8)))
        self.assertEqual(releases.view_bounds("month", d), (date(2026, 11, 1), date(2026, 11, 30)))
        self.assertEqual(releases.view_bounds("year", d), (date(2026, 1, 1), date(2026, 12, 31)))
        with self.assertRaises(ValueError):
            releases.view_bounds("decade", d)

    def test_leap_year_february(self):
        self.assertEqual(releases.view_bounds("month", date(2028, 2, 10))[1], date(2028, 2, 29))
        self.assertEqual(releases.view_bounds("month", date(2027, 2, 10))[1], date(2027, 2, 28))

    def test_moving_between_periods_keeps_a_valid_day(self):
        self.assertEqual(releases.shift_anchor("month", date(2026, 1, 31), 1), date(2026, 2, 28))
        self.assertEqual(releases.shift_anchor("month", date(2028, 1, 31), 1), date(2028, 2, 29))
        self.assertEqual(releases.shift_anchor("month", date(2026, 12, 15), 1), date(2027, 1, 15))
        self.assertEqual(releases.shift_anchor("month", date(2026, 1, 15), -1), date(2025, 12, 15))
        self.assertEqual(releases.shift_anchor("year", date(2028, 2, 29), 1), date(2029, 2, 28))
        self.assertEqual(releases.shift_anchor("week", date(2026, 12, 30), 1), date(2027, 1, 6))
        self.assertEqual(releases.shift_anchor("day", date(2026, 12, 31), 1), date(2027, 1, 1))

    def test_month_grid_is_whole_weeks_monday_to_sunday(self):
        start, end = releases.view_bounds("month", date(2026, 11, 5))
        first, last = releases.grid_bounds(start, end)
        self.assertEqual((first, last), (date(2026, 10, 26), date(2026, 12, 6)))
        self.assertEqual(first.weekday(), 0)
        self.assertEqual(last.weekday(), 6)
        # a month that starts on a Monday and ends on a Sunday needs no padding
        self.assertEqual(releases.grid_bounds(date(2026, 6, 1), date(2026, 6, 30)), (date(2026, 6, 1), date(2026, 7, 5)))

    def test_parse_day(self):
        today = date(2026, 11, 5)
        self.assertEqual(releases.parse_day(None, today), today)
        self.assertEqual(releases.parse_day("", today), today)
        self.assertEqual(releases.parse_day("2026-02-28", today), date(2026, 2, 28))
        for bad in ("2026-02-30", "11/05/2026", "tomorrow", "2026-13-01"):
            with self.assertRaises(ValueError):
                releases.parse_day(bad, today)

    def test_state_words(self):
        today = date(2026, 11, 5)
        r = lambda **k: {"has_file": False, "monitored": True, "date": "2026-11-01", **k}
        self.assertEqual(releases.release_state(r(has_file=True), today), "downloaded")
        self.assertEqual(releases.release_state(r(), today), "wanted")
        self.assertEqual(releases.release_state(r(date="2026-11-05"), today), "wanted")  # out today
        self.assertEqual(releases.release_state(r(date="2026-11-06"), today), "upcoming")
        self.assertEqual(releases.release_state(r(monitored=False), today), "unmonitored")
        # a file wins over everything else
        self.assertEqual(releases.release_state(r(has_file=True, monitored=False, date="2030-01-01"), today), "downloaded")

    def _db(self):
        db = make_db()
        db.executescript("""
            INSERT INTO volumes VALUES (1, 100, 'Saga', 2012, 1), (2, 200, 'Ms. Marvel', 2014, 1);
            INSERT INTO issues VALUES
              (1, 1, '5', 5, '2026-11-04', 1), (2, 1, '6', 6, '2026-12-02', 1), (3, 1, '7', 7, '2027-01-06', 1),
              (4, 2, '12', 12, '2026-11-30', 1), (5, 2, '13', 13, NULL, 1), (6, 2, '1', 1, '2026-02-28', 1),
              (7, 2, '2', 2, '2028-02-29', 0);
            INSERT INTO files VALUES (1, '/c/saga5.cbz', 1); INSERT INTO issues_files VALUES (1, 1);
        """)
        return db

    def test_month_view_includes_the_grid_days_around_it(self):
        with patched(self._db(), releases, store):
            r = releases.calendar("month", date(2026, 12, 15), date(2026, 11, 5))
        self.assertEqual((r["start"], r["end"]), ("2026-12-01", "2026-12-31"))
        self.assertEqual((r["grid_start"], r["grid_end"]), ("2026-11-30", "2027-01-03"))
        self.assertEqual([x["issue_number"] for x in r["releases"]], ["12", "6"])  # Nov 30 is shown in the grid
        self.assertEqual((r["prev"], r["next"]), ("2026-11-15", "2027-01-15"))

    def test_undated_issues_never_appear(self):
        with patched(self._db(), releases, store):
            rows = releases.library_releases(date(2026, 1, 1), date(2030, 12, 31))
        self.assertNotIn("13", [x["issue_number"] for x in rows])
        self.assertEqual(len(rows), 6)

    def test_year_view_counts_per_month(self):
        with patched(self._db(), releases, store):
            r = releases.calendar("year", date(2026, 6, 1), date(2026, 11, 5))
        self.assertEqual(len(r["months"]), 12)
        self.assertEqual(r["months"][1]["total"], 1)       # Feb 2026: Ms. Marvel #1
        self.assertEqual(r["months"][10]["downloaded"], 1)  # Nov: Saga #5 has a file
        self.assertEqual(r["months"][10]["upcoming"], 1)    # Nov 30 is after today
        self.assertEqual(r["months"][10]["wanted"], 0)
        self.assertNotIn("releases", r)

    def test_year_view_states_add_up(self):
        with patched(self._db(), releases, store):
            months = releases.month_summary(2026, date(2026, 11, 5))
        for m in months:
            self.assertEqual(m["total"], m["downloaded"] + m["wanted"] + m["upcoming"] + m["unmonitored"])

    def test_empty_library_gives_empty_periods(self):
        with patched(make_db(), releases, store):
            self.assertEqual(releases.calendar("week", date(2026, 11, 5), date(2026, 11, 5))["releases"], [])
            self.assertEqual(sum(m["total"] for m in releases.calendar("year", date(2026, 11, 5), date(2026, 11, 5))["months"]), 0)
            self.assertEqual(releases.upcoming(date(2026, 11, 5), 3)["next_per_series"], [])

    def test_upcoming_lists_the_next_issue_of_each_series(self):
        with patched(self._db(), releases, store):
            r = releases.upcoming(date(2026, 11, 5), 3)
        self.assertEqual([(x["volume_title"], x["issue_number"]) for x in r["next_per_series"]],
                         [("Ms. Marvel", "12"), ("Saga", "6")])
        self.assertEqual(r["next_per_series"][0]["days_away"], 25)
        self.assertEqual(r["end"], "2027-02-05")
        self.assertFalse(r["truncated"])

    def test_upcoming_range_is_clamped_and_truncated(self):
        with patched(self._db(), releases, store):
            self.assertEqual(releases.upcoming(date(2026, 11, 5), 0)["months"], 1)
            self.assertEqual(releases.upcoming(date(2026, 11, 5), 999)["months"], releases.MAX_UPCOMING_MONTHS)
            self.assertTrue(releases.upcoming(date(2026, 11, 5), 12, limit=1)["truncated"])

    def test_today_is_included_in_upcoming(self):
        with patched(self._db(), releases, store):
            r = releases.upcoming(date(2026, 11, 4), 1)
        self.assertEqual(r["next_per_series"][0]["days_away"], 0)


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
        env = {"KAPOWARR_METRON_API_KEY": "k"}
        with mock.patch.dict(os.environ, env), mock.patch("requests.get", side_effect=RuntimeError):
            self.assertTrue(metron.enabled())
            self.assertEqual(metron.first_issues(date(2026, 1, 1), date(2026, 1, 7)), [])

    def test_comicvine_failure_falls_back_to_metron(self):
        db = make_db()
        env = {"KAPOWARR_METRON_API_KEY": "k"}
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


class KomgaNameTests(unittest.TestCase):
    def test_nested_volume_folders_get_the_series_name(self):
        from backend.implementations.extras.komga_sync import plan_name_fixes
        komga = [
            {"id": "a", "url": "/data/Comics/Kingdom Come/Volume 01 (1996)", "metadata": {"title": "Volume 01 (1996)", "summary": ""}},
            {"id": "b", "url": "/data/Comics/Absolute Batman", "metadata": {"title": "Absolute Batman", "summary": "x"}},
            {"id": "c", "url": "/data/Comics/Other/Volume 01 (2000)", "metadata": {"title": "Volume 01 (2000)", "titleLock": True, "summary": "kept"}},
            {"id": "d", "url": "/data/Comics/Unknown/Volume 02", "metadata": {"title": "Volume 02", "summary": ""}},
        ]
        volumes = [
            {"folder": "/library/Comics/Kingdom Come/Volume 01 (1996)/", "title": "Kingdom Come", "description": "Four issues."},
            {"folder": "/library/Comics/Absolute Batman", "title": "Absolute Batman", "description": "Dark."},
            {"folder": "/library/Comics/Other/Volume 01 (2000)", "title": "Other", "description": ""},
        ]
        plan = {p["id"]: p["patch"] for p in plan_name_fixes(komga, volumes)}
        self.assertEqual(plan["a"]["title"], "Kingdom Come")
        self.assertEqual(plan["a"]["summary"], "Four issues.")
        self.assertTrue(plan["a"]["titleLock"])
        self.assertNotIn("b", plan)          # already named, already has a summary
        self.assertNotIn("c", plan)          # title locked by the user, summary present
        self.assertNotIn("d", plan)          # not a Kapowarr volume
