import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class Storage:
    """Only called on the application's event loop, never from device threads."""
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS metadata(id TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS preferences(light_id TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS scenes(id TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS timers(light_id TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, light_id TEXT, kind TEXT, message TEXT);
            CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY, value TEXT NOT NULL);
        """)
        self.db.commit()
        # Interrupted requests are never replayed after restarting.
        for row in self.db.execute("SELECT id, value FROM operations").fetchall():
            value = json.loads(row["value"])
            if value["status"] in ("pending", "running"):
                value.update(status="failed", message="服务重启，操作未重放", finished_at=utc_now())
                self.put("operations", row["id"], value)

    def get(self, table, key):
        column = "light_id" if table in ("preferences", "timers") else "id"
        row = self.db.execute(f"SELECT value FROM {table} WHERE {column} = ?", (key,)).fetchone()
        return json.loads(row["value"]) if row else None

    def put(self, table, key, value):
        assert table in ("preferences", "scenes", "timers", "operations", "metadata")
        column = "light_id" if table in ("preferences", "timers") else "id"
        self.db.execute(f"INSERT OR REPLACE INTO {table} ({column}, value) VALUES (?, ?)", (key, json.dumps(value, ensure_ascii=False)))
        self.db.commit()

    def delete(self, table, key):
        assert table in ("scenes", "timers")
        column = "light_id" if table == "timers" else "id"
        self.db.execute(f"DELETE FROM {table} WHERE {column} = ?", (key,))
        self.db.commit()

    def all(self, table):
        assert table in ("scenes", "timers", "operations")
        return [json.loads(row["value"]) for row in self.db.execute(f"SELECT value FROM {table} ORDER BY rowid")]

    def event(self, light_id, kind, message):
        self.db.execute("INSERT INTO events (at,light_id,kind,message) VALUES (?,?,?,?)", (utc_now(), light_id, kind, message))
        self.db.execute("DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 300)")
        self.db.commit()

    def events(self, limit=30):
        return [dict(row) for row in self.db.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))]

    def new_operation(self, light_id, target, source, ttl):
        import time
        operation = dict(id=uuid4().hex, light_id=light_id, target=target, source=source, status="pending", message="等待执行", created_at=utc_now(), expires_at=time.time()+ttl)
        self.put("operations", operation["id"], operation)
        self.db.execute("DELETE FROM operations WHERE id NOT IN (SELECT id FROM operations ORDER BY rowid DESC LIMIT 300)")
        self.db.commit()
        return operation

    def close(self):
        self.db.close()
