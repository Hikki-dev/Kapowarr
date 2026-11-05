# -*- coding: utf-8 -*-

"""The endpoints of the extra features: /api/extras/..."""

from datetime import date
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


def _day_arg(name: str, default: date) -> date:
    try:
        return releases.parse_day(request.args.get(name), default)
    except ValueError:
        raise InvalidKeyValue(name, request.args.get(name))


@extras.route('/extras/calendar', methods=['GET'])
@error_handler
@auth
def api_calendar():
    "One period of the calendar. `view` is day, week, month or year; `date` is any day in it; `today` is the caller's own date."
    view = request.args.get('view', 'week')
    if view not in releases.VIEWS:
        raise InvalidKeyValue('view', view)
    today = _day_arg('today', date.today())
    anchor = _day_arg('date', today)
    return return_api(releases.calendar(view, anchor, today))


@extras.route('/extras/calendar/upcoming', methods=['GET'])
@error_handler
@auth
def api_calendar_upcoming():
    "What is still to come in the next few months (1 to 24)."
    try:
        months = int(request.args.get('months', 3))
    except ValueError:
        raise InvalidKeyValue('months', request.args.get('months'))
    return return_api(releases.upcoming(_day_arg('today', date.today()), months))


@extras.route('/extras/calendar/new', methods=['GET'])
@error_handler
@auth
def api_calendar_new():
    "New series that start in a period (not for the year view: too many questions to ComicVine)."
    view = request.args.get('view', 'week')
    if view not in ('day', 'week', 'month'):
        raise InvalidKeyValue('view', view)
    start, end = releases.view_bounds(view, _day_arg('date', _day_arg('today', date.today())))
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
        if kind not in ('series', 'publisher', 'keyword'):
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
