# Keeping up with Kapowarr

This copy is built on the `development` branch of [Kapowarr](https://github.com/Casvt/Kapowarr), with its history, so new work from the original can be merged in.

* **Every Monday** a workflow fetches the original's newest commits and tries to merge them. If they merge cleanly and the tests pass, it opens a pull request. If not, it opens an issue.
* **By hand:** `git remote add upstream https://github.com/Casvt/Kapowarr.git`, then `git fetch upstream development && git merge upstream/development`, then run the tests.
* **Check the migrations.** The database steps are numbered. This copy adds a bridge (for databases of its earlier version) and step 52 (Prowlarr and the Internet Archive). If the original adds a step 52 of its own, move ours to the next free number and check `bridge_fork_database` in `backend/internals/db_migration.py`.
* **What this copy adds** lives in a few files: `backend/implementations/indexer_clients/` and `download_preppers/` (Prowlarr, Internet Archive), `backend/implementations/torrent_links.py`, and the end of `backend/internals/db_migration.py`. Conflicts are rare because the original's own plug-in design is used.
