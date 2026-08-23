"""Per-thread threshold adaptation (feedback learning).

Each group has its own taste: some want Boba proactive, some want it quiet. We
nudge the two thresholds online from cheap feedback signals:

  positive (reaction, "thanks", group acted on suggestion) → lower thresholds
  negative (ignored, dismissed, "stop")                    → raise thresholds

A trained contextual bandit could replace this; the update rule below is the
transparent reference version.
"""
from __future__ import annotations

from ..config import GateConfig
from ..models import Thread


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def apply_feedback(thread: Thread, positive: bool, cfg: GateConfig) -> None:
    if positive:
        thread.theta_high = _clamp(thread.theta_high - cfg.theta_step_down,
                                   cfg.theta_high_floor, cfg.theta_high_ceil)
        thread.theta_low = _clamp(thread.theta_low - cfg.theta_step_down,
                                  cfg.theta_low_floor, cfg.theta_low_ceil)
        thread.recently_ignored = max(0, thread.recently_ignored - 1)
    else:
        thread.theta_high = _clamp(thread.theta_high + cfg.theta_step_up,
                                   cfg.theta_high_floor, cfg.theta_high_ceil)
        thread.theta_low = _clamp(thread.theta_low + cfg.theta_step_up,
                                  cfg.theta_low_floor, cfg.theta_low_ceil)
        thread.recently_ignored += 1


def note_dismiss(thread: Thread, cfg: GateConfig) -> None:
    """Strong negative — an explicit 'Boba im đi'."""
    apply_feedback(thread, positive=False, cfg=cfg)
    thread.recently_ignored += 1  # count dismiss extra
