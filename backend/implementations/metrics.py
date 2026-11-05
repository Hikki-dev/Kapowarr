# -*- coding: utf-8 -*-

"""
Numbers for Homepage, Beszel, Prometheus or a quick look, in the plain-text
format those tools read. Served at `/api/system/metrics` (with the api key, like the
other endpoints).
"""

from typing import Dict, Iterable, Tuple


def render(values: Iterable[Tuple[str, str, float]]) -> str:
    """Make the text of the metrics page.

    Args:
        values (Iterable[Tuple[str, str, float]]): (name, help text, value).

    Returns:
        str: Lines of `name value`, each with its help text above it.
    """
    lines = []
    for name, help_text, value in values:
        lines.append(f"# HELP kapowarr_{name} {help_text}")
        lines.append(f"# TYPE kapowarr_{name} gauge")
        lines.append(f"kapowarr_{name} {value:g}")
    return "\n".join(lines) + "\n"


def collect() -> str:
    "Gather the numbers of this server and render them."
    from backend.implementations.indexer_clients.torrent.Prowlarr import STATS
    from backend.implementations.notifications import COUNTERS
    from backend.internals.db import get_db

    db = get_db()

    def count(sql: str) -> int:
        return db.execute(sql).fetchone()[0]

    numbers: Dict[str, Tuple[str, float]] = {
        "volumes": ("Series in the library",
                    count("SELECT COUNT(*) FROM volumes;")),
        "issues": ("Issues known",
                   count("SELECT COUNT(*) FROM issues;")),
        "issues_with_file": ("Issues that have a file",
                             count("SELECT COUNT(DISTINCT issue_id) FROM issues_files;")),
        "queue": ("Downloads waiting or running",
                  count("SELECT COUNT(*) FROM download_queue;")),
        "prowlarr_searches": ("Searches sent to Prowlarr", STATS["searches"]),
        "prowlarr_cache_hits": ("Searches answered from the cache", STATS["cache_hits"]),
        "prowlarr_fallback_searches": ("Looser searches after an empty answer", STATS["fallback_searches"]),
        "prowlarr_failures": ("Prowlarr searches that failed", STATS["failures"]),
        "prowlarr_last_search_seconds": ("Seconds the last Prowlarr search took", STATS["last_seconds"]),
        "prowlarr_results": ("Results Prowlarr gave", STATS["results"]),
        **{f"{k}": (k.replace("_", " ").capitalize(), v)
           for k, v in COUNTERS.items()},
    }
    return render((name, h, v) for name, (h, v) in numbers.items())
