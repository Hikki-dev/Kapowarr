# -*- coding: utf-8 -*-

"""
Turning the links that indexers hand out into magnet links.

Indexers (Prowlarr, Torznab, ...) answer with a magnet link, with an HTTP link
that redirects to one, or with an HTTP link that serves the `.torrent` file
itself. The torrent client only gets magnet links, so all three are brought
to that form here.
"""

from hashlib import sha1
from typing import List, Optional
from urllib.parse import quote, urljoin

from bencoding import bdecode, bencode
from requests import RequestException

from backend.base.helpers import Session, build_magnet_link, get_torrent_info
from backend.base.logging import LOGGER

TORRENT_CONTENT_TYPES = (
    "application/x-bittorrent",
    "application/octet-stream",
    "binary/octet-stream"
)
MAX_TORRENT_FILE_SIZE = 10 * 1024 * 1024
"A real .torrent file is a few hundred KB at most; anything bigger is not one"
MAX_REDIRECTS = 5


def _trackers(torrent: bytes) -> List[str]:
    "The tracker addresses a torrent file lists itself, if any"
    try:
        meta = bdecode(torrent)
    except Exception:
        return []
    found: List[str] = []
    announce = meta.get(b"announce")
    if isinstance(announce, bytes):
        found.append(announce.decode(errors="replace"))
    for tier in meta.get(b"announce-list") or []:
        for url in tier if isinstance(tier, list) else [tier]:
            if isinstance(url, bytes):
                found.append(url.decode(errors="replace"))
    return [u for u in dict.fromkeys(found) if u.startswith(("http://", "https://", "udp://"))]


def torrent_file_to_magnet(content: bytes) -> Optional[str]:
    """Compute the magnet link of the contents of a torrent file.

    The torrent's own trackers are added to the usual list of trackers. A
    magnet link with no tracker cannot find its peers, so the torrent client
    could never start it.

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

    magnet = build_magnet_link(torrent_hash, name)
    own = [t for t in _trackers(content) if quote(t, safe="") not in magnet and t not in magnet]
    return magnet + "".join(f"&tr={quote(t, safe='')}" for t in own)


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
            # Redirects are followed by hand, a few at a time: one may lead to
            # the magnet link (which a web client would refuse to follow), and
            # others lead on to the server that really has the file.
            url = link
            for _ in range(MAX_REDIRECTS + 1):
                response = session.get(url, stream=True, allow_redirects=False)

                location = response.headers.get("Location", "")
                if location.startswith("magnet:?"):
                    return location
                if 300 <= response.status_code < 400 and location.startswith(
                    ("http://", "https://", "/")
                ):
                    url = urljoin(url, location)
                    continue
                break
            else:
                return None

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
