"""Stage 2 — LLM judge (rare, full context).

Only runs when Stage 1 is in the uncertain band on a high-stakes intent. Two
implementations behind one interface:

  * `RuleBasedJudge` — deterministic fallback so the whole gate runs and tests
    with NO API key. It is a real judge (context-aware heuristics), not a stub.
  * `LLMJudge`      — production path. Loads the rubric from prompts/judge_system.md,
    calls an injected `llm_call(system, user) -> dict`, and falls back to the
    rule-based judge on any error. Wire your Claude/GPT client into `llm_call`.

Both return a `Decision`.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Optional, Protocol

from ..config import GateConfig
from ..models import Decision, Intent, Message, ResponseType, Signals, Stage, Thread
from . import signals as sig_mod

_INTENT_TO_RTYPE = {
    Intent.PLANNING: ResponseType.SUGGEST_PLAN,
    Intent.DECISION_DEADLOCK: ResponseType.SETTLE_DEBATE,
    Intent.EXPLICIT_REQUEST: ResponseType.FULFILL_REQUEST,
}


class JudgeBase(Protocol):
    def evaluate(self, msg: Message, thread: Thread, sig: Signals,
                 cfg: GateConfig, now: float) -> Decision:
        ...


class RuleBasedJudge:
    """Deterministic, context-aware fallback judge."""

    def evaluate(self, msg: Message, thread: Thread, sig: Signals,
                 cfg: GateConfig, now: float) -> Decision:
        s = Stage.STAGE2_JUDGE

        # Retreat if humans are already converging on the answer themselves.
        if sig.humans_converging:
            return Decision.silent(s, "humans converging — yield", conf=0.7)
        # Sensitive/emotional high-velocity exchanges: stay out unless addressed.
        if sig.velocity_high and not (sig.mentions_boba or sig.reply_to_boba):
            return Decision.silent(s, "fast/heated exchange — stay out", conf=0.6)
        # Been ignored repeatedly here → be more reticent.
        if sig.recently_ignored >= cfg.recently_ignored_cap:
            return Decision.silent(s, "repeatedly ignored in this thread", conf=0.6)

        if sig.intent in (Intent.PLANNING, Intent.DECISION_DEADLOCK,
                          Intent.EXPLICIT_REQUEST):
            rtype = _INTENT_TO_RTYPE[sig.intent]
            return Decision(
                speak=True, decided_by=s, intent=sig.intent, response_type=rtype,
                confidence=0.72,
                reason=f"high-stakes {sig.intent.value}, nobody resolving it",
                defer_seconds=_debounce(thread, cfg, now),
            )
        return Decision.silent(s, "no clear value to add", conf=0.5)


class LLMJudge:
    """Production judge. Delegates the actual reasoning to an injected LLM call."""

    def __init__(self, llm_call: Callable[[str, str], dict],
                 prompt_path: Optional[Path] = None):
        self.llm_call = llm_call
        self._fallback = RuleBasedJudge()
        p = prompt_path or Path(__file__).resolve().parents[2] / "prompts" / "judge_system.md"
        self.system_prompt = p.read_text(encoding="utf-8") if p.exists() else _DEFAULT_RUBRIC

    def evaluate(self, msg: Message, thread: Thread, sig: Signals,
                 cfg: GateConfig, now: float) -> Decision:
        try:
            user = self._render_context(msg, thread, sig)
            out = self.llm_call(self.system_prompt, user)
            if not out.get("should_speak"):
                return Decision.silent(Stage.STAGE2_JUDGE,
                                       out.get("reason", "judge: stay silent"),
                                       conf=float(out.get("confidence", 0.5)))
            intent = _coerce_intent(out.get("intent"), sig.intent)
            return Decision(
                speak=True, decided_by=Stage.STAGE2_JUDGE, intent=intent,
                response_type=_INTENT_TO_RTYPE.get(intent, ResponseType.DIRECT),
                confidence=float(out.get("confidence", 0.6)),
                reason=out.get("reason", "judge: speak"),
                defer_seconds=float(out.get("defer_seconds", _debounce(thread, cfg, now))),
            )
        except Exception as e:  # network / parse error → safe fallback
            dec = self._fallback.evaluate(msg, thread, sig, cfg, now)
            dec.reason = f"LLM judge fallback ({type(e).__name__}): {dec.reason}"
            return dec

    def _render_context(self, msg: Message, thread: Thread, sig: Signals) -> str:
        lines = ["Recent conversation (oldest→newest):"]
        for m in thread.history[-8:]:
            who = "BOBA" if m.from_boba else m.sender_id
            lines.append(f"  {who}: {m.text}")
        lines.append(f"New message from {msg.sender_id}: {msg.text}")
        lines.append(f"Signals: intent={sig.intent.value}, addressed={sig.addressed}, "
                     f"unanswered={sig.unanswered_question}, converging={sig.humans_converging}, "
                     f"ignored={sig.recently_ignored}")
        lines.append('Reply ONLY as JSON: {"should_speak": bool, "intent": str, '
                     '"confidence": float, "defer_seconds": number, "reason": str}')
        return "\n".join(lines)


def make_llm_call_from_json_string(fn: Callable[[str, str], str]) -> Callable[[str, str], dict]:
    """Adapt a raw text-returning LLM client into the dict interface LLMJudge wants."""
    def _call(system: str, user: str) -> dict:
        raw = fn(system, user).strip()
        if raw.startswith("```"):
            raw = raw.strip("`")
            raw = raw[raw.find("{"):]
        return json.loads(raw)
    return _call


def _debounce(thread: Thread, cfg: GateConfig, now: float) -> float:
    from .debounce import debounce_delay
    return debounce_delay(thread, cfg, now)


def _coerce_intent(value, default: Intent) -> Intent:
    try:
        return Intent(value)
    except (ValueError, TypeError):
        return default


_DEFAULT_RUBRIC = (
    "You are Boba, a polite guest in a close-friends group chat. Only speak when "
    "you genuinely add value and no human is about to answer. When in doubt, stay "
    "silent. Reply strictly as JSON."
)
