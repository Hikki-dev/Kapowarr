# -*- coding: utf-8 -*-

"""
Tell other apps what happened, without any setting screen to fill in.

Set these environment variables on the container to switch a feature on:

* `KAPOWARR_NOTIFY_URL`: an ntfy topic URL, a Discord webhook URL, or any
  other URL (it then gets a JSON post with `title` and `message`).
  Sent when a comic is imported and when a download fails.
* `KAPOWARR_KOMGA_URL`: the address of Komga. A scan of its libraries is
  started after a comic is imported, so it shows up at once.
  Use `KAPOWARR_KOMGA_API_KEY`, or `KAPOWARR_KOMGA_USER` and
  `KAPOWARR_KOMGA_PASSWORD`, to sign in.

Nothing here may ever stop an import: every call runs in the background,
has a time limit, and swallows its own errors.
"""

from os import environ
from threading import Thread
from typing import Any, Callable, Dict, Optional, Tuple

from requests import post

from backend.base.logging import LOGGER

TIMEOUT = 10
COUNTERS: Dict[str, int] = {"notifications_sent": 0, "notifications_failed": 0,
                            "komga_scans": 0, "komga_scans_failed": 0}


def build_notification(
    url: str, title: str, message: str
) -> Tuple[str, Dict[str, Any]]:
    """Make the request for a URL: ntfy, Discord or a plain JSON webhook.

    Returns:
        Tuple[str, Dict[str, Any]]: The URL and the keyword arguments for
            `requests.post`.
    """
    if "discord.com/api/webhooks" in url or "discordapp.com/api/webhooks" in url:
        return url, {"json": {"content": f"**{title}**\n{message}"[:1900]}}

    if "/ntfy" in url or "ntfy." in url or "ntfy:" in url:
        return url, {
            "data": message.encode(),
            # headers must be latin-1; the body carries the real text
            "headers": {"Title": title.encode("ascii", "replace").decode()}
        }

    return url, {"json": {"title": title, "message": message}}


def _in_background(function: Callable[[], None]) -> None:
    def run() -> None:
        try:
            function()
        except Exception:
            LOGGER.exception("A notification step failed")

    Thread(target=run, daemon=True).start()


def notify(title: str, message: str) -> None:
    "Send a message to `KAPOWARR_NOTIFY_URL`, if it is set."
    url = environ.get("KAPOWARR_NOTIFY_URL", "").strip()
    if not url:
        return

    def send() -> None:
        target, kwargs = build_notification(url, title, message)
        try:
            response = post(target, timeout=TIMEOUT, **kwargs)
            ok = response.ok
        except Exception:
            ok = False
        COUNTERS["notifications_sent" if ok else "notifications_failed"] += 1
        if not ok:
            LOGGER.warning("The notification could not be sent")

    _in_background(send)
    return


def komga_auth() -> Optional[Dict[str, Any]]:
    "How to sign in to Komga, from the environment; None if not set up."
    if not environ.get("KAPOWARR_KOMGA_URL", "").strip():
        return None
    key = environ.get("KAPOWARR_KOMGA_API_KEY", "").strip()
    if key:
        return {"headers": {"X-API-Key": key}}
    user = environ.get("KAPOWARR_KOMGA_USER", "")
    if user:
        return {"auth": (user, environ.get("KAPOWARR_KOMGA_PASSWORD", ""))}
    return {}


def scan_komga() -> None:
    "Ask Komga to scan its libraries, if `KAPOWARR_KOMGA_URL` is set."
    auth = komga_auth()
    if auth is None:
        return
    base = environ["KAPOWARR_KOMGA_URL"].strip().rstrip("/")

    def scan() -> None:
        from requests import get
        try:
            libraries = get(
                f"{base}/api/v1/libraries", timeout=TIMEOUT, **auth
            ).json()
            for library in libraries:
                post(
                    f"{base}/api/v1/libraries/{library['id']}/scan",
                    timeout=TIMEOUT, **auth
                ).raise_for_status()
            COUNTERS["komga_scans"] += 1
        except Exception:
            COUNTERS["komga_scans_failed"] += 1
            LOGGER.warning("Komga could not be asked to scan")

    _in_background(scan)
    return


def imported(title: str) -> None:
    "A comic was imported: tell the user and have Komga look."
    notify("Comic imported", title)
    scan_komga()
    return


def failed(title: str) -> None:
    "A download failed: tell the user."
    notify("Download failed", title)
    return
