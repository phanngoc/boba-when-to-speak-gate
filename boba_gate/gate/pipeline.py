"""The gate orchestrator — glues stage 0 → 1 → 2 → debounce.

`Gate.handle(msg, thread)` returns a `Decision` for one incoming message and
updates thread state (history, open loops, feedback). `Gate.record_boba_utterance`
is the outbound side: it appends Boba's message and opens a loop if Boba asked a
question (feature iii).

`Conversation` is a synchronous driver that also models the debounce timer
firing between messages — used by the demo and tests without asyncio.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..config import DEFAULT, GateConfig
from ..models import (Decision, Intent, Message, PendingSpeak, ResponseType,
                      SenderKind, Stage, Thread)
from . import debounce, openloop, signals, thresholds
from .stage0_rules import evaluate as stage0_evaluate
from .stage1_classifier import ClassifierBase, LinearClassifier
from .stage2_judge import JudgeBase, RuleBasedJudge

_INTENT_RTYPE = {
    Intent.PLANNING: ResponseType.SUGGEST_PLAN,
    Intent.DECISION_DEADLOCK: ResponseType.SETTLE_DEBATE,
    Intent.EXPLICIT_REQUEST: ResponseType.FULFILL_REQUEST,
}


def _intent_rtype(intent: Intent) -> ResponseType:
    return _INTENT_RTYPE.get(intent, ResponseType.DIRECT)


class Gate:
    def __init__(self, cfg: GateConfig = DEFAULT,
                 classifier: Optional[ClassifierBase] = None,
                 judge: Optional[JudgeBase] = None):
        self.cfg = cfg
        self.classifier = classifier or LinearClassifier(cfg)
        self.judge = judge or RuleBasedJudge()

    # --- inbound ----------------------------------------------------------
    def handle(self, msg: Message, thread: Thread, now: Optional[float] = None) -> Decision:
        now = msg.ts if now is None else now

        # (iii) open-loop: did this human answer Boba's pending question?
        answered = openloop.is_answer(msg, thread)
        if answered is not None:
            openloop.resolve(thread, answered, SenderKind.HUMAN, now)

        thread.append(msg)
        sig = signals.extract(msg, thread, now, answers_open_loop=answered is not None)

        if sig.is_dismiss:
            thresholds.note_dismiss(thread, self.cfg)

        # Stage 0 — hard rules
        d0 = stage0_evaluate(msg, thread, sig, self.cfg, now)
        if d0 is not None:
            return self._finalize(d0, thread, now)

        # Stage 1 — cheap classifier + two-threshold band
        p, intent = self.classifier.predict(sig)
        if p < thread.theta_low:
            return self._finalize(
                Decision.silent(Stage.STAGE1_CLASSIFIER,
                                f"p={p:.2f} < θ_low={thread.theta_low:.2f}", p),
                thread, now)
        if p > thread.theta_high:
            dec = Decision(
                speak=True, decided_by=Stage.STAGE1_CLASSIFIER, intent=intent,
                response_type=_intent_rtype(intent), confidence=p,
                reason=f"p={p:.2f} > θ_high={thread.theta_high:.2f}",
                defer_seconds=debounce.debounce_delay(thread, self.cfg, now))
            return self._finalize(dec, thread, now)

        # uncertain band → escalate to LLM judge only if high-stakes
        if intent.value in self.cfg.high_stakes:
            return self._finalize(
                self.judge.evaluate(msg, thread, sig, self.cfg, now), thread, now)
        return self._finalize(
            Decision.silent(Stage.STAGE1_CLASSIFIER,
                            f"uncertain (p={p:.2f}) + low-stakes → silent", p),
            thread, now)

    def _finalize(self, dec: Decision, thread: Thread, now: float) -> Decision:
        if dec.deferred:
            thread.pending_speak = PendingSpeak(
                decision=dec, created_ts=now, fire_at=now + dec.defer_seconds)
        return dec

    # --- outbound (feature iii) ------------------------------------------
    def record_boba_utterance(self, thread: Thread, text: str, now: float) -> Message:
        """Call after Boba actually sends `text`. Appends it and opens a loop if
        Boba asked a question, so a later human answer is caught by Stage 0."""
        m = Message(thread_id=thread.thread_id, sender_id="boba", text=text, ts=now,
                    msg_id=f"boba-{int(now * 1000)}", sender_kind=SenderKind.BOBA)
        thread.append(m)
        openloop.register_from_boba(thread, m)
        thread.pending_speak = None
        return m

    def on_feedback(self, thread: Thread, positive: bool) -> None:
        thresholds.apply_feedback(thread, positive, self.cfg)


# --------------------------------------------------------------------------
# Synchronous driver that also fires the debounce timer between messages.
# --------------------------------------------------------------------------

@dataclass
class Event:
    kind: str          # 'silent' | 'deferred' | 'speak' | 'yield'
    text: str          # human-readable summary
    decision: Optional[Decision] = None
    boba_text: str = ""


class TemplateResponder:
    """Turns a SPEAK Decision into Boba's actual text. Real templates (not a
    stub); a clarifying reply is a QUESTION so it opens a loop (feature iii)."""

    def render(self, dec: Decision, msg: Message, thread: Thread) -> str:
        rt = dec.response_type
        if rt == ResponseType.CONTINUE:
            return "Ok chốt nha, mình note lại: hải sản gần biển, 7h tối 👌"
        if rt == ResponseType.SUGGEST_PLAN:
            return "Để mình giúp chốt — mọi người muốn ăn món gì / khu nào?"
        if rt == ResponseType.SETTLE_DEBATE:
            return "Hai lựa chọn đang 50-50, mình quay số hay để mình đề xuất 1 cái nhé?"
        if rt == ResponseType.FULFILL_REQUEST:
            return "Ok, mình làm ngay 🎨"
        return "Mình đây, để mình hỗ trợ nha."


class Conversation:
    """Feeds messages in order; models the debounce window firing between them."""

    def __init__(self, gate: Gate, thread: Thread,
                 responder: Optional[TemplateResponder] = None):
        self.gate = gate
        self.thread = thread
        self.responder = responder or TemplateResponder()

    def feed(self, msg: Message) -> list[Event]:
        events: list[Event] = []
        p = self.thread.pending_speak

        # 1) resolve any pending SPEAK relative to this incoming message
        if p is not None:
            if (msg.sender_kind == SenderKind.HUMAN and msg.ts < p.fire_at
                    and debounce.incoming_resolves(msg)):
                self.thread.pending_speak = None
                events.append(Event("yield", "⏹  Boba yields — a human resolved it first"))
            elif msg.ts >= p.fire_at:
                events.append(self._fire(p))

        # 2) process the incoming message
        dec = self.gate.handle(msg, self.thread, now=msg.ts)
        if dec.speak and not dec.deferred:
            events.append(self._speak(dec, msg, msg.ts, immediate=True))
        elif dec.deferred:
            events.append(Event("deferred",
                                f"⏳ deferred {dec.defer_seconds:.0f}s ({dec.decided_by.value}): {dec.reason}",
                                dec))
        else:
            events.append(Event("silent",
                                f"🔇 silent ({dec.decided_by.value}): {dec.reason}", dec))
        return events

    def _fire(self, p: PendingSpeak) -> Event:
        self.thread.pending_speak = None
        return self._speak(p.decision, None, p.fire_at, immediate=False)

    def _speak(self, dec: Decision, msg: Optional[Message], ts: float,
               immediate: bool) -> Event:
        text = self.responder.render(dec, msg, self.thread)
        self.gate.record_boba_utterance(self.thread, text, ts)
        tag = "🗣  speak" if immediate else "🗣  speak (after debounce)"
        return Event("speak",
                     f"{tag} [{dec.response_type.value}]: {dec.reason}",
                     dec, boba_text=text)
