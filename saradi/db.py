"""SQLite storage. Every check-in is kept: it is the delay history that becomes the moat."""
from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS doctors (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    hospital TEXT NOT NULL,
    department TEXT NOT NULL DEFAULT '',
    UNIQUE (name, hospital)
);
CREATE TABLE IF NOT EXISTS visits (
    id INTEGER PRIMARY KEY,
    doctor_id INTEGER NOT NULL REFERENCES doctors(id),
    elder_name TEXT NOT NULL,
    elder_phone TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'kannada',
    family_name TEXT NOT NULL,
    family_phone TEXT NOT NULL,
    appointment_at REAL NOT NULL,
    patient_token INTEGER,
    travel_min REAL NOT NULL,
    buffer_min REAL NOT NULL DEFAULT 15,
    clinic_link TEXT,
    state TEXT NOT NULL DEFAULT 'scheduled',
    next_action_at REAL,
    told_leave_at REAL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    visit_id INTEGER REFERENCES visits(id),
    doctor_id INTEGER NOT NULL REFERENCES doctors(id),
    kind TEXT NOT NULL,
    value REAL NOT NULL,
    source TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS reported_waits (
    id INTEGER PRIMARY KEY,
    doctor_id INTEGER NOT NULL REFERENCES doctors(id),
    weekday INTEGER,
    delay_min REAL NOT NULL,
    reported_by TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS calls (
    id INTEGER PRIMARY KEY,
    visit_id INTEGER NOT NULL REFERENCES visits(id),
    purpose TEXT NOT NULL,
    script TEXT NOT NULL,
    provider TEXT NOT NULL,
    external_id TEXT,
    status TEXT NOT NULL,
    response TEXT,
    attempt INTEGER NOT NULL DEFAULT 1,
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    visit_id INTEGER NOT NULL REFERENCES visits(id),
    to_phone TEXT NOT NULL,
    body TEXT NOT NULL,
    channel TEXT NOT NULL,
    status TEXT NOT NULL,
    at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS family_links (
    family_phone TEXT PRIMARY KEY,
    code TEXT NOT NULL UNIQUE,
    chat_id TEXT,
    linked_at REAL
);
CREATE TABLE IF NOT EXISTS family_prefs (
    family_phone TEXT PRIMARY KEY,
    prefs TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    visit_id INTEGER NOT NULL REFERENCES visits(id),
    text TEXT NOT NULL,
    at REAL NOT NULL
);
"""


class DB:
    def __init__(self, path: str | Path = ":memory:"):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.lock = threading.RLock()

    def execute(self, sql: str, params: tuple | dict = ()) -> int:
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur.lastrowid

    def all(self, sql: str, params: tuple | dict = ()) -> list[dict]:
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def one(self, sql: str, params: tuple | dict = ()) -> dict | None:
        rows = self.all(sql, params)
        return rows[0] if rows else None

    def doctor_id(self, name: str, hospital: str, department: str = "") -> int:
        row = self.one("SELECT id FROM doctors WHERE name = ? AND hospital = ?", (name, hospital))
        if row:
            return row["id"]
        return self.execute(
            "INSERT INTO doctors (name, hospital, department) VALUES (?, ?, ?)",
            (name, hospital, department),
        )
