# -*- coding: utf-8 -*-

import re
from asyncio import Semaphore, gather
from datetime import datetime
from typing import Any, Dict, List, Union
from urllib.parse import quote

from requests import RequestException

from backend.base.custom_exceptions import ClientNotWorking
from backend.base.definitions import (BrokenClientReason, DownloadType,
                                      IndexerClientField as ICF, QueryResult,
                                      SearchQuery, SearchResultData)
from backend.base.file_extraction import extract_filename_data
from backend.base.helpers import AsyncSession, Session
from backend.base.logging import LOGGER
from backend.implementations.indexer_client_manager import (BaseIndexerClient,
                                                            IndexerClients)

SEARCH_PATH = "/advancedsearch.php"
METADATA_PATH = "/metadata/{}"
DOWNLOAD_PATH = "/download/{}/{}"
SUPPORTED_EXTENSIONS = (".cbz", ".cbr", ".zip", ".pdf", ".epub")
MAX_ITEMS_TO_EXPAND = 10
MAX_CONCURRENT_METADATA_FETCHES = 3

_DERIVATIVE = re.compile(r"_(jp2|text|hocr|chocr|djvu|meta|files)(\.|$)", re.I)
"Files archive.org makes itself from the scan (page images, text, OCR): not comics to read"

_LUCENE_SPECIAL = set('+-&|!(){}[]^"~*?:\\/')


def escape_query(query: str) -> str:
    """Make a title safe to put inside an archive.org search expression.
    Titles like "Batman: Year One" or "Saga (2012)" hold characters that the
    search syntax would otherwise read as operators and break the query.

    Args:
        query (str): The title to search for.

    Returns:
        str: The title, with every special character escaped.
    """
    return ''.join(
        f'\\{c}' if c in _LUCENE_SPECIAL else c
        for c in query.strip()
    )


def files_to_results(
    base_url: str,
    identifier: str,
    metadata: Any,
    indexer_id: int,
    indexer_title: str
) -> List[SearchResultData]:
    """The downloadable comic files in the metadata of one archive.org item.
    Odd metadata is skipped instead of raising.
    """
    files = metadata.get('files', []) if isinstance(metadata, dict) else []
    results: List[SearchResultData] = []
    for file in files if isinstance(files, list) else []:
        name = file.get('name') if isinstance(file, dict) else None
        if not isinstance(name, str) or not name.lower().endswith(
            SUPPORTED_EXTENSIONS
        ):
            continue

        stem = name.rsplit('/', 1)[-1]
        file_format = file.get('format')
        if _DERIVATIVE.search(stem) or (
            isinstance(file_format, str) and 'jp2' in file_format.lower()
        ):
            continue

        file_title = name.rsplit('/', 1)[-1].rsplit('.', 1)[0]
        size = file.get('size')
        results.append({
            **extract_filename_data(
                file_title,
                assume_volume_number=False,
                fix_year=True
            ),
            "link": base_url + DOWNLOAD_PATH.format(identifier, quote(name)),
            "display_title": file_title,
            "size": int(size) if isinstance(size, str) and size.isdigit() else -1,
            "indexer_id": indexer_id,
            "indexer_title": indexer_title,
            "seeders": None,
            "leechers": None
        })
    return results


@IndexerClients.register_client(
    DownloadType.DDL, 'Internet Archive',
    (ICF.TITLE, ICF.ENABLED, ICF.URL),
    allow_multiple_instances=False
)
class InternetArchiveIndexer(BaseIndexerClient):
    """Finds public domain and archived comics on archive.org. The files
    are direct downloads."""

    def __init__(self, indexer_id: int) -> None:
        super().__init__(indexer_id)

        self.session: Union[AsyncSession, None] = None
        return

    async def __get_json(self, path: str, params: Any = None) -> Any:
        if not self.session:
            self.session = AsyncSession()
        try:
            response = await self.session.get(
                self._url + path, params=params
            )
            if not response.ok:
                LOGGER.warning(
                    "Internet Archive request failed with status %d",
                    response.status
                )
                return None
            return await response.json()
        except Exception:
            LOGGER.exception("Failed to reach the Internet Archive")
            return None

    async def search(self, query: SearchQuery) -> QueryResult:
        data = await self.__get_json(SEARCH_PATH, [
            ("q", f"collection:comics AND title:({escape_query(query['query'])})"),
            ("fl[]", "identifier"),
            ("fl[]", "title"),
            ("rows", str(MAX_ITEMS_TO_EXPAND)),
            ("output", "json")
        ])

        docs = (
            data.get('response', {}).get('docs', [])
            if isinstance(data, dict) and isinstance(data.get('response'), dict)
            else []
        )
        identifiers = [
            doc['identifier']
            for doc in docs
            if isinstance(doc, dict)
            and isinstance(doc.get('identifier'), str)
            and doc['identifier']
        ]

        semaphore = Semaphore(MAX_CONCURRENT_METADATA_FETCHES)

        async def expand(identifier: str) -> List[SearchResultData]:
            async with semaphore:
                metadata = await self.__get_json(
                    METADATA_PATH.format(identifier)
                )
            return files_to_results(
                self._url, identifier, metadata, self._id, self._title
            )

        # One item that fails must not throw away the files of all the others
        per_item = await gather(
            *(expand(i) for i in identifiers),
            return_exceptions=True
        )
        return QueryResult(
            [
                result
                for results in per_item
                if isinstance(results, list)
                for result in results
            ],
            next_page_available=False
        )

    async def discover(self, last_check: datetime) -> List[SearchResultData]:
        # archive.org has no feed of new comics worth following
        return []

    async def shutdown(self) -> None:
        if self.session:
            await self.session.close()
        return

    @classmethod
    def test(cls, url: str, **extra_fields: Any) -> None:
        with Session() as session:
            try:
                response = session.get(f"{url}{SEARCH_PATH}", params={
                    "q": "collection:comics", "rows": "1", "output": "json"
                })
                if not response.ok:
                    raise ClientNotWorking(BrokenClientReason.CONNECTION_ERROR)
                if "response" not in response.json():
                    raise ClientNotWorking(
                        BrokenClientReason.NOT_CLIENT_INSTANCE
                    )
            except RequestException:
                raise ClientNotWorking(BrokenClientReason.CONNECTION_ERROR)
            except ValueError:
                raise ClientNotWorking(BrokenClientReason.NOT_CLIENT_INSTANCE)
        return
