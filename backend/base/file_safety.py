# -*- coding: utf-8 -*-

"""
Checks that a finished download is really a comic and not a program.

A download is only accepted into the library when:

* it is not an executable (Windows, Linux, macOS or a script), whatever its
  name says,
* its content matches its extension (a `.cbz` is a zip, a `.cbr` a rar, ...),
* an archive does not carry programs inside, and
* a PDF does not ask to launch anything.

Nothing here runs or opens the file. The first few bytes are read, and zip and
rar archives have their list of names read. The checks are on purpose strict:
a real comic never fails them, and a download that does is blocklisted and
deleted by the caller.
"""

from os import walk
from os.path import getsize, isdir, isfile, islink, join, splitext
from typing import List, Optional
from zipfile import BadZipFile, ZipFile

from backend.base.definitions import FileConstants
from backend.base.helpers import run_rar
from backend.base.logging import LOGGER

DANGEROUS_EXTENSIONS = frozenset((
    # Windows
    '.exe', '.dll', '.com', '.scr', '.pif', '.msi', '.msp', '.bat', '.cmd',
    '.vbs', '.vbe', '.js', '.jse', '.wsf', '.wsh', '.ps1', '.psm1', '.lnk',
    '.reg', '.cpl', '.hta', '.jar', '.gadget', '.appx', '.msix', '.sys',
    '.chm', '.application', '.library-ms', '.scf', '.url',
    # macOS / Linux / Android
    '.sh', '.bash', '.zsh', '.command', '.app', '.pkg', '.dmg', '.deb',
    '.rpm', '.apk', '.bin', '.run', '.so', '.dylib', '.elf', '.out',
    '.desktop', '.py', '.pl', '.rb', '.php', '.swf'
))
"Extensions of programs and scripts that are never part of a comic"

EXECUTABLE_SIGNATURES = (
    b'MZ',                      # Windows PE / DOS
    b'\x7fELF',                 # Linux
    b'#!',                      # Script
    b'\xfe\xed\xfa\xce', b'\xfe\xed\xfa\xcf',   # Mach-O
    b'\xce\xfa\xed\xfe', b'\xcf\xfa\xed\xfe',   # Mach-O (little endian)
    b'\xca\xfe\xba\xbe',        # Mach-O universal / Java class
    b'dex\n',                   # Android
    b'\x4c\x00\x00\x00\x01\x14\x02\x00',        # Windows shortcut
)
"The first bytes of programs"

ZIP_SIGNATURES = (b'PK\x03\x04', b'PK\x05\x06')
RAR_SIGNATURES = (b'Rar!\x1a\x07\x00', b'Rar!\x1a\x07\x01\x00')
SEVEN_ZIP_SIGNATURE = b"7z\xbc\xaf'\x1c"
GZIP_SIGNATURE = b'\x1f\x8b'

ZIP_EXTENSIONS = ('.cbz', '.zip', '.epub')
RAR_EXTENSIONS = ('.cbr', '.rar')
SEVEN_ZIP_EXTENSIONS = ('.cb7', '.7z', '.7zip')

PDF_RISKS = (b'/Launch', b'/JavaScript', b'/EmbeddedFile')
"PDF keywords that run code or programs"
PDF_SCAN_LIMIT = 64 * 1024 * 1024
"How much of a PDF is searched for risky keywords"
MAX_NAMES = 100_000
"Most names read from one archive"


class UnsafeFile(Exception):
    "The file must not enter the library. The message says why."


def _head(path: str, size: int = 16) -> bytes:
    with open(path, 'rb') as f:
        return f.read(size)


def _is_dangerous_name(name: str) -> bool:
    name = name.replace('\\', '/').rstrip('/')
    if not name:
        return False

    leaf = name.rsplit('/', 1)[-1].lower()
    if leaf in ('autorun.inf', 'desktop.ini'):
        return True

    # "photo.jpg.exe", "x.pdf.scr": the last extension counts, and so does a
    # program hidden behind a space or dot trick
    ext = splitext(leaf.rstrip(' .'))[1]
    return ext in DANGEROUS_EXTENSIONS


def check_names(names: List[str]) -> None:
    """Refuse a list of names from an archive that has a program in it.

    Raises:
        UnsafeFile: A name looks like a program.
    """
    for name in names[:MAX_NAMES]:
        if _is_dangerous_name(name):
            raise UnsafeFile(f'The archive has a program inside: {name!r}')

    if len(names) > MAX_NAMES:
        raise UnsafeFile('The archive has an unreasonable number of files')


def check_file(path: str) -> None:
    """Check one downloaded file.

    Files that are not comics or documents (images, metadata, ...) are not the
    concern of this function: only programs among them are refused.

    Raises:
        UnsafeFile: The file must not be accepted.
    """
    if islink(path):
        raise UnsafeFile('A link, not a file')

    if not isfile(path):
        return

    ext = splitext(path)[1].lower()
    if _is_dangerous_name(path):
        raise UnsafeFile(f'A program or script: {ext}')

    if getsize(path) == 0:
        raise UnsafeFile('The file is empty')

    head = _head(path)
    if head.startswith(EXECUTABLE_SIGNATURES):
        raise UnsafeFile('The content is a program, not a comic')

    if ext in ZIP_EXTENSIONS:
        if not head.startswith(ZIP_SIGNATURES):
            raise UnsafeFile(f'Not a zip file, but named {ext}')
        try:
            with ZipFile(path) as zf:
                check_names(zf.namelist())
        except BadZipFile:
            raise UnsafeFile('The zip file is broken')

    elif ext in RAR_EXTENSIONS:
        if not head.startswith(RAR_SIGNATURES):
            raise UnsafeFile(f'Not a rar file, but named {ext}')
        listing = run_rar(['lb', path])
        if listing.returncode != 0:
            raise UnsafeFile('The rar file cannot be read')
        check_names([n for n in listing.stdout.split('\n') if n.strip()])

    elif ext in SEVEN_ZIP_EXTENSIONS:
        if not head.startswith(SEVEN_ZIP_SIGNATURE):
            raise UnsafeFile(f'Not a 7z file, but named {ext}')

    elif ext == '.pdf':
        # The signature may sit a little after the start
        with open(path, 'rb') as f:
            first = f.read(1024)
            if b'%PDF-' not in first:
                raise UnsafeFile('Not a PDF, but named .pdf')

            f.seek(0)
            tail = b''
            read = 0
            while read < PDF_SCAN_LIMIT:
                chunk = f.read(1024 * 1024)
                if not chunk:
                    break
                read += len(chunk)
                block = tail + chunk
                for risk in PDF_RISKS:
                    if risk in block:
                        raise UnsafeFile(
                            f'The PDF can run code ({risk.decode()})'
                        )
                tail = block[-16:]

    elif ext in FileConstants.CONTAINER_EXTENSIONS:
        # Other containers (cbt, cba, mobi, tar.gz): they cannot be listed
        # here, so at least refuse the ones that are not what they say
        if ext in ('.gz', '.tar.gz') and not head.startswith(GZIP_SIGNATURE):
            raise UnsafeFile('Not a gzip file')


def problem_with(paths: List[str]) -> Optional[str]:
    """Check what a download left on disk.

    A folder (a torrent) is searched for issue files, and the issue files in it
    are checked. Other things in the folder never enter the library and are
    left alone, but a program among them is reported in the log.

    Args:
        paths (List[str]): The files and folders of the download.

    Returns:
        Optional[str]: The reason, or `None` when everything is fine.
    """
    for path in paths:
        try:
            if isdir(path):
                for root, dirs, files in walk(path):
                    for name in list(dirs):
                        if islink(join(root, name)):
                            dirs.remove(name)

                    for name in files:
                        full = join(root, name)
                        if _is_dangerous_name(name):
                            LOGGER.warning(
                                f'Ignoring a program in a download: {full}'
                            )
                        elif splitext(name)[1].lower() in (
                            FileConstants.CONTAINER_EXTENSIONS
                        ):
                            check_file(full)
            else:
                check_file(path)

        except UnsafeFile as e:
            return f'{path}: {e}'

        except OSError as e:
            return f'{path}: cannot be read ({e})'

    return None
