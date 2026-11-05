# -*- coding: utf-8 -*-

"""
Requests: someone asks for a series, it is added and searched for, and the
request shows how far it got. Like Seerr, for comics.
"""

from time import time
from typing import Any, Dict, List

from backend.implementations.extras.store import ensure_tables
from backend.internals.db import commit, get_db


def status_of(issue_count: int, file_count: int, queued: int) -> str:
    """The words for how far a request got.

    Args:
        issue_count: issues the series has.
        file_count: issues that have a file.
        queued: downloads for the series that are waiting or running.
    """
    if issue_count and file_count >= issue_count:
        return "Complete"
    if queued:
        return "Downloading"
    if file_count:
        return "Partly there"
    return "Searching"


def request_series(
    requester: str, comicvine_id: int, volume_adder=None
) -> Dict[str, Any]:
    """Add a series because someone asked for it.

    Args:
        volume_adder: function(comicvine_id) -> volume_id; given for tests.
            By default the series goes in the first root folder, monitored,
            with a search.
    """
    from backend.implementations.extras.releases import _add_volume

    ensure_tables()
    db = get_db()
    existing = db.execute(
        "SELECT id, title, year FROM volumes WHERE comicvine_id = ? LIMIT 1;",
        (comicvine_id,)
    ).fetchone()
    if existing:
        volume_id, title, year = existing
    else:
        volume_id = (volume_adder or _add_volume)(comicvine_id)
        title, year = db.execute(
            "SELECT title, year FROM volumes WHERE id = ?;", (volume_id,)
        ).fetchone()

    cursor = db.execute(
        "INSERT INTO fork_requests(requester, comicvine_id, title, year, volume_id, created_at) VALUES (?,?,?,?,?,?);",
        (requester.strip()[:100], comicvine_id, title, year, volume_id, int(time()))
    )
    commit()
    return {"id": cursor.lastrowid, "title": title, "year": year,
            "volume_id": volume_id, "already_in_library": bool(existing)}


def list_requests() -> List[Dict[str, Any]]:
    ensure_tables()
    db = get_db()
    out = []
    for rid, who, cv, title, year, vid, at in db.execute(
        "SELECT id, requester, comicvine_id, title, year, volume_id, created_at FROM fork_requests ORDER BY id DESC LIMIT 200;"
    ).fetchall():
        issues = files = queued = 0
        if vid:
            issues = db.execute("SELECT COUNT(*) FROM issues WHERE volume_id = ?;", (vid,)).fetchone()[0]
            files = db.execute(
                "SELECT COUNT(DISTINCT f.issue_id) FROM issues_files f INNER JOIN issues i ON i.id = f.issue_id WHERE i.volume_id = ?;",
                (vid,)).fetchone()[0]
            queued = db.execute("SELECT COUNT(*) FROM download_queue WHERE volume_id = ?;", (vid,)).fetchone()[0]
        out.append({"id": rid, "requester": who, "comicvine_id": cv,
                    "title": title, "year": year, "volume_id": vid,
                    "created_at": at, "issues": issues, "downloaded": files,
                    "status": status_of(issues, files, queued)})
    return out
