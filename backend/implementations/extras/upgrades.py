# -*- coding: utf-8 -*-

"""
Quality upgrades: find issues whose file is of a less wanted format than the
format preference says, and pick better results for them.

The format preference is the one in Settings, Media Management (for example
`cbz,cbr,pdf`: cbz is wanted most). Removing the old file after the better one
has arrived is off unless `KAPOWARR_UPGRADE_REMOVE_OLD=1` is set.
"""

from os import environ
from os.path import splitext
from re import findall
from typing import Any, Dict, List, Sequence

KNOWN = ("cbz", "cbr", "cb7", "pdf", "epub", "zip", "rar", "7z")


def format_rank(extension: str, preference: Sequence[str]) -> int:
    """How wanted a format is: 0 is the best. A format not in the list
    ranks after all of those that are."""
    extension = extension.lower().lstrip(".")
    preference = [p.lower() for p in preference]
    return preference.index(extension) if extension in preference \
        else len(preference)


def result_format(result: Dict[str, Any]) -> str:
    "The format a search result seems to be in ('' when it does not say)."
    for text in (result.get("display_title") or "", result.get("link") or ""):
        ext = splitext(text.split("?")[0])[1].lstrip(".").lower()
        if ext in KNOWN:
            return ext
        words = findall(r"[a-z0-9]+", text.lower())
        for word in words:
            if word in KNOWN:
                return word
    return ""


def is_upgrade(
    result: Dict[str, Any], current_format: str, preference: Sequence[str]
) -> bool:
    "Whether a result is in a more wanted format than what we have."
    found = result_format(result)
    return bool(found) and format_rank(found, preference) \
        < format_rank(current_format, preference)


def better_results(
    results: Sequence[Dict[str, Any]], current_format: str,
    preference: Sequence[str]
) -> List[Dict[str, Any]]:
    return [r for r in results if is_upgrade(r, current_format, preference)]


def candidates(preference: Sequence[str], limit: int = 200) -> List[Dict[str, Any]]:
    "Issues whose best file is less wanted than the preference's first format."
    from backend.internals.db import get_db

    if not preference:
        return []
    rows = get_db().execute("""
        SELECT i.id, i.volume_id, v.title, i.issue_number, f.filepath
        FROM issues i
        INNER JOIN volumes v ON v.id = i.volume_id
        INNER JOIN issues_files isf ON isf.issue_id = i.id
        INNER JOIN files f ON f.id = isf.file_id
        ORDER BY v.title, i.calculated_issue_number;
        """).fetchall()

    best: Dict[int, Dict[str, Any]] = {}
    for issue_id, volume_id, title, number, path in rows:
        ext = splitext(path)[1].lstrip(".").lower()
        rank = format_rank(ext, preference)
        known = best.get(issue_id)
        if known is None or rank < known["rank"]:
            best[issue_id] = {"issue_id": issue_id, "volume_id": volume_id,
                              "volume_title": title, "issue_number": number,
                              "format": ext, "rank": rank}
    return [c for c in best.values() if c["rank"] > 0][:limit]


def remove_old_enabled() -> bool:
    return environ.get("KAPOWARR_UPGRADE_REMOVE_OLD", "0").strip().lower() \
        in ("1", "true", "yes")


def remove_superseded(issue_id: int, preference: Sequence[str]) -> int:
    """Delete the files of an issue that rank below its best file, but only
    when the best file is in the preference list and removing is switched on.

    Returns:
        int: How many files were deleted.
    """
    if not remove_old_enabled() or not preference:
        return 0
    from backend.implementations.volumes import delete_issue_file
    from backend.internals.db import get_db

    rows = get_db().execute("""
        SELECT f.id, f.filepath FROM files f
        INNER JOIN issues_files isf ON isf.file_id = f.id
        WHERE isf.issue_id = ?;""", (issue_id,)).fetchall()
    ranked = [(format_rank(splitext(p)[1], preference), fid) for fid, p in rows]
    if len(ranked) < 2:
        return 0
    best = min(r for r, _ in ranked)
    if best >= len(preference):
        return 0
    old = [fid for r, fid in ranked if r > best]
    for fid in old:
        delete_issue_file(fid)
    return len(old)
