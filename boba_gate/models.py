"""Core data models for the When-to-Speak Gate.

Pure stdlib (dataclasses + enums) so the gate logic runs and tests without any
external dependency. The web layer (FastAPI) lives separately in `web.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SenderKind(str, Enum):
    HUMAN = "human"
    BOBA = "boba"      # our own agent
    BOT = "bot"        # some other bot in the group


class Intent(str, Enum):
    CHITCHAT = "chitchat"
    QUESTION = "question"                 # generic question, not clearly a Boba job
    PLANNING = "planning"                 # coordinate: đi ăn, chốt lịch, chọn chỗ
    DECISION_DEADLOCK = "decision_deadlock"
    EXPLICIT_REQUEST = "explicit_request"  # vẽ ảnh, làm bài hát, tra cứu
    DISMISS = "dismiss"                   # "Boba im đi"


class ResponseType(str, Enum):
    NONE = "none"
    DIRECT = "direct"          # replied/mentioned/DM → answer directly
    CONTINUE = "continue"      # continue an open loop Boba started
    SUGGEST_PLAN = "suggest_plan"
    SETTLE_DEBATE = "settle_debate"
    FULFILL_REQUEST = "fulfill_request"


class Stage(str, Enum):
    STAGE0_RULES = "stage0_rules"
    STAGE1_CLASSIFIER = "stage1_classifier"
    STAGE2_JUDGE = "stage2_judge"


@dataclass
class Message:
    thread_id: str
    sender_id: str
    text: str
    ts: float                       # unix seconds
    msg_id: str = ""
    sender_kind: SenderKind = SenderKind.HUMAN
    reply_to: Optional[str] = None  # msg_id this replies to
    media_only: bool = False        # image/sticker with no text
    mention: bool = False           # transport-signalled @mention / reply-to-bot

    @property
    def from_boba(self) -> bool:
        return self.sender_kind == SenderKind.BOBA


@dataclass
class OpenLoop:
    """A question Boba asked and is waiting to hear back on. See gate/openloop.py."""
    loop_id: str
    owner: SenderKind            # who opened it (normally BOBA)
    question_text: str
    kind: str                    # 'time' | 'choice' | 'confirm' | 'open'
    created_ts: float
    status: str = "open"         # 'open' | 'resolved'
    resolved_by: Optional[SenderKind] = None
    resolved_ts: Optional[float] = None


@dataclass
class PendingSpeak:
    """A SPEAK decision held during the debounce window (race with humans)."""
    decision: "Decision"
    created_ts: float
    fire_at: float               # created_ts + defer_seconds


@dataclass
class Thread:
    thread_id: str
    is_dm: bool = False
    muted: bool = False
    opted_out: bool = False
    group_size: int = 2
    # adaptive thresholds (per-thread personalization)
    theta_low: float = 0.35
    theta_high: float = 0.72
    # behavioral state
    history: list = field(default_factory=list)   # list[Message], capped
    last_boba_ts: float = 0.0
    turns_since_boba: int = 999
    recently_ignored: int = 0
    open_loops: list = field(default_factory=list)  # list[OpenLoop]
    pending_speak: Optional[PendingSpeak] = None
    # counters for rate limiting / cooldown
    boba_msgs_window: list = field(default_factory=list)  # timestamps of Boba msgs

    HISTORY_CAP = 60

    def append(self, msg: Message) -> None:
        self.history.append(msg)
        if len(self.history) > self.HISTORY_CAP:
            self.history = self.history[-self.HISTORY_CAP :]
        if msg.from_boba:
            self.last_boba_ts = msg.ts
            self.turns_since_boba = 0
            self.boba_msgs_window.append(msg.ts)
        elif msg.sender_kind == SenderKind.HUMAN:
            self.turns_since_boba += 1

    def open_boba_loop(self) -> Optional[OpenLoop]:
        for lp in reversed(self.open_loops):
            if lp.owner == SenderKind.BOBA and lp.status == "open":
                return lp
        return None


@dataclass
class Signals:
    """Extracted features for a single incoming message + thread context."""
    is_question: bool = False
    intent: Intent = Intent.CHITCHAT
    mentions_boba: bool = False
    reply_to_boba: bool = False
    is_dm: bool = False
    is_dismiss: bool = False
    addressed: str = "group"        # 'group' | 'individual' | 'boba'
    unanswered_question: bool = False
    velocity_high: bool = False     # fast banter → stay out
    humans_converging: bool = False
    recently_ignored: int = 0
    answers_open_loop: bool = False


@dataclass
class Decision:
    speak: bool
    decided_by: Stage
    intent: Intent = Intent.CHITCHAT
    response_type: ResponseType = ResponseType.NONE
    confidence: float = 0.0
    reason: str = ""
    defer_seconds: float = 0.0      # >0 → hold in debounce before sending

    @property
    def deferred(self) -> bool:
        return self.speak and self.defer_seconds > 0

    @classmethod
    def silent(cls, by: Stage, reason: str, conf: float = 0.0) -> "Decision":
        return cls(speak=False, decided_by=by, reason=reason, confidence=conf)
