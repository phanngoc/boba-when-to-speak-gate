# DESIGN — When-to-Speak Gate

Engineering rationale behind the code. The README shows *how it behaves*; this
doc records *why it is built this way*.

## Objective function

The gate optimizes a deliberately **asymmetric** target:

- A **false positive** (barging in wrongly) is penalized ~3× a **false negative**
  (staying silent when it could have helped). Wrong interjections get the bot
  muted or removed; missed ones are barely noticed.
- Therefore **precision ≫ recall**, and the default action is **silence**.
- Secondary constraints: **cost** (don't invoke a large LLM per message) and
  **latency** (texting UX expects fast turns; no token streaming over iMessage/SMS).

The real-world proxy metric that dominates is **mute/kick rate**, not offline F1.

## Why a cascade (funnel), not one model

Running one LLM on every message is too expensive and too slow. The funnel routes
by cost:

| Stage | Cost | Runs on | Job |
|---|---|---|---|
| 0 — hard rules | ~0 | every msg | instant ALLOW/BLOCK; carries safety rules (mute, rate cap) that must live **outside** any LLM (prompt-injection safe) |
| 1 — cheap classifier | ms | msgs passing stage 0 | P(speak)+intent; two-threshold band |
| 2 — LLM judge | 100s ms | only uncertain **and** high-stakes | full-context rubric decision |

Illustrative traffic split: ~70% resolved at stage 0, ~25% at stage 1, ~5% reach
stage 2. That keeps marginal cost low enough for a free product.

## Two-threshold band (stage 1)

`P < θ_low → silent`, `P > θ_high → speak`, in-between → escalate to the judge
*only if the intent is high-stakes* (planning / deadlock / explicit request);
otherwise stay silent. `θ_high` sits high (~0.72+) because speaking must be
confident. The band avoids paying for the LLM on clear-cut messages.

## Debounce — the race with humans

Even a SPEAK decision is **held for τ seconds**. If, during τ, a human resolves
the thread (proposes a place/time, says "chốt …"), the pending SPEAK is
**cancelled**. This is what makes the agent feel like it "waits until needed"
rather than pouncing. τ scales up with conversation velocity (more chatter → more
likely a human answers first). See `debounce.py`.

The cancel predicate (`signals.looks_like_resolution`) is shared with the stage-1
`humans_converging` signal so the two never disagree.

## Open-loop tracking (feature iii)

When Boba asks a question, it records an `OpenLoop` with an inferred `kind`
(time / choice / confirm / open). Incoming human messages are checked against the
open loop; a match is a **hard ALLOW** at stage 0 (`response_type = continue`),
bypassing cooldown — because ignoring an answer to your own question is the most
jarring bot failure. The loop is then marked `resolved`. See `openloop.py`.

Answer detection is kind-specific: `time` → a time expression; `choice` → a
non-question naming a place/food or a directive proposal; `confirm` → yes/no.

## Per-thread adaptation (feedback)

Each thread carries its own `θ_low/θ_high`. Cheap feedback nudges them online:

- positive (reaction, "thanks", group acted on the suggestion) → lower thresholds
- negative (ignored, "boba im đi", mute) → raise thresholds + bump `recently_ignored`

So a group that dislikes proactivity trains Boba quiet; one that likes it trains it
forward. A contextual bandit can replace the hand-rule in `thresholds.py`.

## Evaluation plan (not shipped, but this is how you'd validate)

1. **Offline** on labeled transcripts — report barge-in rate (primary), missed-help
   recall, weighted with the 3× FP penalty.
2. **Shadow mode** — log what the gate *would* send without sending; compare to
   what the group did unaided. Tune thresholds here before going live.
3. **Online A/B** — the metric that matters is **mute/kick rate**, then
   helpful-engagement rate.

Class balance is heavily skewed (~90%+ silent in real chats); do **not** rebalance
to 50/50 — keep the prior and tune the threshold / weight the loss.

## Known gaps

Out of scope for this reference: advanced prompt-injection defense, out-of-order
webhook reconstruction, multi-bot loop suppression, media-only handling, and a
trained classifier. All are noted in the README's Limitations.
