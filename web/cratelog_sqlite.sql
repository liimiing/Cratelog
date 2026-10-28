CREATE TABLE IF NOT EXISTS cratelog_albums (
 id TEXT PRIMARY KEY,
 rating REAL NOT NULL DEFAULT 0 CHECK(rating BETWEEN 0 AND 5 AND rating*2=CAST(rating*2 AS INTEGER)),
 personal_comment TEXT NOT NULL DEFAULT '',
 documents TEXT NOT NULL DEFAULT '[]',
 local_path TEXT NOT NULL,
 metadata TEXT NOT NULL,
 images TEXT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 1,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS cratelog_tracks (
 album_id TEXT NOT NULL REFERENCES cratelog_albums(id) ON DELETE CASCADE,
 position INTEGER NOT NULL,
 filename TEXT NOT NULL,
 selected INTEGER NOT NULL DEFAULT 0,
 highlighted INTEGER NOT NULL DEFAULT 0,
 PRIMARY KEY(album_id,position)
);
CREATE INDEX IF NOT EXISTS cratelog_updated ON cratelog_albums(updated_at);
