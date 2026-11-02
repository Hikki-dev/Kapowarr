# -*- coding: utf-8 -*-

"""
Turning the links that indexers hand out into magnet links.

Indexers (Prowlarr, Torznab, ...) answer with a magnet link, with an HTTP link
that redirects to one, or with an HTTP link that serves the `.torrent` file
itself. The torrent client only gets magnet links, so all three are brought
to that form here.
"""

from hashlib import sha1
from typing import Optional
from urllib.parse import quote

from bencoding import bencode
from requests import RequestException

from backend.base.helpers import Session, get_torrent_info
from backend.base.logging import LOGGER

TORRENT_CONTENT_TYPES = (
    "application/x-bittorrent",
    "application/octet-stream",
    "binary/octet-stream"
)
MAX_TORRENT_FILE_SIZE = 10 * 1024 * 1024
"A real .torrent file is a few hundred KB at most; anything bigger is not one"


def torrent_file_to_magnet(content: bytes) -> Optional[str]:
    """Compute the magnet link of the contents of a torrent file.

    Args:
        content (bytes): The torrent file.

    Returns:
        Optional[str]: The magnet link (with the torrent's own name as `dn=`),
            or `None` if the content is not a valid torrent file.
    """
    try:
        info = get_torrent_info(content)
        torrent_hash = sha1(bencode(info)).hexdigest()
        name = info.get(b"name", b"").decode(errors="replace")
    except Exception:
        return None
    return f"magnet:?xt=urn:btih:{torrent_hash}&dn={quote(name)}"


def resolve_to_magnet(link: str) -> Optional[str]:
    """Bring a link from an indexer to a magnet link.

    Args:
        link (str): A magnet link, an HTTP link that redirects to one, or an
            HTTP link that serves a `.torrent` file.

    Returns:
        Optional[str]: The magnet link, or `None` if it can't be made.
    """
    if link.startswith("magnet:?"):
        return link

    try:
        with Session() as session:
            response = session.get(link, stream=True, allow_redirects=False)

            location = response.headers.get("Location", "")
            if location.startswith("magnet:?"):
                return location

            if not response.ok:
                return None

            content_type = (
                response.headers.get("Content-Type") or ""
            ).split(";")[0].strip().lower()
            if content_type not in TORRENT_CONTENT_TYPES:
                return None

            if int(response.headers.get("Content-Length") or 0) > MAX_TORRENT_FILE_SIZE:
                LOGGER.warning("Torrent file too large to be real: %s", link)
                return None

            # Never trust the announced size: stop reading when it is too big
            chunks = []
            size = 0
            for chunk in response.iter_content(64 * 1024):
                size += len(chunk)
                if size > MAX_TORRENT_FILE_SIZE:
                    LOGGER.warning("Torrent file too large to be real: %s", link)
                    return None
                chunks.append(chunk)

    except (RequestException, ValueError):
        LOGGER.exception("Failed to resolve torrent link: %s", link)
        return None

    return torrent_file_to_magnet(b"".join(chunks))
