# From reference → production-class

This repo is a **reference gate**, not a production system. Below is the honest
gap analysis (mapped to the actual files) and a phased plan. Read together with
[VIETNAM_MARKET.md](./VIETNAM_MARKET.md) — for a Vietnamese product the transport
and compliance rows dominate everything else.

## Gap analysis

| Dimension | Current (reference) | Production requirement | Prio |
|---|---|---|---|
| **Transport** | ✅ started: `Gateway` interface + **Telegram adapter** (`transport.py`) | Add **Zalo OA / Mini App** adapter (the VN play); delivery retries, receipts, media, idempotency. | **P0** |
| **Classifier** (`stage1_classifier.py`) | ✅ started: trainer (`train.py`) + `TrainedLinearClassifier`; only 42 illustrative labels | Scale to thousands of labels with the real skewed prior; version + A/B weights; consider embedding/small-LM. | **P0** |
| **LLM judge** (`stage2_judge.py`) | `RuleBasedJudge` fallback + `LLMJudge` seam | Wire `LLMJudge` to a real model; add timeout, retry, cost cap, structured-output validation, circuit breaker → fallback. | **P0** |
| **State store** (`store.py`) | In-memory dict | Redis (hot thread state, pending debounce) + Postgres (history, loops, feedback). Per-thread isolation, TTL, eviction. | **P0** |
| **Compliance / consent** | ✅ started: `consent.py` (opt-in + data minimization) | Full **PDPL 91/2025 + Decree 356/2025**: VN data storage, local entity, DPIA/DPO, deletion pipeline, cross-border LLM transfer controls. | **P0 (VN)** |
| **Safety** | stage-0 rules outside LLM | Prompt-injection hardening (never let chat text change gate rules), PII minimization/redaction before the LLM, abuse/spam rate limits, jailbreak tests. | **P0** |
| **Debounce at scale** (`debounce.py`) | asyncio in one process | Durable timers (Redis sorted-set / a queue with delay, e.g. Temporal / SQS delay) so pending SPEAKs survive restarts and shard across workers. | **P1** |
| **Observability** | `reason` strings | Structured logs, metrics (barge-in rate, mute rate, stage-hit ratio, LLM cost/msg, p95 latency), tracing, **shadow-mode logging**. | **P1** |
| **Eval harness** | 41 unit tests | Labeled-transcript offline eval with the 3× FP penalty; shadow-mode replay; canary + online A/B on mute/kick rate. | **P1** |
| **Cost controls** | — | Budget per thread/day; downgrade to rules-only under load; cache; batch. Each message is a potential LLM call → guard unit economics. | **P1** |
| **Vietnamese NLP** (`signals.py`) | lexicon + accent rules | Real VN tokenizer/intent model (teencode, code-switching, region slang); the lexicon is a bootstrap, not production coverage. | **P1** |
| **Multi-tenancy / scale** | single `Gate` | Horizontal workers, sticky per-thread routing, backpressure, idempotent webhook handling (dedupe by message id), out-of-order reconstruction. | **P1** |
| **CI/CD & deploy** | ✅ started: GitHub Actions (pytest 3.10/3.12 + smoke) | Add lint, containerize, IaC, staged rollout, secrets mgmt. | **P2** |
| **Feedback loop** (`thresholds.py`) | hand-rule per thread | Contextual bandit / online learner; guard against feedback poisoning; global-model retrain pipeline from aggregated (consented) labels. | **P2** |

## Phased plan

**P0 — “can run for one real pilot group, legally.”**
Transport adapter (Zalo OA or Telegram) · trained-classifier v0 · real LLM judge with
fallback+cost cap · Redis/Postgres state · **PDPL consent flow + VN data storage +
local entity** · prompt-injection & PII hardening.

**P1 — “can scale past a few hundred groups.”**
Durable debounce · observability + shadow mode · offline+online eval · cost budgets ·
production VN NLP · multi-worker isolation + idempotent webhooks.

**P2 — “operable team-owned service.”**
CI/CD + IaC · bandit-based adaptation + retrain pipeline · dashboards/alerts on the
mute-rate SLO.

## What the reference already gets right (keep)
- The **asymmetric objective** (penalize barge-ins ~3× misses) and the **cascade**
  cost structure — these are the expensive design decisions and they're sound.
- **Safety rules live outside the LLM** (stage 0) — correct for injection resistance.
- **Open-loop tracking** and **debounce race-with-humans** — the two hardest UX bits.
- Pluggable `ClassifierBase` / `JudgeBase` interfaces — swap in trained/LLM parts
  without touching the pipeline.
