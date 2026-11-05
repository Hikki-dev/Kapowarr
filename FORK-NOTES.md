# What this fork changes

Based on Casvt/Kapowarr, `development` branch of 2 November 2026 (version 1.3.2 plus unreleased work). Same GPL-3.0 licence. The history of the original is kept, so new work can be merged in.

What is changed:

1. `backend/implementations/indexer_clients/torrent/Prowlarr.py` (new) and `download_preppers/torrent/Prowlarr.py` (new): Prowlarr as an indexer. One search asks every torrent site set up in Prowlarr. It searches the comics category (7030) first, with a 60 second limit, keeps at most 100 results, skips anything that is not a torrent, and sends the API key in a header so it never shows in a log. A bad item never costs the others.
2. `backend/implementations/indexer_clients/ddl/InternetArchive.py` (new) and `download_preppers/ddl/InternetArchive.py` (new): the Internet Archive as an indexer for public domain and archived comics. It understands titles such as "Batman: Year One" and "Saga (2012)" and leaves out the page images and text files the archive makes by itself.
3. `backend/implementations/torrent_links.py` (new), `download_preppers/torrent/Torznab.py` and `download_clients/Torrent.py`: every kind of torrent link becomes a magnet link: a magnet link, a link that redirects to one (up to 5 redirects), or a link that serves the `.torrent` file itself, whatever it is called. A file over 10 MB is not a real torrent and is ignored. A tracker that answers oddly no longer stops the download from being added.
4. `backend/internals/db_migration.py`: a bridge for databases of the earlier version of this copy (version 46), step 52 (adds the Prowlarr and Internet Archive indexers and turns old Prowlarr settings into an indexer), and a guard in steps 38 and 39 so a database from the original 1.0.0 upgrades instead of stopping. The final database version is 53.
5. `backend/base/definitions.py`: the fields the new indexers need.
6. `Dockerfile`, `.dockerignore`, `docker-compose.yml`: one-stage image of about 170 MB for Intel/AMD and ARM, no compiling at install, `MALLOC_ARENA_MAX=2`, and a health check that passes when the web server accepts connections (it works with any URL base). Compose has a 512 MB memory limit and log rotation.
7. `.github/workflows/ci.yml` (replaces `tests.yml` and `deploy.yml`): runs the tests on every change and publishes the image only when they pass.
8. `.github/workflows/upstream-sync.yml` (new): the weekly merge of the original (see below).

9. `backend/features/search_full.py`: a torrent known to have no seeders ranks last, and between equal results more seeders ranks first.
10. `backend/implementations/indexer_clients/torrent/Prowlarr.py`: answers are remembered for ten minutes (200 searches at most), an empty answer is followed by one looser search (`looser_query`), and counters (`STATS`) feed the metrics page.
11. `backend/base/files.py`: `link_or_copy` and `copy_function_for_import`: a finished torrent is hard linked into the library and copied when that is not possible. `KAPOWARR_HARDLINK=0` always copies.
12. `backend/implementations/notifications.py` (new) and `backend/features/post_processing.py`: a message (ntfy, Discord or a JSON webhook) when a comic is imported or a download fails, and a Komga scan after an import. Environment variables only; every call runs in the background and can never stop an import.
13. `backend/implementations/metrics.py` (new) and `frontend/api.py`: `/api/system/metrics`, plain text for dashboards.

14. `backend/implementations/extras/` (new): `releases.py` (calendar, new series, watch list, follow), `requests_.py`, `upgrades.py`, `komga_sync.py`, `metron.py`, `store.py` (three small tables created with `IF NOT EXISTS`, so they take no migration number), `scheduler.py` (one daemon thread: Komga check every 30 minutes, new series every day).
15. `frontend/extras.py` (new) and `backend/internals/server.py`: the endpoints `/api/extras/...`. `frontend/ui.py`, `frontend/templates/extras.html`, `frontend/static/js/extras.js`, `frontend/static/css/extras.css` and one link in `base.html`: the Extras page. `Kapowarr.py` starts the scheduler. `backend/features/post_processing.py` removes a replaced file when `KAPOWARR_UPGRADE_REMOVE_OLD=1`.
16. `frontend/static/css/kapowarr.css` (new), `frontend/static/js/shell.js` (new) and `frontend/templates/base.html`: a new interface in the style of Sonarr and Radarr. Sidebar with sections, page titles with a plain hint, one icon set (`frontend/static/img` and `img/ui`, Material Symbols, Apache 2.0), Roboto only, a first-run setup card, "missing / Complete" on each cover, a Have / Missing / In the run summary on the series page, activity tabs and a tab bar on phones. `frontend/static/js/volumes.js` colours the progress bars green, amber or red; `frontend/ui.py` and `general.js` make dark the default; `frontend/static/css/extras.css` and `add_volume.html` (wording) follow. The palette is one set of colour variables for light and dark (`kapowarr.css`). Icons are inline SVG in the menu (`frontend/templates/icons`) so they render the same in Safari, Chrome and Firefox. See docs/Interface.md.

17. `backend/implementations/extras/releases.py` (`view_bounds`, `shift_anchor`, `grid_bounds`, `release_state`, `month_summary`, `upcoming`, `calendar`), `frontend/extras.py` (`/api/extras/calendar`, `/calendar/upcoming`, `/calendar/new`), `frontend/static/js/calendar.js` and `extras.html`: the calendar has Day, Week, Month and Year views and a Coming up list; checks in `tests/Tbackend/implementations/extras.py` cover leap years, month ends, year boundaries, bad dates and empty libraries.

Checks that run offline on every change, next to the original's own:
`tests/Tbackend/implementations/extras.py`, `improvements.py`, `prowlarr_indexer.py`, `internet_archive_indexer.py`, `torrent_links.py`, `tests/Tbackend/implementations/download_clients/torrent_name.py` and `tests/Tbackend/internals/db_migration_fork.py`.

Image: `ghcr.io/hikki-dev/kapowarr-fork:latest` (amd64 and arm64), built by `.github/workflows/ci.yml`. It has its own name so the package is linked to this fork and is public. Run it like the original image:

    docker run -d --name kapowarr --restart unless-stopped -p 5656:5656 -e PUID=1000 -e PGID=1000 -v kapowarr-db:/app/db -v /path/downloads:/app/temp_downloads -v /path/comics:/comics-1 ghcr.io/hikki-dev/kapowarr-fork:latest

From the original Kapowarr image, or from the earlier version of this copy: back up the database volume and start this image on the same volumes. The database is upgraded on the first start. Databases made by the original versions 1.0.0, 1.1.0, 1.2.0, 1.3.0, 1.3.1 and 1.3.2 were each upgraded this way.

Keeping up with the original: `.github/workflows/upstream-sync.yml` runs every Monday, merges Casvt/Kapowarr `development` into a branch and opens a pull request if it merges cleanly and the tests pass, or an issue if not. By hand: `git fetch upstream development && git merge upstream/development`. The step numbers of the database must be checked after every merge (see docs/Keeping up with Kapowarr.md). Nothing is pushed to the original.
