# -*- coding: utf-8 -*-

"""The endpoints of the extra features: /api/extras/..."""

from datetime import date, timedelta
from typing import Any

from flask import Blueprint, request

from backend.base.custom_exceptions import InvalidKeyValue, KeyNotFound
from backend.implementations.extras import (komga_sync, releases, requests_,
                                            upgrades)
from backend.implementations.extras.store import ensure_tables
from backend.internals.db import commit, get_db
from backend.internals.settings import Settings
from frontend.api import auth, error_handler, return_api

extras = Blueprint('extras', __name__)


def _body() -> dict:
    data: Any = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise InvalidKeyValue("body", data)
    return data


@extras.route('/extras/calendar', methods=['GET'])
@error_handler
@auth
def api_calendar():
    today = date.today()
    start, end = releases.week_bounds(today + timedelta(weeks=int(request.args.get('week', 0))))
    return return_api({"start": start.isoformat(), "end": end.isoformat(),
                       "releases": releases.library_releases(start, end)})


@extras.route('/extras/calendar/new', methods=['GET'])
@error_handler
@auth
def api_calendar_new():
    today = date.today()
    start, end = releases.week_bounds(today + timedelta(weeks=int(request.args.get('week', 0))))
    entries, source = releases.first_issues(start, end)
    return return_api({"start": start.isoformat(), "end": end.isoformat(),
                       "source": source, "series": entries})


@extras.route('/extras/watchlist', methods=['GET', 'POST', 'DELETE'])
@error_handler
@auth
def api_watchlist():
    ensure_tables()
    db = get_db()
    if request.method == 'POST':
        data = _body()
        kind, value = data.get('kind'), (data.get('value') or '').strip()
        if kind not in ('publisher', 'keyword'):
            raise InvalidKeyValue('kind', kind)
        if not value:
            raise KeyNotFound('value')
        db.execute("INSERT OR IGNORE INTO fork_watchlist(kind, value) VALUES (?, ?);", (kind, value))
        commit()
    elif request.method == 'DELETE':
        db.execute("DELETE FROM fork_watchlist WHERE id = ?;", (int(request.args.get('id', 0)),))
        commit()
    return return_api([{"id": r[0], "kind": r[1], "value": r[2]} for r in
                       db.execute("SELECT id, kind, value FROM fork_watchlist ORDER BY kind, value;")])


@extras.route('/extras/requests', methods=['GET', 'POST'])
@error_handler
@auth
def api_requests():
    if request.method == 'POST':
        data = _body()
        if not isinstance(data.get('comicvine_id'), int):
            raise InvalidKeyValue('comicvine_id', data.get('comicvine_id'))
        return return_api(requests_.request_series(
            str(data.get('requester') or ''), data['comicvine_id']), code=201)
    return return_api(requests_.list_requests())


@extras.route('/extras/upgrades', methods=['GET'])
@error_handler
@auth
def api_upgrades():
    preference = list(Settings().sv.format_preference)
    return return_api({"preference": preference,
                       "issues": upgrades.candidates(preference)})


@extras.route('/extras/upgrades/search', methods=['POST'])
@error_handler
@auth
def api_upgrades_search():
    from backend.features.search_full import manual_search

    data = _body()
    issue_id = data.get('issue_id')
    if not isinstance(issue_id, int):
        raise InvalidKeyValue('issue_id', issue_id)
    preference = list(Settings().sv.format_preference)
    candidate = next((c for c in upgrades.candidates(preference, 100000)
                      if c['issue_id'] == issue_id), None)
    if candidate is None:
        return return_api({"results": []})
    results = manual_search(candidate['volume_id'], issue_id)
    return return_api({"current": candidate['format'], "results": upgrades.better_results(
        [dict(r) for r in results], candidate['format'], preference)[:20]})


@extras.route('/extras/reading', methods=['GET'])
@error_handler
@auth
def api_reading():
    return return_api(komga_sync.overview())
