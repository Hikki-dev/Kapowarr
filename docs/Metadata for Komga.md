# Metadata for Komga

Sonarr and Radarr give Plex and Jellyfin everything they need to show the right title, season, summary and poster. Kapowarr now does the same for comics, for Komga and Kavita.

## What is written

| Where | What |
|---|---|
| Inside every **CBZ** | A `ComicInfo.xml` with the series, issue number, volume, issue title, summary, release date, publisher and the ComicVine link. Komga uses it to order and name every issue |
| In the series folder | A `cover.jpg` (the ComicVine cover) and a `series.json` (Mylar format) with the series name, summary, publisher and status. Komga uses them for the series page and its cover |

Nothing that is there already is replaced. If a CBZ has a `ComicInfo.xml` from another tool, its extra details (writers, artists, characters) are kept and the ComicVine details are put on top, under the proper field names. If it cannot be read, it is left alone. A CBZ is rewritten through a temporary file, so a crash leaves the original, and the file date is kept. CBR and PDF files cannot be changed without converting them, so Komga matches those by their file name.

## When

* After every download, as the last step.
* On every **Refresh & Scan** of a series (and **Update All**), so a library you already have is filled in by itself.

Switch it off under Settings, Media Management, **Write metadata for Komga**.

## File names

The default naming (`Series (2024) Volume 01 Issue 001`) is already one Komga reads well, and with ComicInfo inside, Komga no longer depends on the name at all. Change the naming under Media Management and press **Preview Rename** on a series to see the result before anything moves.
