"""FastAPI webhook layer (transport ⇄ gate).

Flow:  iMessage gateway (Sendblue/BlueBubbles) --webhook POST--> /webhook
       → parse to Message → Gate.handle → if SPEAK, responder renders text →
       gateway REST send. Deferred SPEAKs are held by DebounceScheduler.

This module needs `fastapi`/`uvicorn` (see requirements.txt); the core gate does
not. Run:  uvicorn boba_gate.web:app --reload
"""
from __future__ import annotations

import time
from typing import Awaitable, Callable

try:
    from fastapi import FastAPI, Request
except ImportError as e:  # pragma: no cover - only when web extra missing
    raise SystemExit("web layer needs fastapi: pip install -r requirements.txt") from e

from .gate.debounce import DebounceScheduler
from .gate.pipeline import Gate, TemplateResponder
from .models import Message, SenderKind, Thread
from .store import ThreadStore

app = FastAPI(title="Boba When-to-Speak Gate")

gate = Gate()
store = ThreadStore()
responder = TemplateResponder()


# --- gateway send abstraction --------------------------------------------
# Default sink logs the outbound message. To go live, reassign this module-level
# function (or monkeypatch) with a coroutine that POSTs to your iMessage API
# provider (Sendblue/BlueBubbles/LoopMessage). Kept as a seam so the service
# runs end-to-end locally with no provider credentials.
async def send_to_gateway(thread_id: str, text: str) -> None:
    print(f"[SEND → {thread_id}] {text}")


async def _deliver(thread: Thread) -> None:
    pending = thread.pending_speak
    if pending is None:
        return
    text = responder.render(pending.decision, thread.history[-1], thread)
    await send_to_gateway(thread.thread_id, text)
    gate.record_boba_utterance(thread, text, time.time())


scheduler = DebounceScheduler(_deliver)


def parse_webhook(payload: dict) -> Message:
    """Normalize a Sendblue-style inbound payload into our Message."""
    return Message(
        thread_id=str(payload.get("group_id") or payload.get("from_number", "dm")),
        sender_id=str(payload.get("from_number", "unknown")),
        text=str(payload.get("content", "")),
        ts=float(payload.get("date", time.time())),
        msg_id=str(payload.get("message_handle", "")),
        sender_kind=SenderKind.HUMAN,
        reply_to=payload.get("reply_to"),
        media_only=not payload.get("content") and bool(payload.get("media_url")),
    )


@app.post("/webhook")
async def webhook(request: Request):
    payload = await request.json()
    msg = parse_webhook(payload)
    thread = store.get_or_create(
        msg.thread_id, is_dm=bool(payload.get("is_dm")),
        group_size=int(payload.get("group_size", 2)))

    scheduler.on_new_message(thread)          # maybe cancel an in-flight SPEAK
    dec = gate.handle(msg, thread)

    if dec.speak and not dec.deferred:
        text = responder.render(dec, msg, thread)
        await send_to_gateway(thread.thread_id, text)
        gate.record_boba_utterance(thread, text, time.time())
    elif dec.deferred and thread.pending_speak is not None:
        scheduler.schedule(thread, thread.pending_speak, time.time())

    return {"speak": dec.speak, "deferred": dec.deferred,
            "stage": dec.decided_by.value, "reason": dec.reason}


@app.post("/feedback")
async def feedback(request: Request):
    body = await request.json()
    thread = store.get(str(body["thread_id"]))
    if thread is not None:
        gate.on_feedback(thread, positive=bool(body["positive"]))
    return {"ok": thread is not None}


@app.get("/health")
async def health():
    return {"status": "ok"}
