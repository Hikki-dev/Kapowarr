# -*- coding: utf-8 -*-

"""
Reading progress from Komga. For every series in the library that Komga also
has, how many issues are read, and whether you are caught up (everything that
is downloaded has been read). Caught-up series are searched for new issues
first. Uses the same `KAPOWARR_KOMGA_*` variables as the scan after import.
"""

from re import sub
from typing import Any, Dict, List, Sequence

from backend.implementations import notifications


def normalize(title: str) -> str:
    "A title in a form two apps can agree on."
    return sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def match_series(
    title: str, year: Any, komga_series: Sequence[Dict[str, Any]]
) -> Dict[str, Any]:
    """The Komga series that is the same as a library volume, or {}.
    The name must match; when several do, the one whose name or folder holds
    the start year wins."""
    wanted = normalize(title)
    same = [s for s in komga_series if normalize(s.get("name", "")) == wanted]
    if len(same) > 1 and year:
        for s in same:
            if str(year) in (s.get("name", "") + s.get("url", "")):
                return s
    return same[0] if same else {}


def progress(volume: Dict[str, Any], series: Dict[str, Any]) -> Dict[str, Any]:
    "The reading state of one volume, given its Komga series."
    total = int(series.get("booksCount") or 0)
    read = int(series.get("booksReadCount") or 0)
    unread = int(series.get("booksUnreadCount") or 0) \
        + int(series.get("booksInProgressCount") or 0)
    return {**volume, "komga_books": total, "read": read, "unread": unread,
            "caught_up": total > 0 and read > 0 and unread == 0}


def fetch_series() -> List[Dict[str, Any]]:
    "All series of Komga, or [] if it is not set up or does not answer."
    from os import environ

    from requests import get

    auth = notifications.komga_auth()
    if auth is None:
        return []
    base = environ["KAPOWARR_KOMGA_URL"].strip().rstrip("/")
    out: List[Dict[str, Any]] = []
    try:
        page = 0
        while True:
            body = get(f"{base}/api/v1/series", params={"page": page, "size": 200},
                       timeout=20, **auth).json()
            out.extend(body.get("content", []))
            page += 1
            if body.get("last", True) or page > 50:
                break
    except Exception:
        return []
    return out


def overview() -> List[Dict[str, Any]]:
    "Reading progress for every library volume that Komga also has."
    from backend.internals.db import get_db

    series = fetch_series()
    if not series:
        return []
    volumes = get_db().execute("""
        SELECT v.id, v.title, v.year, v.monitored,
            (SELECT COUNT(*) FROM issues i WHERE i.volume_id = v.id AND i.monitored
                AND NOT EXISTS (SELECT 1 FROM issues_files f WHERE f.issue_id = i.id))
        FROM volumes v;""").fetchall()
    out = []
    for vid, title, year, monitored, missing in volumes:
        match = match_series(title, year, series)
        if match:
            out.append(progress({"volume_id": vid, "title": title, "year": year,
                                 "monitored": bool(monitored),
                                 "missing_monitored": missing}, match))
    return out


def search_caught_up() -> List[int]:
    "Start a search for each caught-up, monitored volume that has gaps."
    from backend.features.tasks import AutoSearchVolume, TaskHandler

    started = []
    for row in overview():
        if row["caught_up"] and row["monitored"] and row["missing_monitored"]:
            TaskHandler().add(AutoSearchVolume(row["volume_id"]))
            started.append(row["volume_id"])
    return started
