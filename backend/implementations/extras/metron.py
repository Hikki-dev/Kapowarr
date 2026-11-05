# -*- coding: utf-8 -*-

"""
Metron (metron.cloud) as a second source of comic data, used when ComicVine is
slow, blocked or out of requests.

Set `KAPOWARR_METRON_USER` and `KAPOWARR_METRON_PASSWORD` (a free account on
metron.cloud). Without them nothing here does anything.
"""

from datetime import date
from os import environ
from typing import Any, Dict, List

API = "https://metron.cloud/api"


def enabled() -> bool:
    return bool(environ.get("KAPOWARR_METRON_USER") and
                environ.get("KAPOWARR_METRON_PASSWORD"))


def parse_issues(body: Any) -> List[Dict[str, Any]]:
    """Turn the answer of Metron's issue list into new-series entries. Odd
    answers and odd items are skipped."""
    if not isinstance(body, dict) or not isinstance(body.get("results"), list):
        return []
    found = []
    for item in body["results"]:
        if not isinstance(item, dict):
            continue
        series = item.get("series")
        series = series if isinstance(series, dict) else {}
        publisher = item.get("publisher")
        publisher = publisher.get("name") if isinstance(publisher, dict) \
            else publisher
        name = series.get("name") or item.get("series_name")
        if not name or str(item.get("number")) != "1":
            continue
        found.append({
            # Metron's own IDs are not ComicVine's. A series' cv_id links them.
            "comicvine_id": series.get("cv_id") or None,
            "metron_id": item.get("id"),
            "series_id": series.get("id"),
            "title": name,
            "issue_number": "1",
            "store_date": item.get("store_date"),
            "publisher": publisher if isinstance(publisher, str) else None,
            "start_year": series.get("year_began")
        })
    return found


def first_issues(start: date, end: date) -> List[Dict[str, Any]]:
    "Number ones that go on sale between two dates. Empty on any failure."
    if not enabled():
        return []
    from requests import get
    try:
        response = get(
            f"{API}/issue/",
            params={"store_date_range_after": start.isoformat(),
                    "store_date_range_before": end.isoformat(),
                    "number": "1"},
            auth=(environ["KAPOWARR_METRON_USER"],
                  environ["KAPOWARR_METRON_PASSWORD"]),
            timeout=30
        )
        response.raise_for_status()
        found = parse_issues(response.json())
        for entry in found[:40]:
            if not entry["comicvine_id"] and entry.get("series_id"):
                detail = get(f"{API}/series/{entry['series_id']}/",
                             auth=(environ["KAPOWARR_METRON_USER"],
                                   environ["KAPOWARR_METRON_PASSWORD"]),
                             timeout=30).json()
                entry["comicvine_id"] = detail.get("cv_id") or None
        # Series without a ComicVine link cannot be added to Kapowarr
        return [e for e in found if e["comicvine_id"]]
    except Exception:
        return []
