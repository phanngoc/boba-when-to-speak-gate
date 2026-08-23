"""Train the Stage-1 classifier and write data/classifier_weights.json.

    python scripts/train_classifier.py

Then use it in the gate:

    from boba_gate.gate.stage1_classifier import TrainedLinearClassifier
    from boba_gate import Gate
    clf = TrainedLinearClassifier.load("data/classifier_weights.json")
    gate = Gate(classifier=clf)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boba_gate.train import DEFAULT_OUT, main


def _fmt(model: dict) -> str:
    ws = sorted(model["weights"].items(), key=lambda kv: -abs(kv[1]))
    lines = [f"  bias = {model['bias']:+.3f}   (trained on n={model['n']})"]
    lines += [f"  {k:<20} {w:+.3f}" for k, w in ws]
    return "\n".join(lines)


if __name__ == "__main__":
    model = main()
    print("Trained Stage-1 classifier weights:")
    print(_fmt(model))
    print(f"\nSaved → {DEFAULT_OUT}")
