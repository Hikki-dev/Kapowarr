# Zipped downloads

Some sites give you a `.zip` or `.rar` with whole issues inside: for example `Kingdom Come 01 (of 04).cbr` up to `04`, or a few PDFs. Kapowarr now takes the issues out and files them in your library by itself.

## What happens

1. The download finishes and the archive is placed in the series folder.
2. Kapowarr looks inside. If it holds CBZ, CBR or PDF files, the issues are taken out. A plain CBZ or CBR (one comic) is left as it is.
3. The issues are put next to your other files, matched to their issue numbers and renamed the way you chose in Settings, Media Management.
4. Only then is the archive deleted.

The format of an issue never changes: a CBR stays a CBR, a PDF stays a PDF. This works on its own. You do not need to turn on **Convert/Extract Downloaded Files**, which is the switch that changes formats.

It is on by default (Settings, Media Management, **Extract archives containing issues**).

## The precautions

| Risk | What Kapowarr does |
|---|---|
| A file name that climbs out of the folder (`../../x`), an absolute path or a drive letter | The archive is refused before anything is written |
| A link inside the archive | The archive is refused |
| A password protected zip | The archive is refused and kept |
| A "zip bomb" (a small file that unpacks to something enormous) | Refused when it unpacks to more than 50 times its size, or more than 20 GB in all, or has more than 500 files. The sizes are also counted while writing, because an archive can lie about them |
| Not enough room on the drive | Refused unless the unpacked size fits with 1 GB to spare |
| Junk (`__MACOSX`, `._files`, `.DS_Store`, `Thumbs.db`, cover images, text files) | Never extracted, so nothing loose is dropped in your library |
| A half-finished extraction | Unpacked in a separate hidden folder first, and that folder is deleted if anything fails |
| A file with the same name already in your library | An identical file is kept once. A different one is saved as `Name (2)`. Nothing is overwritten |
| Nothing useful came out | The archive is **kept** and the reason is written to the log. The archive is deleted only when at least one issue made it into the library |
| An archive inside an archive | Taken out one level at a time, so it can never loop |

The limits can be changed with environment variables: `KAPOWARR_EXTRACT_MAX_GB` (default 20) and `KAPOWARR_EXTRACT_MAX_FILES` (default 500).

If something is refused, find "Not extracting" in the log (Status, then the log file). The archive stays where it is, so you can open it yourself.

## Already have a zip in your library?

Open the series and press **Preview Convert**. The zip is listed, and pressing the green button takes its issues out in the same careful way.
