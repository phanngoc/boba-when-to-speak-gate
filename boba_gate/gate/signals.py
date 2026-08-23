"""Signal / feature extraction — Vietnamese-aware.

Turns a raw incoming message + thread context into a `Signals` object that both
the cheap classifier (stage 1) and the LLM judge (stage 2) consume. Kept as
plain rules so behavior is transparent and unit-testable.
"""
from __future__ import annotations

import re
import unicodedata

from ..models import Intent, Message, SenderKind, Signals, Thread

# --- lexicons (tiếng Việt + English), matched on accent-stripped lowercase ----

_QUESTION_WORDS = [
    "?", "khong", "ko", "chua", "nhi", "ha", "vay",
    "o dau", "dau", "may gio", "khi nao", "bao gio", "luc nao", "gio nao",
    "the nao", "sao", "gi", "ai", "cho nao", "quan nao", "mon gi", "khu nao",
]
_PLANNING = [
    "di an", "an gi", "di choi", "di dau", "toi nay", "cuoi tuan", "hom nay",
    "chieu nay", "hen", "gap", "chot lich", "lich", "ranh", "keo", "tu tap",
    "off", "hop", "di uong", "ca phe", "cafe", "nhau", "chot",
]
_DEADLOCK = [
    "cung duoc", "sao cung duoc", "cung dc", "gi cung dc", "khong biet nua",
    "tuy", "ai quyet", "chot di", "khong chot duoc", "cai nao cung",
]
_EXPLICIT_REQUEST = [
    "tao anh", "tao hinh", "poster", "bai hat", "lam bai hat",
    "sang tac", "tra cuu", "tim giup", "tinh giup", "dich giup",
]
# Cues kept WITH diacritics because their accent-stripped form collides with a
# common word: "vẽ" (draw) vs "về" (go home), "hát" (sing) vs "hạt" (seed).
_EXPLICIT_ACCENTED = ["vẽ", "hát"]
_DISMISS = [
    "boba im", "im di", "boba di", "no bot", "stop boba", "boba stop",
    "on qua", "phien qua", "boba thoi", "boba shush", "cam mieng",
]
_CONVERGING = [
    "chot", "ok luon", "vay nhe", "quyet dinh", "chot keo", "di quan",
    "thong nhat", "vay di", "ok chot", "done", "deal",
]
_BOBA_NAMES = ["boba", "@boba"]

_PLACE_FOOD = ["quan", "nha hang", "mon", "lau", "nuong", "hai san", "pho",
               "bun", "com", "pizza", "beer", "bia", "cafe", "ca phe", "tra sua"]

_TIME_RE = re.compile(r"\b\d{1,2}\s*(h|gio|:)\s*\d{0,2}\b")


def strip_accents(s: str) -> str:
    # 'đ'/'Đ' are standalone Latin letters (no combining mark) → replace manually,
    # otherwise "đi"/"đồng" survive as "đi"/"đong" and lexicon matches silently fail.
    s = s.replace("đ", "d").replace("Đ", "D")
    nfkd = unicodedata.normalize("NFD", s)
    return "".join(c for c in nfkd if unicodedata.category(c) != "Mn")


def norm(text: str) -> str:
    return strip_accents(text.lower()).strip()


def _any(text_norm: str, lexicon) -> bool:
    return any(kw in text_norm for kw in lexicon)


def _wany(text_norm: str, lexicon) -> bool:
    """Word-boundary match — avoids substrings like 've' inside 've nha' (về nhà)
    falsely firing the 'vẽ' (draw) request cue."""
    return any(re.search(rf"(^|\W){re.escape(w)}(\W|$)", text_norm) for w in lexicon)


def mentions_boba(text: str) -> bool:
    t = norm(text)
    return any(name in t for name in _BOBA_NAMES)


def is_dismiss(text: str) -> bool:
    return _wany(norm(text), _DISMISS)


def is_question(text: str) -> bool:
    if "?" in text:
        return True
    t = norm(text)
    # word-ish match to avoid false hits (e.g. "ai" inside "email")
    return any(re.search(rf"(^|\W){re.escape(w)}(\W|$)", t) for w in _QUESTION_WORDS if w != "?")


def detect_intent(text: str) -> Intent:
    t = norm(text)
    if _wany(t, _DISMISS):
        return Intent.DISMISS
    if _wany(t, _EXPLICIT_REQUEST) or _wany(text.lower(), _EXPLICIT_ACCENTED):
        return Intent.EXPLICIT_REQUEST
    if _wany(t, _DEADLOCK):
        return Intent.DECISION_DEADLOCK
    if _wany(t, _PLANNING):
        return Intent.PLANNING
    if is_question(text):
        return Intent.QUESTION
    return Intent.CHITCHAT


def has_time_expression(text: str) -> bool:
    t = norm(text)
    if _TIME_RE.search(t):
        return True
    return _any(t, ["toi nay", "sang", "trua", "chieu", "toi mai", "cuoi tuan", "gio"])


def addressed_target(text: str, thread: Thread) -> str:
    """'boba' | 'individual' | 'group' — who is this message aimed at?"""
    if mentions_boba(text):
        return "boba"
    t = norm(text)
    # "<Name> oi", "<Name> ơi" → a specific human, not Boba's business
    if re.search(r"(^|\W)[a-z]{2,10}\s+oi(\W|$)", t) and not mentions_boba(text):
        return "individual"
    return "group"


def mentions_place_or_food(text: str) -> bool:
    return _wany(norm(text), _PLACE_FOOD)


def looks_like_resolution(text: str) -> bool:
    """A message that closes the loop: a convergence word, a concrete proposal
    (place/food/time), or a directive '... đi'. Shared by the classifier's
    `humans_converging` signal and the debounce cancel check for consistency."""
    t = norm(text)
    if _wany(t, _CONVERGING):
        return True
    if mentions_place_or_food(text):
        return True
    if has_time_expression(text) and not is_question(text):
        return True
    if t == "di" or t.endswith(" di"):     # trailing "... đi" = a proposal
        return True
    return False


def humans_converging(thread: Thread, lookback: int = 2) -> bool:
    """Are the humans themselves closing in on an answer? → Boba should retreat."""
    recent = [m for m in thread.history[-lookback:] if m.sender_kind == SenderKind.HUMAN]
    return any(looks_like_resolution(m.text) for m in recent)


def velocity_msgs_per_min(thread: Thread, now: float, window_s: float = 60.0) -> float:
    recent = [m for m in thread.history if now - m.ts <= window_s]
    if not recent:
        return 0.0
    return len(recent) * 60.0 / window_s


def has_unanswered_question(thread: Thread, exclude_last: bool = True) -> bool:
    """A group question left hanging (asked, then no human answered after it)."""
    msgs = thread.history[:-1] if exclude_last and thread.history else thread.history
    for i in range(len(msgs) - 1, -1, -1):
        m = msgs[i]
        if m.sender_kind == SenderKind.HUMAN and is_question(m.text):
            # answered if a later human message exists that is not itself a question
            later = msgs[i + 1 :]
            answered = any(
                x.sender_kind == SenderKind.HUMAN and not is_question(x.text) for x in later
            )
            return not answered
        if i < len(msgs) - 4:  # only look a few turns back
            break
    return False


def extract(msg: Message, thread: Thread, now: float, answers_open_loop: bool) -> Signals:
    """Build the full Signals vector for `msg` given `thread` context."""
    intent = detect_intent(msg.text)
    return Signals(
        is_question=is_question(msg.text),
        intent=intent,
        mentions_boba=mentions_boba(msg.text) or msg.mention,
        reply_to_boba=_reply_to_boba(msg, thread),
        is_dm=thread.is_dm,
        is_dismiss=intent == Intent.DISMISS,
        addressed=addressed_target(msg.text, thread),
        unanswered_question=has_unanswered_question(thread),
        velocity_high=velocity_msgs_per_min(thread, now) >= 8.0,
        humans_converging=humans_converging(thread),
        recently_ignored=thread.recently_ignored,
        answers_open_loop=answers_open_loop,
    )


def _reply_to_boba(msg: Message, thread: Thread) -> bool:
    if not msg.reply_to:
        return False
    for m in thread.history:
        if m.msg_id == msg.reply_to and m.from_boba:
            return True
    return False
