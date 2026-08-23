import sqlite3

from boba_gate import Conversation, Gate, Message, SenderKind, Thread
from boba_gate.store_backends import RedisThreadStore, SqlThreadStore


class FakeKV:
    """Minimal redis-py-compatible stand-in (get/set/delete)."""

    def __init__(self):
        self.d = {}

    def get(self, k):
        return self.d.get(k)

    def set(self, k, v, ex=None):
        self.d[k] = v

    def delete(self, k):
        self.d.pop(k, None)


def _run(store):
    g = Gate()
    th = store.get_or_create("g", group_size=5)
    c = Conversation(g, th)
    c.feed(Message("g", "a", "tối nay đi đâu ăn ta?", 1000,
                   sender_kind=SenderKind.HUMAN, msg_id="a1"))
    c.feed(Message("g", "b", "còn ai on ko", 1010,
                   sender_kind=SenderKind.HUMAN, msg_id="b1"))
    store.save(th)
    return th


def test_redis_roundtrip_preserves_state():
    kv = FakeKV()
    th = _run(RedisThreadStore(kv))
    loaded = RedisThreadStore(kv).get("g")           # fresh store, same backend
    assert loaded is not None
    assert len(loaded.history) == len(th.history)
    assert loaded.theta_high == th.theta_high
    assert len(loaded.open_loops) == len(th.open_loops)


def test_redis_get_or_create_and_reset():
    kv = FakeKV()
    store = RedisThreadStore(kv)
    assert store.get("none") is None
    t = store.get_or_create("x", is_dm=True)
    assert t.is_dm and store.get("x") is None         # not saved yet
    store.save(t)
    assert store.get("x") is not None
    store.reset("x")
    assert store.get("x") is None


def test_sqlite_roundtrip_and_scalar_columns():
    conn = sqlite3.connect(":memory:")
    th = _run(SqlThreadStore(conn))
    loaded = SqlThreadStore(conn, init_schema=False).get("g")
    assert loaded is not None and len(loaded.history) == len(th.history)
    cur = conn.cursor()
    cur.execute("SELECT recently_ignored FROM threads WHERE thread_id = 'g'")
    assert cur.fetchone() is not None                 # scalar column queryable


def test_sqlite_feedback_and_reset():
    conn = sqlite3.connect(":memory:")
    store = SqlThreadStore(conn)
    store.save(Thread("g"))
    store.add_feedback("g", True, 1.0)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM feedback WHERE thread_id = 'g'")
    assert cur.fetchone()[0] == 1
    store.reset("g")
    assert store.get("g") is None
