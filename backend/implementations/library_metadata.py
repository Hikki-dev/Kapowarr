# -*- coding: utf-8 -*-

"""
Give Komga (and Kavita, Mylar-style readers) the metadata it needs, the way
Sonarr and Radarr do for video.

* Every CBZ gets a `ComicInfo.xml` (series, issue number, volume, title,
  summary, release date, publisher, link), built from what ComicVine told
  Kapowarr. A file that already has a ComicInfo.xml from someone else is left
  alone. CBR and PDF files cannot be changed without converting them, so they
  are matched by their file name.
* The series folder gets a `series.json` (Mylar format, which Komga reads for
  the series title, summary, publisher, status and age rating) and a cover.

Nothing is ever overwritten that is not ours, a CBZ is rewritten through a
temporary file (so a crash leaves the original), and the file date is kept.
"""

from html import unescape
from copy import copy
from json import dumps
from os import remove, replace, stat, utime
from os.path import basename, dirname, exists, getsize, isdir, join, relpath, splitext
from re import sub
from shutil import disk_usage
from typing import Dict, List, Optional, Union
from xml.etree.ElementTree import Element, SubElement, tostring
from zipfile import BadZipFile, ZipFile, is_zipfile

from backend.base.definitions import IssueData, VolumeData
from backend.base.logging import LOGGER

MARKER = 'Tagged by Kapowarr'
SPARE_BYTES = 1024 ** 3
COVER_NAMES = ('cover.jpg', 'cover.jpeg', 'cover.png', 'cover.webp')
MAX_SUMMARY = 4000


def plain_text(html: Union[str, None]) -> str:
    "Turn the HTML of a ComicVine description into plain text."
    if not html:
        return ''

    text = sub(r'(?i)<\s*br\s*/?>|</p>|</li>|</h\d>', '\n', html)
    text = sub(r'<[^>]+>', '', text)
    text = unescape(text)
    text = sub(r'[ \t]+', ' ', text)
    text = sub(r'\n\s*\n+', '\n\n', text).strip()
    return text[:MAX_SUMMARY]


def comicinfo_xml(
    vd: VolumeData,
    issue: Optional[IssueData],
    total_issues: int = 0
) -> bytes:
    """Build the ComicInfo.xml for one issue.

    Args:
        vd (VolumeData): The series.
        issue (Optional[IssueData]): The issue, or `None` for a file that is
            not matched to one.
        total_issues (int, optional): How many issues the series has.

    Returns:
        bytes: The XML document.
    """
    root = Element('ComicInfo')
    values: Dict[str, str] = {
        'Series': vd.title,
        'Volume': str(vd.volume_number) if vd.volume_number else '',
        'Count': str(total_issues) if total_issues else '',
        'Publisher': vd.publisher or '',
        'Web': vd.site_url or '',
        'LanguageISO': 'en',
        'Manga': 'No',
        'Notes': f'{MARKER}, ComicVine volume {vd.comicvine_id}'
    }
    if issue is not None:
        values['Number'] = issue.issue_number
        values['Title'] = issue.title or ''
        values['Summary'] = plain_text(issue.description) \
            or plain_text(vd.description)

        if issue.date and len(issue.date) >= 4 and issue.date[:4].isdigit():
            parts = issue.date.split('-')
            values['Year'] = str(int(parts[0]))
            if len(parts) > 1 and parts[1].isdigit():
                values['Month'] = str(int(parts[1]))
            if len(parts) > 2 and parts[2][:2].isdigit():
                values['Day'] = str(int(parts[2][:2]))
    else:
        values['Summary'] = plain_text(vd.description)
        if vd.year:
            values['Year'] = str(vd.year)

    for key, value in values.items():
        if value != '':
            SubElement(root, key).text = value

    return b'<?xml version="1.0" encoding="utf-8"?>\n' + tostring(root, 'utf-8')


def series_json(vd: VolumeData, total_issues: int, cover_name: str) -> bytes:
    "The Mylar `series.json` that Komga reads."
    description = plain_text(vd.description)
    doc = {
        'version': '1.0.2',
        'metadata': {
            'type': 'comicSeries',
            'publisher': vd.publisher or '',
            'imprint': None,
            'name': vd.title,
            'comicid': vd.comicvine_id,
            'year': vd.year,
            'description_text': description,
            'description_formatted': None,
            'volume': vd.volume_number,
            'booktype': 'Print',
            'age_rating': None,
            'collects': [],
            'comic_image': cover_name,
            'total_issues': total_issues,
            'publication_run': str(vd.year) if vd.year else '',
            'status': 'Continuing'
        }
    }
    return dumps(doc, indent=2, ensure_ascii=False).encode('utf-8')


# region CBZ
def _has_comicinfo(names: List[str]) -> Optional[str]:
    for name in names:
        if basename(name).lower() == 'comicinfo.xml':
            return name

    return None


def embed_comicinfo(cbz: str, xml: bytes) -> bool:
    """Put a ComicInfo.xml in a CBZ, if it has none of its own.

    The archive is copied to a temporary file with the new XML added and only
    then swapped in, so the original is never half-written. The copy needs free
    space for one comic. The date of the file is kept.

    Returns:
        bool: Whether the file was changed.
    """
    if splitext(cbz)[1].lower() != '.cbz' or not is_zipfile(cbz):
        return False

    tmp = join(dirname(cbz), f'.{basename(cbz)}.kapowarr-tmp')
    try:
        with ZipFile(cbz) as src:
            names = src.namelist()
            existing = _has_comicinfo(names)
            if existing is not None:
                current = src.read(existing)
                if MARKER.encode() not in current:
                    return False  # Someone else's metadata: respect it

                if current == xml:
                    return False  # Already up to date

            if disk_usage(dirname(cbz)).free < getsize(cbz) + SPARE_BYTES:
                LOGGER.warning(
                    f'Not enough free space to tag {basename(cbz)}; skipped'
                )
                return False

            old_stat = stat(cbz)
            with ZipFile(tmp, 'w') as dest:
                for info in src.infolist():
                    if existing is not None and info.filename == existing:
                        continue

                    with src.open(info) as s, dest.open(copy(info), 'w') as d:
                        while chunk := s.read(1024 * 1024):
                            d.write(chunk)

                dest.writestr('ComicInfo.xml', xml)

        with ZipFile(tmp) as check:
            if len(check.namelist()) != len(names) + (
                0 if existing is not None else 1
            ) or check.testzip() is not None:
                raise BadZipFile('The tagged copy did not check out')

        replace(tmp, cbz)
        utime(cbz, (old_stat.st_atime, old_stat.st_mtime))
        return True

    except (BadZipFile, OSError, RuntimeError, NotImplementedError) as e:
        LOGGER.warning(f'Could not tag {cbz}: {e}')
        return False

    finally:
        if exists(tmp):
            remove(tmp)


# region Series folder
def _image_name(data: bytes) -> Optional[str]:
    if data[:3] == b'\xff\xd8\xff':
        return 'cover.jpg'
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        return 'cover.png'
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        return 'cover.webp'
    return None


def write_series_files(
    series_folder: str,
    vd: VolumeData,
    cover: Optional[bytes],
    total_issues: int
) -> None:
    """Write `series.json` and the cover in the series folder, when they are
    not there yet. Existing files are never replaced.
    """
    if not isdir(series_folder):
        return

    cover_name = next(
        (n for n in COVER_NAMES if exists(join(series_folder, n))), ''
    )
    if not cover_name and cover:
        name = _image_name(cover)
        if name:
            with open(join(series_folder, name), 'wb') as f:
                f.write(cover)
            cover_name = name

    target = join(series_folder, 'series.json')
    if not exists(target):
        with open(target, 'wb') as f:
            f.write(series_json(vd, total_issues, cover_name))

    return


def series_folder_of(root_folder: str, volume_folder: str) -> str:
    """The folder Komga treats as the series: the first folder below the
    root folder.
    """
    first = relpath(volume_folder, root_folder).replace('\\', '/').split('/')[0]
    if first in ('', '.', '..'):
        return volume_folder

    return join(root_folder, first)


def mass_write_metadata(
    volume_id: int,
    filepath_filter: Union[List[str], None] = None
) -> int:
    """Tag the CBZ files of a volume and write the series files.

    Args:
        volume_id (int): The volume.
        filepath_filter (Union[List[str], None], optional): Only these files.

    Returns:
        int: How many files were changed.
    """
    from backend.implementations.root_folders import RootFolders
    from backend.implementations.volumes import Volume
    from backend.internals.settings import Settings

    if not Settings().sv.write_metadata:
        return 0

    volume = Volume(volume_id)
    vd = volume.get_data()
    issues = volume.get_issues()
    total = len(issues)

    changed = 0
    seen = set()
    for issue in issues:
        for file in issue.files:
            path = file['filepath']
            if path in seen:
                continue  # One file for several issues: the first one counts

            seen.add(path)
            if filepath_filter and path not in filepath_filter:
                continue

            if not exists(path):
                continue

            if embed_comicinfo(path, comicinfo_xml(vd, issue, total)):
                changed += 1

    try:
        cover = volume.get_cover().getvalue()
    except Exception:
        cover = None

    try:
        write_series_files(
            series_folder_of(RootFolders()[vd.root_folder], vd.folder),
            vd, cover, total
        )
    except OSError as e:
        LOGGER.warning(f'Could not write the series files for {vd.title}: {e}')

    if changed:
        LOGGER.info(f'Tagged {changed} files of {vd.title}')

    return changed
