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


# --- raw features for TRAINING a classifier ---------------------------------
# Keys are the learnable feature space (see boba_gate/train.py). Values are raw
# indicators (0/1 or small counts) — the trainer learns the weights.
FEATURE_KEYS = [
    "planning", "deadlock", "explicit_request", "question_group", "unanswered",
    "addressed_individual", "velocity_high", "humans_converging",
    "recently_ignored", "mentions_boba", "is_dm", "is_question",
]


def indicators(sig: Signals, ignored_cap: int = 3) -> dict[str, float]:
    return {
        "planning": float(sig.intent == Intent.PLANNING),
        "deadlock": float(sig.intent == Intent.DECISION_DEADLOCK),
        "explicit_request": float(sig.intent == Intent.EXPLICIT_REQUEST),
        "question_group": float(sig.is_question and sig.addressed == "group"),
        "unanswered": float(sig.unanswered_question),
        "addressed_individual": float(sig.addressed == "individual"),
        "velocity_high": float(sig.velocity_high),
        "humans_converging": float(sig.humans_converging),
        "recently_ignored": float(min(sig.recently_ignored, ignored_cap)),
        "mentions_boba": float(sig.mentions_boba),
        "is_dm": float(sig.is_dm),
        "is_question": float(sig.is_question),
    }


class TrainedLinearClassifier:
    """Logistic model with LEARNED weights (from train.py). Same interface as
    LinearClassifier, so `Gate(classifier=...)` swaps it in unchanged."""

    def __init__(self, weights: dict[str, float], bias: float,
                 ignored_cap: int = 3):
        self.weights = weights
        self.bias = bias
        self.ignored_cap = ignored_cap

    def predict(self, sig: Signals) -> tuple[float, Intent]:
        x = indicators(sig, self.ignored_cap)
        z = self.bias + sum(self.weights.get(k, 0.0) * v for k, v in x.items())
        return _sigmoid(z), sig.intent

    @classmethod
    def load(cls, path) -> "TrainedLinearClassifier":
        import json
        from pathlib import Path
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data["weights"], data["bias"], data.get("ignored_cap", 3))
