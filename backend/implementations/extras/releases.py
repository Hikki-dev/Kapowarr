# -*- coding: utf-8 -*-

"""
The release calendar: what comes out this week, and which new series start.

* `library_releases` needs no internet: it reads the release dates that the
  library already knows.
* `first_issues` asks ComicVine (or Metron when ComicVine fails) for the
  number ones that go on sale in a week.
* `follow_new_series` adds the number ones that match the watch list.
"""

import re
from calendar import monthrange
from datetime import date, timedelta
from time import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from backend.base.logging import LOGGER
from backend.implementations.extras import metron
from backend.implementations.extras.store import ensure_tables
from backend.internals.db import commit, get_db


def week_bounds(day: date) -> Tuple[date, date]:
    "Monday and Sunday of the week that holds `day`."
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


VIEWS = ("day", "week", "month", "year")
MAX_UPCOMING_MONTHS = 24


def parse_day(value: Optional[str], default: date) -> date:
    "A `YYYY-MM-DD` text as a date. Nothing given means `default`; anything else raises ValueError."
    if value is None or value == "":
        return default
    return date.fromisoformat(value)


def add_months(day: date, months: int) -> date:
    "`day` moved by whole months. The day of the month is kept, or the last day when the month is shorter (31 Jan + 1 month = 28 or 29 Feb)."
    index = day.year * 12 + (day.month - 1) + months
    year, month = divmod(index, 12)
    month += 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def view_bounds(view: str, anchor: date) -> Tuple[date, date]:
    "First and last day shown by a view that is centred on `anchor`."
    if view == "day":
        return anchor, anchor
    if view == "week":
        return week_bounds(anchor)
    if view == "month":
        return (anchor.replace(day=1),
                anchor.replace(day=monthrange(anchor.year, anchor.month)[1]))
    if view == "year":
        return date(anchor.year, 1, 1), date(anchor.year, 12, 31)
    raise ValueError(f"unknown view: {view}")


def shift_anchor(view: str, anchor: date, steps: int) -> date:
    "The anchor of the previous (-1) or next (+1) period of a view."
    if view == "day":
        return anchor + timedelta(days=steps)
    if view == "week":
        return anchor + timedelta(weeks=steps)
    if view == "month":
        return add_months(anchor, steps)
    if view == "year":
        return add_months(anchor, 12 * steps)
    raise ValueError(f"unknown view: {view}")


def grid_bounds(start: date, end: date) -> Tuple[date, date]:
    "A month as whole weeks: from the Monday on or before `start` to the Sunday on or after `end`."
    return week_bounds(start)[0], week_bounds(end)[1]


def release_state(
    release: Dict[str, Any], today: date
) -> str:
    """One word for how an issue stands:
    `downloaded`, `wanted` (out and missing), `upcoming` (not out yet) or `unmonitored`."""
    if release["has_file"]:
        return "downloaded"
    if not release["monitored"]:
        return "unmonitored"
    return "upcoming" if release["date"] > today.isoformat() else "wanted"


def library_releases(start: date, end: date) -> List[Dict[str, Any]]:
    "Issues in the library with a release date between two dates (inclusive)."
    ensure_tables()
    rows = get_db().execute("""
        SELECT i.id, i.volume_id, v.title, i.issue_number, i.date, i.monitored,
            EXISTS (SELECT 1 FROM issues_files f WHERE f.issue_id = i.id)
        FROM issues i
        INNER JOIN volumes v ON v.id = i.volume_id
        WHERE i.date BETWEEN ? AND ?
        ORDER BY i.date, v.title, i.calculated_issue_number;
        """, (start.isoformat(), end.isoformat())).fetchall()
    return [
        {"issue_id": r[0], "volume_id": r[1], "volume_title": r[2],
         "issue_number": r[3], "date": r[4], "monitored": bool(r[5]),
         "has_file": bool(r[6])}
        for r in rows
    ]


def month_summary(year: int, today: date) -> List[Dict[str, Any]]:
    "For each month of a year: how many issues come out, and how they stand."
    ensure_tables()
    summary = [
        {"month": m, "total": 0, "downloaded": 0, "wanted": 0,
         "upcoming": 0, "unmonitored": 0}
        for m in range(1, 13)
    ]
    for r in library_releases(date(year, 1, 1), date(year, 12, 31)):
        month = int(r["date"][5:7])
        entry = summary[month - 1]
        entry["total"] += 1
        entry[release_state(r, today)] += 1
    return summary


def upcoming(today: date, months: int, limit: int = 300) -> Dict[str, Any]:
    """What is still to come in the next `months` months (1 to 24):
    every issue with a date from today on, and the next one of each series."""
    months = max(1, min(int(months), MAX_UPCOMING_MONTHS))
    end = add_months(today, months)
    rows = library_releases(today, end)
    for r in rows:
        r["state"] = release_state(r, today)
        r["days_away"] = (date.fromisoformat(r["date"]) - today).days
    next_up: Dict[int, Dict[str, Any]] = {}
    for r in rows:
        next_up.setdefault(r["volume_id"], r)
    return {"start": today.isoformat(), "end": end.isoformat(),
            "months": months, "releases": rows[:limit],
            "truncated": len(rows) > limit,
            "next_per_series": sorted(next_up.values(), key=lambda r: (r["date"], r["volume_title"]))}


def calendar(view: str, anchor: date, today: date) -> Dict[str, Any]:
    "Everything the calendar page needs for one period."
    start, end = view_bounds(view, anchor)
    result: Dict[str, Any] = {
        "view": view, "anchor": anchor.isoformat(), "today": today.isoformat(),
        "start": start.isoformat(), "end": end.isoformat(),
        "prev": shift_anchor(view, anchor, -1).isoformat(),
        "next": shift_anchor(view, anchor, 1).isoformat(),
    }
    if view == "year":
        result["months"] = month_summary(anchor.year, today)
        return result
    shown_start, shown_end = (grid_bounds(start, end) if view == "month" else (start, end))
    result["grid_start"], result["grid_end"] = shown_start.isoformat(), shown_end.isoformat()
    rows = library_releases(shown_start, shown_end)
    for r in rows:
        r["state"] = release_state(r, today)
    result["releases"] = rows
    return result


def _plain(title: str) -> str:
    "A title without a year in brackets, case and extra spaces: `Saga (2012)` -> `saga`."
    return " ".join(re.sub(r"\(\s*\d{4}\s*\)", " ", title or "").lower().split())


def matches_watchlist(
    entry: Dict[str, Any], watchlist: Iterable[Tuple[str, str]]
) -> bool:
    """Whether a new series is one the user wants followed.

    Args:
        entry: has `title` and `publisher`.
        watchlist: (kind, value) pairs. `series` must equal the title (a year
            in brackets and capitals are ignored): the safest choice.
            `publisher` must equal the publisher; `keyword` must be part of
            the title.
    """
    title = (entry.get("title") or "").lower()
    publisher = (entry.get("publisher") or "").lower()
    for kind, value in watchlist:
        value = value.strip().lower()
        if not value:
            continue
        if kind == "series" and _plain(value) == _plain(title):
            return True
        if kind == "publisher" and value == publisher:
            return True
        if kind == "keyword" and value in title:
            return True
    return False


def _comicvine_first_issues(start: date, end: date) -> List[Dict[str, Any]]:
    from backend.base.definitions import Constants
    from backend.base.helpers import Session
    from backend.internals.settings import Settings

    key = Settings().sv.comicvine_api_key
    if not key:
        raise RuntimeError("no ComicVine key")

    with Session() as session:
        base = {"api_key": key, "format": "json"}
        issues = session.get(
            f"{Constants.CV_API_URL}/issues/",
            params={**base, "limit": 100,
                    "field_list": "id,issue_number,store_date,volume",
                    "filter": f"store_date:{start}|{end},issue_number:1",
                    "sort": "store_date:asc"},
            timeout=60
        ).json()
        if issues.get("status_code") != 1:
            raise RuntimeError(f"ComicVine said {issues.get('error')}")

        found: Dict[int, Dict[str, Any]] = {}
        for issue in issues.get("results", []):
            volume = issue.get("volume") or {}
            if volume.get("id") and str(issue.get("issue_number")) == "1":
                found.setdefault(volume["id"], {
                    "comicvine_id": volume["id"],
                    "title": volume.get("name") or "",
                    "issue_number": "1",
                    "store_date": issue.get("store_date"),
                    "publisher": None, "start_year": None
                })

        for batch_start in range(0, len(found), 50):
            ids = list(found)[batch_start:batch_start + 50]
            volumes = session.get(
                f"{Constants.CV_API_URL}/volumes/",
                params={**base, "limit": 100,
                        "field_list": "id,publisher,start_year",
                        "filter": "id:" + "|".join(map(str, ids))},
                timeout=60
            ).json()
            for volume in volumes.get("results", []):
                entry = found.get(volume.get("id"))
                if entry:
                    publisher = volume.get("publisher") or {}
                    entry["publisher"] = publisher.get("name")
                    entry["start_year"] = volume.get("start_year")

    return list(found.values())


def first_issues(start: date, end: date) -> Tuple[List[Dict[str, Any]], str]:
    """The number ones released in a week, and where they came from.

    ComicVine is used first. If it fails (rate limit, blocked, no key) and
    Metron is set up, Metron answers instead.
    """
    try:
        found, source = _comicvine_first_issues(start, end), "ComicVine"
    except Exception as e:
        LOGGER.warning("ComicVine could not list new releases: %s", e)
        if not metron.enabled():
            return [], "none"
        found, source = metron.first_issues(start, end), "Metron"

    library_ids = {
        r[0] for r in get_db().execute("SELECT comicvine_id FROM volumes;")
    }
    for entry in found:
        entry["in_library"] = entry["comicvine_id"] in library_ids
    return found, source


def follow_new_series(
    start: date, end: date, add_volume=None
) -> List[Dict[str, Any]]:
    """Add the number ones of a week that match the watch list.

    Args:
        add_volume: function(comicvine_id) that adds the series; given for
            tests. By default it adds the series to the first root folder,
            monitored, and starts a search.

    Returns:
        The series that were added.
    """
    ensure_tables()
    db = get_db()
    watchlist: Sequence[Tuple[str, str]] = db.execute(
        "SELECT kind, value FROM fork_watchlist;"
    ).fetchall()
    if not watchlist:
        return []

    already = {r[0] for r in db.execute("SELECT comicvine_id FROM fork_followed;")}
    entries, _ = first_issues(start, end)
    added = []
    for entry in entries:
        if (
            entry["in_library"]
            or entry["comicvine_id"] in already
            or not matches_watchlist(entry, watchlist)
        ):
            continue
        try:
            (add_volume or _add_volume)(entry["comicvine_id"])
        except Exception:
            LOGGER.exception("Could not follow %s", entry["title"])
            continue
        db.execute(
            "INSERT OR IGNORE INTO fork_followed VALUES (?, ?, ?);",
            (entry["comicvine_id"], entry["title"], int(time()))
        )
        commit()
        added.append(entry)
        LOGGER.info("Followed new series: %s", entry["title"])
    return added


def _add_volume(comicvine_id: int) -> int:
    from backend.base.definitions import MonitorScheme
    from backend.features.tasks import AutoSearchVolume, TaskHandler
    from backend.implementations.root_folders import RootFolders
    from backend.implementations.volumes import Library

    folders = RootFolders().get_all()
    if not folders:
        raise RuntimeError("no root folder")
    volume_id = Library.add(
        comicvine_id, folders[0].id, True, MonitorScheme.ALL, True, None, None,
        False
    )
    TaskHandler().add(AutoSearchVolume(volume_id))
    return volume_id
