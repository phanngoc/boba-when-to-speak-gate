"""Stage 0 — deterministic hard rules (~0 cost).

Returns a `Decision` for instant ALLOW / BLOCK, or `None` to PASS the message
down to the cheap classifier. Nothing here calls a model, so these rules must
live OUTSIDE any LLM (they can't be overridden by prompt injection).
"""
from __future__ import annotations

from typing import Optional

from ..config import GateConfig
from ..models import Decision, Intent, Message, ResponseType, Signals, Stage, Thread


def evaluate(msg: Message, thread: Thread, sig: Signals, cfg: GateConfig,
             now: float) -> Optional[Decision]:
    s = Stage.STAGE0_RULES

    # 1) hard BLOCK — user opted out / muted the thread
    if thread.muted or thread.opted_out:
        return Decision.silent(s, "thread muted/opted-out")

    # 2) explicit dismiss ("Boba im đi") — block AND signal negative feedback
    if sig.is_dismiss:
        return Decision.silent(s, "explicit dismiss by user")

    # 3) hard ALLOW — direct address bypasses cooldown/rate limits
    if sig.is_dm:
        return _allow(s, msg, sig, ResponseType.DIRECT, "direct message (1:1)")
    if sig.mentions_boba or sig.reply_to_boba:
        return _allow(s, msg, sig, ResponseType.DIRECT, "mentioned / replied to Boba")
    if sig.answers_open_loop:
        return _allow(s, msg, sig, ResponseType.CONTINUE,
                      "answers Boba's open loop — must follow through")

    # 4) cooldown — just spoke, give the group room
    if thread.turns_since_boba < cfg.cooldown_turns:
        return Decision.silent(s, f"cooldown ({thread.turns_since_boba} turns since Boba)")

    # 5) hard rate cap in the recent window
    recent = [t for t in thread.boba_msgs_window if now - t <= cfg.rate_window_s]
    thread.boba_msgs_window = recent
    if len(recent) >= cfg.max_boba_per_window:
        return Decision.silent(s, "rate cap reached for window")

    return None  # → PASS to Stage 1


def _allow(stage: Stage, msg: Message, sig: Signals, rtype: ResponseType,
           reason: str) -> Decision:
    return Decision(
        speak=True,
        decided_by=stage,
        intent=sig.intent if sig.intent != Intent.CHITCHAT else Intent.QUESTION,
        response_type=rtype,
        confidence=0.99,
        reason=reason,
        defer_seconds=0.0,  # direct address → answer promptly, no debounce
    )
