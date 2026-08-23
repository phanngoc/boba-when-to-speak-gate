"""Train the Stage-1 classifier from labeled examples (pure stdlib).

Reads data/labeled_examples.jsonl, builds each example's feature vector through
the SAME `signals` pipeline production uses (so train/serve features match), and
fits a logistic regression by gradient descent. Emits weights consumable by
`TrainedLinearClassifier`.

Soft labels: speak→1.0, escalate→0.6, silent→0.0 (the escalate band sits between
speak and silent). Deterministic (zero init, no randomness) so CI is stable.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Optional

from .gate import openloop, signals
from .gate.stage1_classifier import FEATURE_KEYS, indicators
from .models import Message, SenderKind, Thread

_LABEL_TARGET = {"speak": 1.0, "escalate": 0.6, "silent": 0.0}


def _sigmoid(x: float) -> float:
    if x < -60:
        return 0.0
    if x > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def example_to_signals(ex: dict) -> signals.Signals:
    """Rebuild thread context from an example and extract the same Signals the
    live gate would compute. Context entries prefixed 'Boba:' become Boba
    messages (opening a loop) so the `answers_open_loop` feature is realistic."""
    thread = Thread(thread_id="train", group_size=5)
    ts = 100.0
    for c in ex.get("context", []):
        ts += 10.0
        if c.startswith("Boba:"):
            bm = Message("train", "boba", c[len("Boba:"):].strip(), ts,
                         sender_kind=SenderKind.BOBA, msg_id=f"b{int(ts)}")
            thread.append(bm)
            openloop.register_from_boba(thread, bm)
        else:
            thread.append(Message("train", "u", c, ts,
                                  sender_kind=SenderKind.HUMAN, msg_id=f"h{int(ts)}"))
    ts += 10.0
    target = Message("train", "u", ex["text"], ts,
                     sender_kind=SenderKind.HUMAN, msg_id=f"t{int(ts)}")
    answered = openloop.is_answer(target, thread)
    if answered is not None:
        openloop.resolve(thread, answered, SenderKind.HUMAN, ts)
    return signals.extract(target, thread, ts, answers_open_loop=answered is not None)


def load_dataset(path) -> list[tuple[dict, float]]:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        ex = json.loads(line)
        y = _LABEL_TARGET.get(ex.get("speak_label", "silent"), 0.0)
        x = indicators(example_to_signals(ex))
        rows.append((x, y))
    return rows


def train_from_jsonl(path, epochs: int = 1500, lr: float = 0.3,
                     l2: float = 1e-3) -> dict:
    data = load_dataset(path)
    weights = {k: 0.0 for k in FEATURE_KEYS}
    bias = 0.0
    n = max(1, len(data))
    for _ in range(epochs):
        gw = {k: 0.0 for k in FEATURE_KEYS}
        gb = 0.0
        for x, y in data:
            z = bias + sum(weights[k] * x.get(k, 0.0) for k in FEATURE_KEYS)
            err = _sigmoid(z) - y
            for k in FEATURE_KEYS:
                gw[k] += err * x.get(k, 0.0)
            gb += err
        for k in FEATURE_KEYS:
            weights[k] -= lr * (gw[k] / n + l2 * weights[k])
        bias -= lr * (gb / n)
    return {"weights": weights, "bias": bias, "ignored_cap": 3, "n": len(data)}


def save_weights(model: dict, path) -> None:
    Path(path).write_text(json.dumps(model, indent=2, ensure_ascii=False),
                          encoding="utf-8")


DEFAULT_DATA = Path(__file__).resolve().parent.parent / "data" / "labeled_examples.jsonl"
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "classifier_weights.json"


def main(data: Optional[Path] = None, out: Optional[Path] = None) -> dict:
    model = train_from_jsonl(data or DEFAULT_DATA)
    save_weights(model, out or DEFAULT_OUT)
    return model
