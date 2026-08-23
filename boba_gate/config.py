"""Tunable knobs for the gate. All illustrative defaults — tune per product."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GateConfig:
    # --- rate limiting / cooldown -----------------------------------------
    cooldown_turns: int = 2          # stay quiet for N human turns after speaking
    max_boba_per_window: int = 2     # hard cap of Boba msgs...
    rate_window_s: float = 300.0     # ...within this window (seconds)

    # --- debounce (race with humans) --------------------------------------
    debounce_base_s: float = 6.0     # base wait before a deferred SPEAK fires
    debounce_min_s: float = 3.0
    debounce_max_s: float = 12.0

    # --- classifier bias / weights (linear, interpretable) ----------------
    # Encodes the design: default lean silent (negative bias); planning /
    # explicit requests push up; individual-address / converging push down.
    bias: float = -2.2
    w_planning: float = 2.2
    w_deadlock: float = 2.0
    w_explicit_request: float = 2.5
    w_question_group: float = 1.2
    w_unanswered: float = 0.8
    w_addressed_individual: float = -2.6
    w_velocity_high: float = -1.2
    w_humans_converging: float = -3.0
    w_recently_ignored: float = -1.5   # per ignore, capped
    recently_ignored_cap: int = 3

    # --- threshold adaptation (feedback) ----------------------------------
    theta_step_up: float = 0.08      # raise thresholds when ignored/dismissed
    theta_step_down: float = 0.04    # lower slightly when appreciated
    theta_high_floor: float = 0.55
    theta_high_ceil: float = 0.92
    theta_low_floor: float = 0.20
    theta_low_ceil: float = 0.55

    # high-stakes intents worth escalating to the (expensive) LLM judge
    high_stakes = ("planning", "decision_deadlock", "explicit_request")


DEFAULT = GateConfig()
