# -*- coding: utf-8 -*-

"""
The small tables of the extra features (watch list, requests, followed
series). They are created here when first needed, with `IF NOT EXISTS`, so
they do not take a number in the database migration steps of the original.
"""

from backend.internals.db import commit, get_db

SCHEMA = """
CREATE TABLE IF NOT EXISTS fork_watchlist(
    id INTEGER PRIMARY KEY,
    kind VARCHAR(20) NOT NULL,
    value VARCHAR(255) NOT NULL COLLATE NOCASE,
    UNIQUE(kind, value)
);
CREATE TABLE IF NOT EXISTS fork_requests(
    id INTEGER PRIMARY KEY,
    requester VARCHAR(100) NOT NULL DEFAULT '',
    comicvine_id INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    year INTEGER,
    volume_id INTEGER,
    created_at INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS fork_followed(
    comicvine_id INTEGER PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    followed_at INTEGER NOT NULL
);
"""

_ready = False


def ensure_tables() -> None:
    "Create the tables if they are not there yet."
    global _ready
    if _ready:
        return
    cursor = get_db()
    for statement in SCHEMA.split(";"):
        if statement.strip():
            cursor.execute(statement)
    commit()
    _ready = True
    return
