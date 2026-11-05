# -*- coding: utf-8 -*-

import re
from datetime import datetime, timezone
from time import monotonic
from typing import Any, Dict, List, Tuple, Union

from aiohttp import ClientTimeout
from requests import RequestException

from backend.base.custom_exceptions import ClientNotWorking, CredentialInvalid
from backend.base.definitions import (BrokenClientReason, DownloadType,
                                      IndexerClientField as ICF, QueryResult,
                                      SearchQuery, SearchResultData)
from backend.base.file_extraction import extract_filename_data
from backend.base.helpers import AsyncSession, Session
from backend.base.logging import LOGGER
from backend.implementations.indexer_client_manager import (BaseIndexerClient,
                                                            IndexerClients)

SEARCH_TIMEOUT_SECONDS = 60
"Prowlarr asks every one of its indexers; a slow one should not cut the rest off"
COMICS_CATEGORY = 7030
MAX_RESULTS = 100
CACHE_SECONDS = 600
"The same search within ten minutes gets the same answer, without asking every site again"
CACHE_LIMIT = 200

STATS: Dict[str, float] = {
    "searches": 0, "cache_hits": 0, "fallback_searches": 0,
    "failures": 0, "last_seconds": 0.0, "results": 0
}
"What the metrics page shows about Prowlarr"

_cache: Dict[str, Tuple[float, Any]] = {}

_NOISE = re.compile(
    r"\(\s*(?:19|20)\d{2}\s*\)|#\s*\d+[\w.]*|\bv(?:ol(?:ume)?\.?)?\s*\d+\b|"
    r"\b(?:19|20)\d{2}\b",
    re.IGNORECASE
)


def looser_query(query: str) -> str:
    """The same search without the year, volume and issue number, for when
    the exact one finds nothing (sites often write "Batman 003" or "Batman
    v3 #3" in ways that never match the exact words).

    Returns:
        str: The looser query, or "" when it would not be any looser.
    """
    loose = " ".join(_NOISE.sub(" ", query).split())
    if loose and loose.lower() != query.lower().strip():
        return loose
    return ""


def parse_results(
    results: Any,
    indexer_id: int,
    indexer_title: str
) -> List[SearchResultData]:
    """Turn the answer of Prowlarr's search into search results. Odd answers
    and odd items are skipped, so one bad item never costs the others.

    Args:
        results (Any): The decoded JSON answer.
        indexer_id (int): The ID of this indexer.
        indexer_title (str): The title of this indexer.

    Returns:
        List[SearchResultData]: The torrent results.
    """
    if not isinstance(results, list):
        # An error answer is an object, not a list of results
        LOGGER.warning("Prowlarr answered with something unexpected")
        return []

    formatted: List[SearchResultData] = []
    for result in results:
        try:
            if (
                not isinstance(result, dict)
                or result.get("protocol") != "torrent"
            ):
                continue

            link = result.get("magnetUrl") or result.get("downloadUrl")
            title = result.get("title")
            if (
                not isinstance(link, str) or not link
                or not isinstance(title, str) or not title
            ):
                continue

            size = result.get("size")
            seeders = result.get("seeders")
            leechers = result.get("leechers")
            formatted.append({
                **extract_filename_data(
                    title,
                    assume_volume_number=False,
                    fix_year=True
                ),
                "link": link,
                "display_title": title,
                "size": size if isinstance(size, int) else -1,
                "indexer_id": indexer_id,
                "indexer_title": indexer_title,
                "seeders": seeders if isinstance(seeders, int) else None,
                "leechers": leechers if isinstance(leechers, int) else None
            })

        except Exception:
            # One odd result must not throw away all the others
            LOGGER.exception("Skipping a Prowlarr result that failed")

    return formatted


@IndexerClients.register_client(
    DownloadType.TORRENT, 'Prowlarr',
    (ICF.TITLE, ICF.ENABLED, ICF.URL, ICF.API_KEY),
    allow_multiple_instances=False
)
class ProwlarrIndexer(BaseIndexerClient):
    """Searches every torrent indexer of a Prowlarr in one request."""

    def __init__(self, indexer_id: int) -> None:
        super().__init__(indexer_id)

        self.session: Union[AsyncSession, None] = None
        return

    async def __request(self, params: Dict[str, Any]) -> Any:
        if not self.session:
            self.session = AsyncSession()

        try:
            response = await self.session.get(
                f"{self._url}/api/v1/search",
                params=params,
                # In a header, not in the URL, so the key never ends up in logs
                headers={"X-Api-Key": self._api_key or ""},
                timeout=ClientTimeout(total=SEARCH_TIMEOUT_SECONDS)
            )
            if not response.ok:
                LOGGER.warning(
                    "Prowlarr search request failed with status %d",
                    response.status
                )
                return None
            return await response.json()

        except Exception:
            LOGGER.exception("Failed to search Prowlarr")
            return None

    async def _cached_request(self, params: Dict[str, Any]) -> Any:
        "Ask Prowlarr, or reuse an answer from the last ten minutes."
        key = repr(sorted(params.items()))
        hit = _cache.get(key)
        if hit and monotonic() - hit[0] < CACHE_SECONDS:
            STATS["cache_hits"] += 1
            return hit[1]

        started = monotonic()
        answer = await self.__request(params)
        STATS["searches"] += 1
        STATS["last_seconds"] = round(monotonic() - started, 2)
        if answer is None:
            STATS["failures"] += 1
            return answer

        if len(_cache) >= CACHE_LIMIT:
            _cache.pop(next(iter(_cache)))
        _cache[key] = (monotonic(), answer)
        return answer

    async def search(self, query: SearchQuery) -> QueryResult:
        # Only the comics category: Prowlarr then asks the indexers that have
        # comics and answers in about ten seconds, with results that are about
        # comics. Searching every category takes over a minute per query and
        # mostly returns films and shows.
        params = {
            "query": query["query"],
            "type": "search",
            "categories": COMICS_CATEGORY,
            "limit": MAX_RESULTS
        }
        found = parse_results(
            await self._cached_request(params), self._id, self._title
        )
        if not found:
            loose = looser_query(query["query"])
            if loose:
                STATS["fallback_searches"] += 1
                found = parse_results(
                    await self._cached_request({**params, "query": loose}),
                    self._id, self._title
                )
        STATS["results"] += len(found)
        return QueryResult(found, next_page_available=False)

    async def discover(self, last_check: datetime) -> List[SearchResultData]:
        # An empty query gives the newest releases, like an RSS feed
        answer = await self.__request({
            "query": "",
            "type": "search",
            "categories": COMICS_CATEGORY,
            "limit": MAX_RESULTS
        })
        if answer is None or not isinstance(answer, list):
            return []

        recent = []
        for item in answer:
            published = item.get("publishDate") if isinstance(item, dict) else None
            try:
                when = datetime.fromisoformat(
                    str(published).replace("Z", "+00:00")
                ).astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                continue
            if when >= last_check:
                recent.append(item)
        return parse_results(recent, self._id, self._title)

    async def shutdown(self) -> None:
        if self.session:
            await self.session.close()
        return

    @classmethod
    def test(cls, url: str, **extra_fields: Any) -> None:
        api_key: str = extra_fields["api_key"]

        with Session() as session:
            try:
                response = session.get(
                    f"{url}/api/v1/system/status",
                    headers={"X-Api-Key": api_key}
                )
            except RequestException:
                raise ClientNotWorking(BrokenClientReason.CONNECTION_ERROR)

        if response.status_code in (401, 403):
            raise CredentialInvalid

        if not response.ok:
            raise ClientNotWorking(BrokenClientReason.CONNECTION_ERROR)

        try:
            if "version" not in response.json():
                raise ClientNotWorking(BrokenClientReason.NOT_CLIENT_INSTANCE)
        except ValueError:
            raise ClientNotWorking(BrokenClientReason.NOT_CLIENT_INSTANCE)
        return
