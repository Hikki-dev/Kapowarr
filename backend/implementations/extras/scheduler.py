# -*- coding: utf-8 -*-

"""Runs the extra features on a timer, in one quiet background thread."""

from datetime import date
from time import sleep

from backend.base.logging import LOGGER

KOMGA_EVERY = 30 * 60
FOLLOW_EVERY = 24 * 60 * 60


def _loop() -> None:
    from backend.implementations import notifications
    from backend.implementations.extras import komga_sync, releases

    waited = 0
    sleep(120)  # let the server finish starting
    while True:
        try:
            if notifications.komga_auth() is not None and waited % KOMGA_EVERY == 0:
                started = komga_sync.search_caught_up()
                if started:
                    LOGGER.info("Searching %d caught-up series", len(started))

            if waited % FOLLOW_EVERY == 0:
                start, end = releases.week_bounds(date.today())
                for entry in releases.follow_new_series(start, end):
                    notifications.notify("New series followed", entry["title"])
        except Exception:
            LOGGER.exception("A scheduled extra task failed")

        sleep(60)
        waited = (waited + 60) % FOLLOW_EVERY


def start() -> None:
    from backend.internals.server import Server

    thread = Server().get_db_thread(target=_loop, name="ExtrasThread")
    thread.daemon = True
    thread.start()
    return
