import sqlite3
import unittest
from unittest.mock import patch

from backend.base.definitions import DownloadType
from backend.internals import db_migration as dm

# the app registers this for its own connection; a plain one needs it too
sqlite3.register_adapter(DownloadType, lambda v: v.value)


def make_db(volume_columns="id, mangadex_id", client_columns="id, title"):
    db = sqlite3.connect(":memory:")
    db.executescript(f"""
        CREATE TABLE volumes({volume_columns});
        CREATE TABLE external_download_clients({client_columns});
        CREATE TABLE config(key TEXT PRIMARY KEY, value);
        CREATE TABLE indexer_clients(
            id INTEGER PRIMARY KEY, enabled BOOL NOT NULL DEFAULT 1,
            download_type INTEGER NOT NULL, client_type VARCHAR(255) NOT NULL,
            title VARCHAR(255) NOT NULL, url TEXT NOT NULL,
            gc_service_preference TEXT, gc_avoid_large_downloads BOOL,
            api_path VARCHAR(255), api_key VARCHAR(255), categories VARCHAR(255));
    """)
    return db


class BridgeForkDatabaseTests(unittest.TestCase):
    def bridge(self, db, version):
        with patch.object(dm, 'get_db', return_value=db):
            return dm.DatabaseMigrationHandler.bridge_fork_database(version)

    def test_fork_database_goes_back_to_45(self):
        self.assertEqual(self.bridge(make_db(), 46), 45)

    def test_database_that_already_has_the_upstream_change_stays(self):
        db = make_db(client_columns="id, title, enabled")
        self.assertEqual(self.bridge(db, 46), 46)

    def test_plain_upstream_database_stays(self):
        db = make_db(volume_columns="id")
        self.assertEqual(self.bridge(db, 46), 46)

    def test_other_versions_are_never_touched(self):
        for v in (20, 45, 47, 51):
            self.assertEqual(self.bridge(make_db(), v), v)


class ForkDataMigrationTests(unittest.TestCase):
    def run_handler(self, db):
        with patch.object(dm, 'get_db', return_value=db):
            dm.DatabaseMigrationHandler.handlers[52]()

    def indexers(self, db):
        return db.execute(
            "SELECT client_type, url, api_key, enabled FROM indexer_clients "
            "ORDER BY client_type").fetchall()

    def test_prowlarr_settings_become_an_indexer_and_the_key_is_removed(self):
        db = make_db()
        db.executemany("INSERT INTO config VALUES (?, ?)", [
            ('prowlarr_base_url', b'http://prowlarr:9696'),
            ('prowlarr_api_key', 'secret'), ('port', 5656)])
        self.run_handler(db)
        self.assertEqual(self.indexers(db), [
            ('Internet Archive', 'https://archive.org', None, 1),
            ('Prowlarr', 'http://prowlarr:9696', 'secret', 1)])
        self.assertEqual(
            db.execute("SELECT key FROM config").fetchall(), [('port',)])

    def test_no_prowlarr_settings_only_adds_internet_archive(self):
        db = make_db()
        self.run_handler(db)
        self.assertEqual([r[0] for r in self.indexers(db)], ['Internet Archive'])

    def test_empty_prowlarr_settings_add_nothing(self):
        db = make_db()
        db.executemany("INSERT INTO config VALUES (?, ?)", [
            ('prowlarr_base_url', ''), ('prowlarr_api_key', '')])
        self.run_handler(db)
        self.assertEqual([r[0] for r in self.indexers(db)], ['Internet Archive'])

    def test_running_twice_adds_nothing_new(self):
        db = make_db()
        db.executemany("INSERT INTO config VALUES (?, ?)", [
            ('prowlarr_base_url', 'http://p:9696'), ('prowlarr_api_key', 'k')])
        self.run_handler(db)
        before = self.indexers(db)
        db.executemany("INSERT INTO config VALUES (?, ?)", [
            ('prowlarr_base_url', 'http://p:9696'), ('prowlarr_api_key', 'k')])
        self.run_handler(db)
        self.assertEqual(self.indexers(db), before)


class AddColumnsIfMissingTests(unittest.TestCase):
    def test_adds_only_what_is_missing(self):
        db = sqlite3.connect(":memory:")
        db.execute("CREATE TABLE t(id, api_path)")
        with patch.object(dm, 'get_db', return_value=db):
            dm._add_columns_if_missing("t", {"api_path": "TEXT", "api_key": "TEXT"})
            dm._add_columns_if_missing("t", {"api_path": "TEXT", "api_key": "TEXT"})
        self.assertEqual([r[1] for r in db.execute("PRAGMA table_info(t)")],
                         ["id", "api_path", "api_key"])


if __name__ == '__main__':
    unittest.main()
