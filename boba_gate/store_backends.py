"""Durable state stores: Redis (hot state) and SQL (Postgres/SQLite).

Both expose the same surface as the in-memory `ThreadStore`:
    get_or_create(thread_id, *, is_dm, group_size) -> Thread
    get(thread_id) -> Thread | None
    save(thread) -> None
    reset(thread_id) -> None

so the gate flow becomes: `t = store.get_or_create(id); gate.handle(msg, t); store.save(t)`.

Neither `redis` nor `psycopg` is imported here — the clients are duck-typed and
injected, so this module (and its tests, via a fake KV and stdlib `sqlite3`) run
with zero third-party dependencies. Production wiring:

    import redis
    RedisThreadStore(redis.Redis.from_url("redis://..."))

    import psycopg
    SqlThreadStore(psycopg.connect("postgresql://..."), placeholder="%s",
                   autocommit=True)
"""
from __future__ import annotations

import json
from typing import Optional

from .models import Thread
from .serialize import thread_from_dict, thread_to_dict


# --- Redis: whole-thread JSON blob (hot state) ------------------------------
class RedisThreadStore:
    def __init__(self, client, prefix: str = "boba:thread:",
                 ttl_seconds: Optional[int] = None):
        self.client = client          # redis-py style: get/set/delete
        self.prefix = prefix
        self.ttl = ttl_seconds

    def _key(self, thread_id: str) -> str:
        return f"{self.prefix}{thread_id}"

    def get(self, thread_id: str) -> Optional[Thread]:
        raw = self.client.get(self._key(thread_id))
        if raw is None:
            return None
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        return thread_from_dict(json.loads(raw))

    def get_or_create(self, thread_id: str, *, is_dm: bool = False,
                      group_size: int = 2) -> Thread:
        t = self.get(thread_id)
        if t is None:
            t = Thread(thread_id=thread_id, is_dm=is_dm, group_size=group_size)
        return t

    def save(self, thread: Thread) -> None:
        payload = json.dumps(thread_to_dict(thread), ensure_ascii=False)
        if self.ttl:
            self.client.set(self._key(thread.thread_id), payload, ex=self.ttl)
        else:
            self.client.set(self._key(thread.thread_id), payload)

    def reset(self, thread_id: str) -> None:
        self.client.delete(self._key(thread_id))


# --- SQL: durable relational store (Postgres / SQLite) ----------------------
_SCHEMA_SQLITE = """
CREATE TABLE IF NOT EXISTS threads (
  thread_id TEXT PRIMARY KEY, is_dm INTEGER, muted INTEGER, opted_out INTEGER,
  group_size INTEGER, theta_low REAL, theta_high REAL, last_boba_ts REAL,
  turns_since_boba INTEGER, recently_ignored INTEGER, state_json TEXT
);
CREATE TABLE IF NOT EXISTS feedback (
  id INTEGER PRIMARY KEY AUTOINCREMENT, thread_id TEXT, positive INTEGER, ts REAL
);
"""

# For Postgres, use SERIAL and store state_json as JSONB; see data/schema_postgres.sql.


class SqlThreadStore:
    """Reference relational store. For simplicity `save()` writes the whole
    thread as one row (scalar columns for querying + a `state_json` blob for
    faithful reload). A production store would append messages/loops
    incrementally into their own tables; the columns here show the shape."""

    def __init__(self, conn, placeholder: str = "?", init_schema: bool = True):
        self.conn = conn
        self.ph = placeholder            # "?" for sqlite3, "%s" for psycopg
        if init_schema:
            self.ensure_schema()

    def ensure_schema(self) -> None:
        cur = self.conn.cursor()
        # sqlite supports executescript; psycopg users should run schema_postgres.sql
        if hasattr(cur, "executescript"):
            cur.executescript(_SCHEMA_SQLITE)
        else:  # generic DBAPI: run statements one by one
            for stmt in filter(str.strip, _SCHEMA_SQLITE.split(";")):
                cur.execute(stmt)
        self.conn.commit()

    def get(self, thread_id: str) -> Optional[Thread]:
        cur = self.conn.cursor()
        cur.execute(f"SELECT state_json FROM threads WHERE thread_id = {self.ph}",
                    (thread_id,))
        row = cur.fetchone()
        if not row or not row[0]:
            return None
        return thread_from_dict(json.loads(row[0]))

    def get_or_create(self, thread_id: str, *, is_dm: bool = False,
                      group_size: int = 2) -> Thread:
        t = self.get(thread_id)
        if t is None:
            t = Thread(thread_id=thread_id, is_dm=is_dm, group_size=group_size)
        return t

    def save(self, thread: Thread) -> None:
        p = self.ph
        state = json.dumps(thread_to_dict(thread), ensure_ascii=False)
        cols = (thread.thread_id, int(thread.is_dm), int(thread.muted),
                int(thread.opted_out), thread.group_size, thread.theta_low,
                thread.theta_high, thread.last_boba_ts, thread.turns_since_boba,
                thread.recently_ignored, state)
        placeholders = ", ".join([p] * len(cols))
        cur = self.conn.cursor()
        # upsert (both sqlite and Postgres support ON CONFLICT)
        cur.execute(
            f"INSERT INTO threads (thread_id, is_dm, muted, opted_out, group_size, "
            f"theta_low, theta_high, last_boba_ts, turns_since_boba, "
            f"recently_ignored, state_json) VALUES ({placeholders}) "
            f"ON CONFLICT(thread_id) DO UPDATE SET is_dm=excluded.is_dm, "
            f"muted=excluded.muted, opted_out=excluded.opted_out, "
            f"group_size=excluded.group_size, theta_low=excluded.theta_low, "
            f"theta_high=excluded.theta_high, last_boba_ts=excluded.last_boba_ts, "
            f"turns_since_boba=excluded.turns_since_boba, "
            f"recently_ignored=excluded.recently_ignored, "
            f"state_json=excluded.state_json",
            cols)
        self.conn.commit()

    def add_feedback(self, thread_id: str, positive: bool, ts: float) -> None:
        p = self.ph
        cur = self.conn.cursor()
        cur.execute(
            f"INSERT INTO feedback (thread_id, positive, ts) VALUES ({p}, {p}, {p})",
            (thread_id, int(positive), ts))
        self.conn.commit()

    def reset(self, thread_id: str) -> None:
        p = self.ph
        cur = self.conn.cursor()
        cur.execute(f"DELETE FROM threads WHERE thread_id = {p}", (thread_id,))
        cur.execute(f"DELETE FROM feedback WHERE thread_id = {p}", (thread_id,))
        self.conn.commit()
