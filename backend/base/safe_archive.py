# -*- coding: utf-8 -*-

"""
Careful extraction of archives that hold whole issues (a zip or rar with
`.cbz`, `.cbr` or `.pdf` files inside).

An archive comes from the internet, so before anything is written the names,
sizes and kinds of its members are checked, and the extraction itself stays
inside the folder it was given. Nothing here deletes the original archive: the
caller does that only after the issues have been placed in the library.

Limits can be changed with environment variables:

* `KAPOWARR_EXTRACT_MAX_GB`: biggest total size to extract (default 20).
* `KAPOWARR_EXTRACT_MAX_FILES`: most issue files in one archive (default 500).
"""

from os import environ, makedirs, remove, walk
from os.path import commonpath, dirname, getsize, islink, join, realpath, splitext
from shutil import disk_usage
from stat import S_IFLNK, S_IFMT
from typing import Iterable, List, Tuple
from zipfile import ZipFile, ZipInfo

from backend.base.definitions import FileConstants
from backend.base.helpers import run_rar
from backend.base.logging import LOGGER

GB = 1024 ** 3
MAX_RATIO = 50
"Biggest allowed extracted size / archive size, for archives over 100 MB"
SPARE_BYTES = GB
"Free space that must stay free on the drive after extracting"
JUNK_NAMES = {".ds_store", "thumbs.db", "desktop.ini"}
JUNK_FOLDERS = {"__macosx"}
CONTAINERS = tuple(e.lower() for e in FileConstants.CONTAINER_EXTENSIONS)
CHUNK = 1024 * 1024


class UnsafeArchive(Exception):
    "The archive must not be extracted. The message says why."


def max_bytes() -> int:
    return int(float(environ.get("KAPOWARR_EXTRACT_MAX_GB", "20")) * GB)


def max_files() -> int:
    return int(environ.get("KAPOWARR_EXTRACT_MAX_FILES", "500"))


# region Names
def clean_member_name(name: str) -> List[str]:
    """Turn a name inside an archive into safe path parts.

    Raises:
        UnsafeArchive: The name is absolute, climbs out of the folder, has
            a drive letter or contains a null byte.
    """
    if "\x00" in name:
        raise UnsafeArchive(f"A file name has a null byte: {name!r}")

    unified = name.replace("\\", "/")
    if unified.startswith("/") or (len(unified) > 1 and unified[1] == ":"):
        raise UnsafeArchive(f"A file has an absolute path: {name!r}")

    parts = [p for p in unified.split("/") if p not in ("", ".")]
    if ".." in parts:
        raise UnsafeArchive(f"A file path climbs out of the folder: {name!r}")

    return parts


def is_junk(parts: Iterable[str]) -> bool:
    "macOS and Windows leftovers that are never part of a comic."
    parts = list(parts)
    if not parts:
        return True

    return (
        any(p.lower() in JUNK_FOLDERS for p in parts[:-1])
        or parts[-1].startswith("._")
        or parts[-1].lower() in JUNK_NAMES
    )


def is_issue_file(name: str) -> bool:
    return splitext(name)[1].lower() in CONTAINERS


def inside(folder: str, target: str) -> bool:
    "Whether `target` really lies in `folder`, after following links."
    folder = realpath(folder)
    try:
        return commonpath([folder, realpath(target)]) == folder
    except ValueError:
        return False


# region Checks
def check_free_space(folder: str, needed: int) -> None:
    makedirs(folder, exist_ok=True)
    free = disk_usage(folder).free
    if free < needed + SPARE_BYTES:
        raise UnsafeArchive(
            f"Not enough free space: {free // GB} GB free, "
            f"about {needed // GB + 1} GB needed"
        )


def check_zip(zf: ZipFile) -> Tuple[List[ZipInfo], int]:
    """Check a zip before anything is extracted.

    Returns:
        Tuple[List[ZipInfo], int]: The issue files to extract, and their total
            size in bytes.

    Raises:
        UnsafeArchive: The zip must not be extracted.
    """
    wanted: List[ZipInfo] = []
    total = 0
    compressed = 0
    for info in zf.infolist():
        parts = clean_member_name(info.filename)
        if info.is_dir() or is_junk(parts):
            continue

        if info.flag_bits & 0x1:
            raise UnsafeArchive("The archive is password protected")

        if S_IFMT(info.external_attr >> 16) == S_IFLNK:
            raise UnsafeArchive(f"The archive has a link: {info.filename!r}")

        if not is_issue_file(parts[-1]):
            continue

        wanted.append(info)
        total += info.file_size
        compressed += info.compress_size

    if not wanted:
        raise UnsafeArchive("There are no issue files inside")

    if len(wanted) > max_files():
        raise UnsafeArchive(
            f"Too many files inside ({len(wanted)}, the limit is {max_files()})"
        )

    if total > max_bytes():
        raise UnsafeArchive(
            f"Too big when extracted ({total // GB} GB, "
            f"the limit is {max_bytes() // GB} GB)"
        )

    if (
        total > 100 * 1024 * 1024
        and compressed
        and total / compressed > MAX_RATIO
    ):
        raise UnsafeArchive(
            "The archive is suspiciously compressed (a possible zip bomb)"
        )

    return wanted, total


# region Extraction
def extract_zip(archive: str, folder: str) -> List[str]:
    """Extract the issue files of a zip into `folder`, keeping their folder
    structure. Everything else in the archive is skipped.

    On an error some files may already be in `folder`, so the caller should
    delete `folder` then.

    Raises:
        UnsafeArchive: The archive must not be extracted.
        zipfile.BadZipFile: The file is not a readable zip.

    Returns:
        List[str]: The filepaths of the extracted files.
    """
    extracted: List[str] = []
    with ZipFile(archive, "r") as zf:
        wanted, total = check_zip(zf)
        check_free_space(folder, total)

        written_total = 0
        for info in wanted:
            target = join(folder, *clean_member_name(info.filename))
            if not inside(folder, target):
                raise UnsafeArchive(
                    f"A file would land outside the folder: {info.filename!r}"
                )

            makedirs(dirname(target), exist_ok=True)
            written = 0
            with zf.open(info, "r") as source, open(target, "wb") as dest:
                for chunk in iter(lambda: source.read(CHUNK), b""):
                    written += len(chunk)
                    written_total += len(chunk)
                    # The sizes in the header can lie, so count what comes out
                    if (
                        written > info.file_size + CHUNK
                        or written_total > max_bytes()
                    ):
                        raise UnsafeArchive(
                            f"{info.filename!r} is bigger than the archive says"
                        )
                    dest.write(chunk)

            extracted.append(target)

    return extracted


def check_rar(archive: str) -> int:
    """List a rar and check the names before it is extracted.

    Returns:
        int: How many issue files it holds.

    Raises:
        UnsafeArchive: The rar must not be extracted.
    """
    listing = run_rar(["lb", archive])
    if listing.returncode != 0:
        raise UnsafeArchive("The rar file cannot be read")

    issues = 0
    for name in (n for n in listing.stdout.split("\n") if n.strip()):
        parts = clean_member_name(name)
        if not is_junk(parts) and is_issue_file(parts[-1]):
            issues += 1

    if not issues:
        raise UnsafeArchive("There are no issue files inside")

    if issues > max_files():
        raise UnsafeArchive(f"Too many files inside ({issues})")

    return issues


def extract_rar(archive: str, folder: str) -> List[str]:
    """Extract a rar into `folder` and keep only the issue files.

    Raises:
        UnsafeArchive: The archive must not be extracted, or what came out
            was not what it should be.

    Returns:
        List[str]: The issue files that were extracted.
    """
    check_rar(archive)
    check_free_space(folder, getsize(archive) * 2)

    result = run_rar(["x", "-inul", "-y", archive, folder])
    if result.returncode != 0:
        raise UnsafeArchive(f"Extracting failed (code {result.returncode})")

    return prune_to_issue_files(folder)


def prune_to_issue_files(folder: str) -> List[str]:
    """Delete everything in `folder` that is not an issue file: links, junk,
    loose images and metadata. Refuses an extraction that grew too big.

    Returns:
        List[str]: The issue files that are left.

    Raises:
        UnsafeArchive: What is left is too big, too many, or nothing.
    """
    kept: List[str] = []
    total = 0
    for root, dirs, files in walk(folder):
        for name in list(dirs):
            if islink(join(root, name)):
                remove(join(root, name))  # A linked folder could lead outside
                dirs.remove(name)

        for name in files:
            path = join(root, name)
            if (
                islink(path)
                or not inside(folder, path)
                or is_junk([name])
                or not is_issue_file(name)
            ):
                remove(path)
                continue

            total += getsize(path)
            kept.append(path)

    if not kept:
        raise UnsafeArchive("There are no issue files inside")

    if total > max_bytes():
        raise UnsafeArchive("What was extracted is bigger than the limit")

    if len(kept) > max_files():
        raise UnsafeArchive("What was extracted has too many files")

    LOGGER.debug(f"Kept {len(kept)} issue files from the extraction")
    return kept
