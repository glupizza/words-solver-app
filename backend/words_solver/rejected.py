"""Persistent rejected words. Each operation uses its own SQLite connection."""

import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

WORD = re.compile(r"[а-яё]{1,25}\Z")


def normalize_word(value):
    if not isinstance(value, str):
        raise ValueError("Некорректное слово")
    word = value.strip().lower()
    if not WORD.fullmatch(word):
        raise ValueError("Введите слово из русских букв длиной до 25 символов")
    return word


class RejectedStore:
    def __init__(self, path):
        self.path = Path(path).resolve()
        self.initializing = True
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "CREATE TABLE IF NOT EXISTS rejected_words (word TEXT PRIMARY KEY, rejected_at TEXT NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS admin_sessions (token TEXT PRIMARY KEY, expires_at REAL NOT NULL)"
            )
            db.execute(
                "CREATE TABLE IF NOT EXISTS login_attempts (id INTEGER PRIMARY KEY, attempted_at REAL NOT NULL, client_key TEXT)"
            )
            columns = {row[1] for row in db.execute("PRAGMA table_info(login_attempts)")}
            if "client_key" not in columns:
                db.execute("ALTER TABLE login_attempts ADD COLUMN client_key TEXT")
            db.execute(
                "CREATE INDEX IF NOT EXISTS login_attempts_client_time ON login_attempts (client_key, attempted_at)"
            )

        self.initializing = False

    @contextmanager
    def connect(self):
        mode = "rwc" if self.initializing else "rw"
        db = sqlite3.connect(f"{self.path.as_uri()}?mode={mode}", uri=True, timeout=5)
        try:
            db.execute("PRAGMA busy_timeout=5000")
            with db:
                yield db
        finally:
            db.close()

    def snapshot(self):
        with self.connect() as db:
            return frozenset(row[0] for row in db.execute("SELECT word FROM rejected_words"))

    def reject(self, word):
        with self.connect() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO rejected_words VALUES (?, ?)",
                (word, datetime.now(timezone.utc).isoformat()),
            )
            return cursor.rowcount == 1

    def restore(self, word):
        with self.connect() as db:
            db.execute("DELETE FROM rejected_words WHERE word = ?", (word,))

    def list_words(self, search, limit, offset):
        with self.connect() as db:
            total = db.execute("SELECT count(*) FROM rejected_words").fetchone()[0]
            # instr avoids LIKE wildcards and handles Cyrillic after Python lowercasing.
            rows = db.execute(
                "SELECT word, rejected_at FROM rejected_words WHERE instr(word, ?) > 0 ORDER BY rejected_at DESC, word ASC LIMIT ? OFFSET ?",
                (search, limit, offset),
            ).fetchall()
            count = db.execute(
                "SELECT count(*) FROM rejected_words WHERE instr(word, ?) > 0", (search,)
            ).fetchone()[0]
        return total, count, rows

    def login_attempt(self, client_key, now, limit=5, window=900):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM login_attempts WHERE attempted_at <= ?", (now - window,))
            count = db.execute(
                "SELECT count(*) FROM login_attempts WHERE client_key = ?", (client_key,)
            ).fetchone()[0]
            if count >= limit:
                return False
            db.execute(
                "INSERT INTO login_attempts (attempted_at, client_key) VALUES (?, ?)",
                (now, client_key),
            )
            return True

    def clear_attempts(self, client_key):
        with self.connect() as db:
            db.execute("DELETE FROM login_attempts WHERE client_key = ?", (client_key,))

    def create_session(self, token, expires):
        with self.connect() as db:
            db.execute(
                "DELETE FROM admin_sessions WHERE expires_at <= ?",
                (datetime.now(timezone.utc).timestamp(),),
            )
            db.execute("INSERT INTO admin_sessions VALUES (?, ?)", (token, expires))

    def has_session(self, token, now):
        with self.connect() as db:
            return (
                db.execute(
                    "SELECT 1 FROM admin_sessions WHERE token = ? AND expires_at > ?", (token, now)
                ).fetchone()
                is not None
            )

    def delete_session(self, token):
        with self.connect() as db:
            db.execute("DELETE FROM admin_sessions WHERE token = ?", (token,))
