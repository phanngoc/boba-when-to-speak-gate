"""Debounce — the race with humans.

Even when the gate decides SPEAK, we don't send immediately. We hold the
decision for `defer_seconds` and, if a human resolves the thread in the
meantime, we cancel. This is what makes Boba feel like it "waits until needed".

Pure logic here (delay + cancel predicate) so it's unit-testable; the async
scheduler at the bottom is for real deployment.
"""
from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from ..config import GateConfig
from ..models import PendingSpeak, SenderKind, Thread
from . import openloop, signals as sig


def debounce_delay(thread: Thread, cfg: GateConfig, now: float) -> float:
    """Longer wait when the group is chatty (more likely a human answers first)."""
    vmin = sig.velocity_msgs_per_min(thread, now)
    delay = cfg.debounce_base_s + min(vmin, 10.0) * 0.4
    return max(cfg.debounce_min_s, min(cfg.debounce_max_s, delay))


def should_cancel(thread: Thread) -> tuple[bool, str]:
    """Re-evaluated when the debounce timer fires (or a new msg arrives).

    Cancel the pending SPEAK if, during the window, humans either:
      * answered the pending question themselves, or
      * converged on an answer ("chốt quán X đi").
    """
    if sig.humans_converging(thread):
        return True, "humans converged on an answer"
    pending = thread.pending_speak
    if pending is not None and openloop.human_answered_since(thread, pending.created_ts):
        return True, "a human answered first"
    return False, ""


def incoming_resolves(msg) -> bool:
    """Does this single incoming human message look like it resolves the thread,
    such that a pending Boba SPEAK should yield? (converge / propose / answer)."""
    if msg.sender_kind != SenderKind.HUMAN:
        return False
    return sig.looks_like_resolution(msg.text)


class DebounceScheduler:
    """asyncio-based holder for deferred SPEAK decisions (one per thread).

    `send_cb(thread)` is awaited when the timer fires and no cancellation
    happened. Call `on_new_message(thread)` whenever a new message lands so an
    in-flight pending decision can be cancelled early.
    """

    def __init__(self, send_cb: Callable[[Thread], Awaitable[None]]):
        self.send_cb = send_cb
        self._tasks: dict[str, asyncio.Task] = {}

    def schedule(self, thread: Thread, pending: PendingSpeak, now: float) -> None:
        self.cancel(thread.thread_id)
        thread.pending_speak = pending
        delay = max(0.0, pending.fire_at - now)
        self._tasks[thread.thread_id] = asyncio.ensure_future(self._run(thread, delay))

    async def _run(self, thread: Thread, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
            cancel, _ = should_cancel(thread)
            if not cancel and thread.pending_speak is not None:
                await self.send_cb(thread)
        finally:
            thread.pending_speak = None
            self._tasks.pop(thread.thread_id, None)

    def on_new_message(self, thread: Thread) -> None:
        if thread.pending_speak is None:
            return
        cancel, _ = should_cancel(thread)
        if cancel:
            self.cancel(thread.thread_id)
            thread.pending_speak = None

    def cancel(self, thread_id: str) -> None:
        task = self._tasks.pop(thread_id, None)
        if task and not task.done():
            task.cancel()
