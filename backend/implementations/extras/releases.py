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
from datetime import date, timedelta
from time import time
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from backend.base.logging import LOGGER
from backend.implementations.extras import metron
from backend.implementations.extras.store import ensure_tables
from backend.internals.db import commit, get_db


def week_bounds(day: date) -> Tuple[date, date]:
    "Monday and Sunday of the week that holds `day`."
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


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
