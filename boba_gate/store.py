"""In-memory per-thread state store.

Swap for Redis/Postgres in production — the Gate only needs get_or_create.
State must be isolated per thread_id (multi-tenant: one Boba number serves
many group chats concurrently)."""
from __future__ import annotations

from typing import Dict

from .models import Thread


class ThreadStore:
    def __init__(self):
        self._threads: Dict[str, Thread] = {}

    def get_or_create(self, thread_id: str, *, is_dm: bool = False,
                      group_size: int = 2) -> Thread:
        t = self._threads.get(thread_id)
        if t is None:
            t = Thread(thread_id=thread_id, is_dm=is_dm, group_size=group_size)
            self._threads[thread_id] = t
        return t

    def get(self, thread_id: str) -> Thread | None:
        return self._threads.get(thread_id)

    def reset(self, thread_id: str) -> None:
        self._threads.pop(thread_id, None)
