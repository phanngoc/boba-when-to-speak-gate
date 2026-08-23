"""(iii) Open-loop tracking.

When Boba asks the group a question, it opens a "loop" and must notice when
someone answers it — otherwise it looks like a bot that asks and then ignores
the reply. This module:

  * registers a loop when Boba speaks a question (`register_from_boba`)
  * detects whether an incoming human message answers the open loop
    (`is_answer`) — feeds the Stage-0 hard ALLOW (`response_type=continue`)
  * resolves loops, either by a human or by Boba following up (`resolve`)

The loop's `kind` (time / choice / confirm / open) is inferred from Boba's
question so the answer-detector knows what a valid answer looks like.
"""
from __future__ import annotations

from typing import Optional

from ..models import Message, OpenLoop, SenderKind, Thread
from . import signals as sig

_AFFIRM = ["u", "uh", "um", "ok", "oke", "duoc", "dc", "co", "vang", "chuan", "roi"]
_NEGATE = ["khong", "ko", "thoi", "khoi"]


def infer_kind(question_text: str) -> str:
    t = sig.norm(question_text)
    if any(k in t for k in ["may gio", "khi nao", "luc nao", "gio nao", "bao gio"]) \
            or sig.has_time_expression(question_text) and "?" in question_text:
        return "time"
    if any(k in t for k in ["quan nao", "mon gi", "cho nao", "o dau", "khu nao",
                            "chon", "cai nao", "an gi", "di dau"]):
        return "choice"
    if any(k in t for k in ["duoc khong", "dc khong", "ok khong", "co khong", "nhe", "chứ"]):
        return "confirm"
    return "open"


def register_from_boba(thread: Thread, boba_msg: Message) -> Optional[OpenLoop]:
    """Call right after Boba sends a message; opens a loop if it asked a question."""
    if not boba_msg.from_boba or not sig.is_question(boba_msg.text):
        return None
    loop = OpenLoop(
        loop_id=f"loop-{boba_msg.msg_id or int(boba_msg.ts)}",
        owner=SenderKind.BOBA,
        question_text=boba_msg.text,
        kind=infer_kind(boba_msg.text),
        created_ts=boba_msg.ts,
    )
    thread.open_loops.append(loop)
    return loop


def is_answer(msg: Message, thread: Thread) -> Optional[OpenLoop]:
    """Does this human message answer Boba's currently-open loop? Returns it if so."""
    if msg.sender_kind != SenderKind.HUMAN:
        return None
    loop = thread.open_boba_loop()
    if loop is None or msg.ts < loop.created_ts:
        return None
    t = sig.norm(msg.text)

    if loop.kind == "time":
        matched = sig.has_time_expression(msg.text)
    elif loop.kind == "choice":
        # a proposal/statement (not another question) that names something concrete
        matched = (not sig.is_question(msg.text)) and (
            sig.mentions_place_or_food(msg.text) or _looks_like_proposal(t)
        )
    elif loop.kind == "confirm":
        matched = _has_word(t, _AFFIRM) or _has_word(t, _NEGATE)
    else:  # open
        matched = len(t) >= 2 and not sig.is_question(msg.text)

    return loop if matched else None


def human_answered_since(thread: Thread, since_ts: float) -> bool:
    """Did a human post a substantive (non-question) answer after `since_ts`?

    Used by the debounce to yield when a human resolves the thread first.
    """
    for m in thread.history:
        if (m.ts > since_ts and m.sender_kind == SenderKind.HUMAN
                and not sig.is_question(m.text) and len(sig.norm(m.text)) >= 2):
            return True
    return False


def resolve(thread: Thread, loop: OpenLoop, by: SenderKind, ts: float) -> None:
    loop.status = "resolved"
    loop.resolved_by = by
    loop.resolved_ts = ts


def resolve_all_boba_loops(thread: Thread, by: SenderKind, ts: float) -> int:
    n = 0
    for lp in thread.open_loops:
        if lp.owner == SenderKind.BOBA and lp.status == "open":
            resolve(thread, lp, by, ts)
            n += 1
    return n


# --- small heuristics -------------------------------------------------------

def _looks_like_proposal(t: str) -> bool:
    # a directive/close: trailing "... đi" or a "chốt ..."
    return t == "di" or t.endswith(" di") or "chot" in t


def _has_word(t: str, lex) -> bool:
    import re
    return any(re.search(rf"(^|\W){re.escape(w)}(\W|$)", t) for w in lex)
