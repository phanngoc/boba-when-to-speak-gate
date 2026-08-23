# Labeling guide — Stage 1 "when to speak" classifier

Goal: train a cheap, fast classifier that outputs **P(should_speak)** and an
**intent** for a single incoming group-chat message, given light context. This
model is the funnel's middle stage: it must be cheap enough to run on *every*
message that passes the hard rules.

## What you are labeling
For each message (with the few prior messages as context), assign:

### 1. `speak_label` — the target
- `speak` — Boba would add clear value by responding now.
- `silent` — Boba should stay quiet.
- `escalate` — genuinely borderline / high-stakes; a human labeler is unsure.
  (At serve time these become the uncertain band routed to the LLM judge.)

**Bias rule (critical):** when torn between `speak` and `silent`, choose
`silent`. False positives (barge-ins) are penalized ~3× in eval.

### 2. `intent` — one of
| intent | Vietnamese cues |
|---|---|
| `planning` | đi ăn, đi đâu, tối nay, cuối tuần, chốt lịch, rảnh không, tụ tập, cà phê |
| `decision_deadlock` | cũng được, sao cũng được, không chốt được, ai quyết đi |
| `explicit_request` | vẽ, tạo ảnh, poster, làm bài hát, tra cứu, tính giúp |
| `question` | generic question not obviously Boba's job |
| `chitchat` | jokes, reactions, venting |
| `dismiss` | boba im đi, ồn quá, stop |

### 3. Context flags (features, not labels)
`addressed` = group / individual / boba · `unanswered_question` (a group Q left
hanging) · `humans_converging` (someone just proposed/"chốt") · `recently_ignored`.

## Positive labels (speak)
- Directly addressed: `@Boba`, reply to Boba, or a 1:1 DM. → almost always speak.
- A group planning question with no one answering: "tối nay đi đâu ăn ta?"
- An explicit creative/lookup request: "ai vẽ giúp cái poster đi".
- A stuck decision: "quán A hay B? cũng được á" (deadlock).
- A human answering Boba's own open question (continue the loop).

## Negative labels (silent) — the majority
- Chit-chat/jokes/reactions: "haha ông này hài vãi".
- Aimed at one person: "Nam ơi mai đi không?".
- Humans already converging: "thôi chốt quán Bụi đi".
- Sensitive/heated venting (unless addressed).
- Right after Boba spoke (cooldown) or after being dismissed.

## Class balance & sampling
Real group chats are ~90%+ `silent`. Do **not** rebalance to 50/50 — keep the
prior skewed and instead weight the loss / tune the decision threshold. Oversample
`escalate` and near-boundary cases for the judge-training set.

## Weak/auto labels (bootstrap before human labels)
- 👍 / ❤️ reaction or "thanks Boba" after a Boba msg → previous decision was good (+).
- Boba spoke and got 0 engagement for N turns, or a "stop"/mute → bad (−).
These implicit labels are **noisy** — use them to bootstrap, then verify a sample
by hand.

## Eval metrics (report all)
- **Barge-in rate** = false-positive speaks / total speaks (primary; keep low).
- **Helpful-speak rate** = speaks that got positive engagement.
- **Missed-help recall** = should-have-spoken that were silent.
- **Mute/kick rate** in A/B (the real-world proxy that dominates).

Run new thresholds in **shadow mode** first (log the decision, don't send) and
compare against what the group did on its own.

## JSONL schema (see ../data/labeled_examples.jsonl)
```json
{"text": "...", "context": ["prev1", "prev2"], "addressed": "group",
 "speak_label": "speak|silent|escalate", "intent": "planning", "notes": "..."}
```
