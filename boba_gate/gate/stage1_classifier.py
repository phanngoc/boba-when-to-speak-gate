"""Stage 1 — cheap classifier (~ms, runs on most messages).

Reference implementation is an INTERPRETABLE linear model (logistic on a small
feature vector). It is real and deterministic, encodes the design's weights, and
implements the same `ClassifierBase` interface a trained model would — so you can
drop in a fine-tuned small-LM / embedding classifier later without touching the
pipeline.

Output: P(speak) plus the intent. The pipeline applies the two-threshold band.
"""
from __future__ import annotations

import math
from typing import Protocol

from ..config import GateConfig
from ..models import Intent, Signals


class ClassifierBase(Protocol):
    def predict(self, sig: Signals) -> tuple[float, Intent]:
        """Return (P(speak) in [0,1], intent)."""
        ...


def _sigmoid(x: float) -> float:
    if x < -60:
        return 0.0
    if x > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


class LinearClassifier:
    """Hand-weighted logistic model. Transparent stand-in for a trained one."""

    def __init__(self, cfg: GateConfig):
        self.cfg = cfg

    def features(self, sig: Signals) -> dict[str, float]:
        c = self.cfg
        f: dict[str, float] = {"bias": c.bias}
        if sig.intent == Intent.PLANNING:
            f["planning"] = c.w_planning
        if sig.intent == Intent.DECISION_DEADLOCK:
            f["deadlock"] = c.w_deadlock
        if sig.intent == Intent.EXPLICIT_REQUEST:
            f["explicit_request"] = c.w_explicit_request
        if sig.is_question and sig.addressed == "group":
            f["question_group"] = c.w_question_group
        if sig.unanswered_question:
            f["unanswered"] = c.w_unanswered
        if sig.addressed == "individual":
            f["addressed_individual"] = c.w_addressed_individual
        if sig.velocity_high:
            f["velocity_high"] = c.w_velocity_high
        if sig.humans_converging:
            f["humans_converging"] = c.w_humans_converging
        if sig.recently_ignored > 0:
            n = min(sig.recently_ignored, c.recently_ignored_cap)
            f["recently_ignored"] = c.w_recently_ignored * n
        return f

    def predict(self, sig: Signals) -> tuple[float, Intent]:
        z = sum(self.features(sig).values())
        return _sigmoid(z), sig.intent
