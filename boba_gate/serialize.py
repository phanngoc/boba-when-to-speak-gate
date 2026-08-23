"""(De)serialize Thread state to plain dicts (JSON-safe).

Used by the Redis / SQL state stores to persist and reload a `Thread` — its
history, open loops, adaptive thresholds, and any in-flight debounce decision.
Enums are stored by `.value` and rebuilt on load.
"""
from __future__ import annotations

from typing import Optional

from .models import (Decision, Intent, Message, OpenLoop, PendingSpeak,
                     ResponseType, SenderKind, Stage, Thread)


def msg_to_dict(m: Message) -> dict:
    return {
        "thread_id": m.thread_id, "sender_id": m.sender_id, "text": m.text,
        "ts": m.ts, "msg_id": m.msg_id, "sender_kind": m.sender_kind.value,
        "reply_to": m.reply_to, "media_only": m.media_only, "mention": m.mention,
    }


def msg_from_dict(d: dict) -> Message:
    return Message(
        thread_id=d["thread_id"], sender_id=d["sender_id"], text=d["text"],
        ts=d["ts"], msg_id=d.get("msg_id", ""),
        sender_kind=SenderKind(d.get("sender_kind", "human")),
        reply_to=d.get("reply_to"), media_only=d.get("media_only", False),
        mention=d.get("mention", False),
    )


def loop_to_dict(l: OpenLoop) -> dict:
    return {
        "loop_id": l.loop_id, "owner": l.owner.value, "question_text": l.question_text,
        "kind": l.kind, "created_ts": l.created_ts, "status": l.status,
        "resolved_by": l.resolved_by.value if l.resolved_by else None,
        "resolved_ts": l.resolved_ts,
    }


def loop_from_dict(d: dict) -> OpenLoop:
    return OpenLoop(
        loop_id=d["loop_id"], owner=SenderKind(d["owner"]),
        question_text=d["question_text"], kind=d["kind"],
        created_ts=d["created_ts"], status=d.get("status", "open"),
        resolved_by=SenderKind(d["resolved_by"]) if d.get("resolved_by") else None,
        resolved_ts=d.get("resolved_ts"),
    )


def decision_to_dict(d: Decision) -> dict:
    return {
        "speak": d.speak, "decided_by": d.decided_by.value, "intent": d.intent.value,
        "response_type": d.response_type.value, "confidence": d.confidence,
        "reason": d.reason, "defer_seconds": d.defer_seconds,
    }


def decision_from_dict(d: dict) -> Decision:
    return Decision(
        speak=d["speak"], decided_by=Stage(d["decided_by"]),
        intent=Intent(d["intent"]), response_type=ResponseType(d["response_type"]),
        confidence=d["confidence"], reason=d["reason"],
        defer_seconds=d["defer_seconds"],
    )


def pending_to_dict(p: Optional[PendingSpeak]) -> Optional[dict]:
    if p is None:
        return None
    return {"decision": decision_to_dict(p.decision),
            "created_ts": p.created_ts, "fire_at": p.fire_at}


def pending_from_dict(d: Optional[dict]) -> Optional[PendingSpeak]:
    if not d:
        return None
    return PendingSpeak(decision=decision_from_dict(d["decision"]),
                        created_ts=d["created_ts"], fire_at=d["fire_at"])


def thread_to_dict(t: Thread) -> dict:
    return {
        "thread_id": t.thread_id, "is_dm": t.is_dm, "muted": t.muted,
        "opted_out": t.opted_out, "group_size": t.group_size,
        "theta_low": t.theta_low, "theta_high": t.theta_high,
        "last_boba_ts": t.last_boba_ts, "turns_since_boba": t.turns_since_boba,
        "recently_ignored": t.recently_ignored,
        "history": [msg_to_dict(m) for m in t.history],
        "open_loops": [loop_to_dict(l) for l in t.open_loops],
        "pending_speak": pending_to_dict(t.pending_speak),
        "boba_msgs_window": list(t.boba_msgs_window),
    }


def thread_from_dict(d: dict) -> Thread:
    t = Thread(
        thread_id=d["thread_id"], is_dm=d.get("is_dm", False),
        muted=d.get("muted", False), opted_out=d.get("opted_out", False),
        group_size=d.get("group_size", 2),
        theta_low=d.get("theta_low", 0.35), theta_high=d.get("theta_high", 0.72),
    )
    t.last_boba_ts = d.get("last_boba_ts", 0.0)
    t.turns_since_boba = d.get("turns_since_boba", 999)
    t.recently_ignored = d.get("recently_ignored", 0)
    t.history = [msg_from_dict(m) for m in d.get("history", [])]
    t.open_loops = [loop_from_dict(l) for l in d.get("open_loops", [])]
    t.pending_speak = pending_from_dict(d.get("pending_speak"))
    t.boba_msgs_window = list(d.get("boba_msgs_window", []))
    return t
