# Safe downloads

Kapowarr only files comics. Before a finished download is moved into your library it is checked, and it is thrown away and blocklisted if it is not what it says.

## What is refused

| Case | Result |
|---|---|
| A program or script: `.exe`, `.bat`, `.cmd`, `.scr`, `.msi`, `.ps1`, `.vbs`, `.js`, `.jar`, `.sh`, `.apk`, `.lnk` and more, also behind a double name such as `comic.cbz.exe` | Refused |
| A file whose first bytes are a program (Windows, Linux, macOS or a `#!` script), whatever it is called | Refused |
| A `.cbz` that is not a zip, a `.cbr` that is not a rar, a `.pdf` that is not a PDF, a broken or empty file | Refused |
| A zip or rar with a program inside (`setup.exe` next to the pages) | Refused |
| A PDF that can launch programs, run JavaScript or hide embedded files | Refused |
| A link (symlink) instead of a file | Refused |
| A torrent with a stray `.exe` next to the issues | The issues are used. The program is left where it is and is never moved into the library |

Nothing is opened or run: only the first bytes and the list of names inside archives are read. The check is strict on purpose; a real comic does not trip it. The PDF check looks for the words in plain text, so it catches the usual cases and is not a virus scanner. For a full scan, run ClamAV on your downloads folder as well.

A refused download shows as failed in History, its link goes on the Blocklist with the reason **Unsafe file** (remove it there to allow that link again), its files are deleted from the download folder and you get a notification. With **Search again after a refused download** (Media Management, on by default) Kapowarr then looks for another release of the same issue, the way Sonarr and Radarr do after "blocklist and search".

## What is not changed

Archives with issues inside are still unpacked as described in [Zipped downloads](Zipped%20downloads.md), which already refuses paths that climb out of the folder, links, passwords, zip bombs and a full disk.
