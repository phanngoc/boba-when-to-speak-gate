# Boba — When-to-Speak Gate 🫧

Reference implementation of the **"khi nào nói" (when-to-speak) gate** for an AI
agent that lives inside a group chat — the Boba / Poke / iMessage-assistant class
of product. The gate decides **whether the agent should speak at all** *before*
deciding what to say. In a friends' group chat, replying to everything is the
fastest way to get muted; the hard problem is knowing when to stay quiet.

> This repo is the **gate**, not the whole agent. It does not ship the iMessage
> transport (that's a Mac fleet / Sendblue / BlueBubbles concern) and its
> classifier is an interpretable stand-in, not a trained model. See
> [Limitations](#limitations). It is fully runnable and tested with **zero
> third-party dependencies** (Python 3.10+ stdlib).

> 📈 **Going to production / Vietnam market?** Read
> [`PRODUCTION.md`](./PRODUCTION.md) (reference → production-class gap analysis)
> and [`VIETNAM_MARKET.md`](./VIETNAM_MARKET.md) (why the iMessage model must
> pivot for VN: Zalo dominates but is closed to friend-group bots, Messenger
> group bots can't read history, and PDPL 91/2025 + data-localization apply).

---

## Vì sao cần cổng này? (The core idea)

Trong group chat, **sai lầm không đối xứng**:

| Sai lầm | Hệ quả | Chi phí |
|---|---|---|
| **False Positive** — chen ngang vô duyên | user mute / kick bot | ⚠️ **rất cao** |
| **False Negative** — im lúc đáng ra nên giúp | bỏ lỡ cơ hội | trung bình |

→ **Nguyên tắc số 1:** phạt "chen ngang" nặng hơn "bỏ lỡ". **Phân vân thì im.**
Đây là lý do mặc định là *im lặng*, và "nói" mới là ngoại lệ phải chứng minh.

Ràng buộc phụ: **chi phí** (đừng gọi LLM lớn cho *mọi* tin) và **độ trễ**.
Giải pháp: một **phễu 3 tầng** — lọc rẻ trước, đắt sau.

```
mỗi tin trong group
      │
┌─────▼──────────────────────────────────────┐
│ TẦNG 0 — HARD RULES (deterministic, ~0ms)   │  stage0_rules.py
│  ALLOW ngay | BLOCK ngay | else PASS ↓       │  (mute, dismiss, @mention, DM,
└─────┬───────────────────────────────────────┘   open-loop, cooldown, rate cap)
      │
┌─────▼──────────────────────────────────────┐
│ TẦNG 1 — CHEAP CLASSIFIER (~ms, rẻ)         │  stage1_classifier.py
│  P(speak) + intent → 2-ngưỡng bất đối xứng   │  (linear/logistic, interpretable)
│  P<θ_low SILENT · P>θ_high SPEAK · else ↓    │
└─────┬───────────────────────────────────────┘
      │ vùng phân vân + intent high-stakes
┌─────▼──────────────────────────────────────┐
│ TẦNG 2 — LLM JUDGE (~vài trăm ms, hiếm)     │  stage2_judge.py
│  full context + rubric → {speak, type, why}  │  (RuleBasedJudge fallback / LLMJudge)
└─────┬───────────────────────────────────────┘
      │ nếu SPEAK
┌─────▼──────────────────────────────────────┐
│ DEBOUNCE — chờ τ giây; nếu người tự trả lời  │  debounce.py
│  trước → HỦY (yield). else → responder gửi    │
└──────────────────────────────────────────────┘
```

Chi phí biên thấp vì đa số tin dừng ở Tầng 0/1; chỉ số ít chạm LLM.

---

## Ba tính năng trong repo này

Đây là câu trả lời cụ thể cho 3 yêu cầu (i)/(ii)/(iii):

### (i) Reference implementation: webhook → gate → debounce → send
- `boba_gate/gate/pipeline.py` — `Gate.handle()` chạy tầng 0→1→2 và trả `Decision`.
- `boba_gate/gate/debounce.py` — giữ quyết định SPEAK trong cửa sổ τ, **nhường**
  con người nếu họ tự chốt trước (`DebounceScheduler` async cho production;
  `Conversation` đồng bộ cho demo/test).
- `boba_gate/web.py` — FastAPI: parse webhook kiểu Sendblue → gate → gửi trả.

### (ii) Labeling + prompt cho classifier/judge (có ví dụ tiếng Việt)
- `prompts/judge_system.md` — rubric cho LLM judge (JSON-only, "phân vân thì im").
- `prompts/classifier_labeling.md` — hướng dẫn gán nhãn, taxonomy intent, class
  balance (~90% `silent`), weak labels, và **metric** (barge-in rate, mute rate…).
- `data/labeled_examples.jsonl` — 42 ví dụ tiếng Việt đã gán nhãn.

### (iii) Open-loop tracking (Boba tự theo dõi vòng hỏi của chính nó)
- `boba_gate/gate/openloop.py` — khi Boba hỏi một câu, nó **mở một loop**
  (`kind` = time / choice / confirm / open). Khi một người trả lời đúng loop đó,
  Tầng 0 **bắt buộc** Boba đáp lại (`response_type = continue`) — tránh lỗi kinh
  điển "bot hỏi rồi phớt lờ câu trả lời".

---

## Tín hiệu (signals) — Vietnamese-aware

`boba_gate/gate/signals.py` trích đặc trưng, có xử lý tiếng Việt (bỏ dấu, teencode,
ranh giới từ). Vài nhóm chính:

| Nhóm | Ví dụ tín hiệu | Ví dụ tiếng Việt |
|---|---|---|
| Cứng (tầng 0) | `@mention`, reply, DM, dismiss | `@Boba`, `boba im đi` |
| Ý định (trigger) | planning, deadlock, explicit request | `tối nay đi đâu ăn ta?`, `sao cũng được ai quyết đi`, `vẽ giúp poster` |
| Hội thoại | is_question, addressed_to | `mấy giờ?` · `Nam ơi …` (→ cá nhân, không phải Boba) |
| Ức chế (negative) | humans_converging, velocity_high, recently_ignored | `thôi chốt quán Bụi đi` |

> ⚠️ **Bẫy tiếng Việt đã xử lý:** "vẽ" (draw) và "về" (go home) đều bỏ dấu thành
> "ve" → dễ nhận nhầm là yêu cầu vẽ. Cue "vẽ"/"hát" được match **có dấu** để
> tránh false-positive (xem `test_no_false_explicit_request_on_substring`).

---

## Chạy thử

```bash
# 1) Demo — kịch bản group chat tiếng Việt (thuần stdlib, không cần cài gì)
python scripts/demo.py

# 2) Test (41 test)
python -m pytest -q

# 3) Web layer (tuỳ chọn) — cần FastAPI
pip install -r requirements.txt
uvicorn boba_gate.web:app --reload
#   POST /webhook  {group_id, from_number, content, date, ...}
#   POST /feedback {thread_id, positive}
```

---

## Ví dụ tường minh — chú giải từng dòng demo

Chạy `python scripts/demo.py` cho một nhóm 5 người bạn. Mỗi dòng chú giải cơ chế:

```
[1000] An: haha ông này hài vãi 😂
        🔇 silent (stage1_classifier): p=0.10 < θ_low=0.35
```
→ Tán gẫu, không tín hiệu nào → classifier cho p thấp → **im** (mặc định).

```
[1020] An: tối nay đi đâu ăn ta?
        ⏳ deferred 7s (stage1_classifier): p=0.77 > θ_high=0.72
[1030] Dũng: còn ai on ko
        🗣  speak (after debounce) [suggest_plan]
          └─ 🫧 Boba: Để mình giúp chốt — mọi người muốn ăn món gì / khu nào?
```
→ Câu hỏi **planning** cho cả nhóm: p vượt θ_high → SPEAK nhưng **hoãn 7s**
(debounce). Trong 7s không ai trả lời → Boba lên tiếng, và vì câu của Boba là
**câu hỏi** nên nó **mở một open-loop** (kind=`choice`).  ← *(i) + (iii)*

```
[1050] An: quán hải sản gần biển đi
        🗣  speak [continue]: answers Boba's open loop — must follow through
          └─ 🫧 Boba: Ok chốt nha, mình note lại: hải sản gần biển, 7h tối 👌
```
→ An trả lời đúng loop Boba mở → **Tầng 0 bắt buộc** Boba đáp (`continue`),
bỏ qua cooldown. Loop được đánh dấu `resolved`.  ← *(iii)*

```
[1400] An: trưa mai ăn gì nhỉ
        ⏳ deferred 6s (stage1_classifier): p=0.77 > θ_high=0.72
[1404] Bình: thôi ăn cơm tấm đầu ngõ đi
        ⏹  Boba yields — a human resolved it first
        🔇 silent (stage1_classifier): p=0.01 < θ_low=0.35
```
→ Lại một câu planning → SPEAK hoãn. Nhưng **trong cửa sổ debounce**, Bình tự
đề xuất chỗ ăn ("… đi") → Boba **nhường** (yield), không nói.  ← *(i) debounce race*

```
[1500] Chi: @Boba vẽ giúp cái poster cuối tuần đi
        🗣  speak [direct]: mentioned / replied to Boba
          └─ 🫧 Boba: Mình đây, để mình hỗ trợ nha.
[1510] Dũng: boba im đi phiền quá
        🔇 silent (stage0_rules): explicit dismiss by user
[1540] An: tối nay đi nhậu không
        🔇 silent (stage1_classifier): p=0.14 < θ_low=0.43
```
→ `@Boba` → **ALLOW cứng** (tầng 0), trả lời ngay. Rồi bị "im đi" → **BLOCK** +
**nâng ngưỡng** (adaptation). Ngay sau đó một câu planning *tương tự* câu ở đầu
(vốn sẽ SPEAK) giờ bị **im** vì `recently_ignored` kéo p xuống dưới θ_low mới
(0.43). ← *thread tự học "gu" nhóm*

```
final θ_low=0.43  θ_high=0.80  recently_ignored=2   # ngưỡng đã dịch lên sau khi bị mắng
```

---

## Dùng như thư viện

```python
from boba_gate import Gate, Conversation, Thread, Message, SenderKind

gate = Gate()                                  # dùng LinearClassifier + RuleBasedJudge mặc định
thread = Thread("group-42", group_size=5)
convo = Conversation(gate, thread)             # driver đồng bộ, tự lo debounce timer

msg = Message("group-42", "an", "tối nay đi đâu ăn ta?", ts=1000.0,
              sender_kind=SenderKind.HUMAN, msg_id="an-1")
for ev in convo.feed(msg):
    print(ev.kind, "→", ev.text)               # 'deferred' / 'speak' / 'silent' / 'yield'
```

Cắm LLM thật cho Tầng 2:

```python
from boba_gate.gate.stage2_judge import LLMJudge, make_llm_call_from_json_string

def my_llm(system, user):                      # gọi Claude/GPT của bạn, trả text JSON
    return call_anthropic(system=system, user=user)

judge = LLMJudge(make_llm_call_from_json_string(my_llm))
gate = Gate(judge=judge)                        # cùng interface, phần còn lại không đổi
```

---

## Production add-ons (P0)

Những mảnh đầu tiên đưa reference tiến gần production (xem [`PRODUCTION.md`](./PRODUCTION.md)):

**1. Transport có thể thay thế + adapter Telegram** (`transport.py`) — kênh *duy nhất*
có Group Bot API mở để đọc mọi tin (xem [`VIETNAM_MARKET.md`](./VIETNAM_MARKET.md)):
```python
from boba_gate import TelegramGateway
gw = TelegramGateway(token="…", bot_username="boba_bot")   # tạo bot + TẮT privacy mode
msg = gw.parse(update)          # webhook Telegram → Message (tự nhận @mention/reply)
await gw.send(msg.thread_id, "chào cả nhà")
```

**2. Train classifier từ nhãn** (`train.py`) — dùng đúng feature của production:
```bash
python scripts/train_classifier.py          # → data/classifier_weights.json
```
```python
from boba_gate import Gate, TrainedLinearClassifier
clf = TrainedLinearClassifier.load("data/classifier_weights.json")
gate = Gate(classifier=clf)                  # cùng interface, thay thẳng
```
> ⚠️ Chỉ 42 ví dụ minh hoạ → weights *đúng hướng* nhưng **chưa đủ mạnh cho prod**
> (cần vài nghìn nhãn theo prior thật ~90% `silent`). Mặc định `Gate()` vẫn dùng
> `LinearClassifier` gán tay.

**3. Consent PDPL** (`consent.py`, xem [`COMPLIANCE_VN.md`](./COMPLIANCE_VN.md)) —
không có consent thì **không xử lý/lưu** tin (data minimization):
```python
from boba_gate import Gate, ConsentStore
gate = Gate(consent=ConsentStore())          # im lặng + không lưu tới khi nhóm "Boba đồng ý"
```

**4. CI** — `.github/workflows/ci.yml` chạy pytest (3.10/3.12) + smoke demo/train.

---

## Cấu trúc repo

```
boba_gate/
  models.py            # dataclasses: Message, Thread, Signals, Decision, OpenLoop
  config.py            # ngưỡng & trọng số (tunable)
  store.py             # ThreadStore in-memory (thay bằng Redis/PG khi lên prod)
  transport.py         # Gateway interface + Telegram adapter (P0)
  consent.py           # PDPL consent gating (P0)
  train.py             # train Stage-1 classifier từ nhãn (P0)
  web.py               # FastAPI webhook layer (tuỳ chọn)
  gate/
    signals.py         # trích tín hiệu (Vietnamese-aware, xử lý đ→d)
    stage0_rules.py    # (0) hard rules
    stage1_classifier.py # (1) cheap classifier — linear + TrainedLinearClassifier
    stage2_judge.py    # (2) LLM judge + fallback
    openloop.py        # (iii) open-loop tracking
    debounce.py        # (i)  debounce / race-with-humans
    thresholds.py      # feedback adaptation per-thread
    pipeline.py        # orchestrator: Gate + Conversation + responder
prompts/               # (ii) judge rubric + labeling guide
data/                  # (ii) 42 ví dụ tiếng Việt đã gán nhãn + classifier_weights.json
scripts/               # demo.py + train_classifier.py
tests/                 # 41 test
PRODUCTION.md · VIETNAM_MARKET.md · COMPLIANCE_VN.md   # roadmap + phân tích thị trường + PDPL
```

---

## Limitations

Honest caveats — đây là **reference/MVP**, không phải hệ thống production:

- **Classifier là mô hình tuyến tính gán trọng số bằng tay**, không phải model
  huấn luyện. Nó minh hoạ đúng thiết kế và có cùng interface (`ClassifierBase`)
  để thay bằng small-LM/embedding đã train. Trọng số & ngưỡng trong `config.py`
  là **minh hoạ, cần tune bằng dữ liệu thật**.
- **Không kèm transport iMessage/RCS** (Mac fleet, Sendblue, BlueBubbles). `web.py`
  chỉ có seam `send_to_gateway` để cắm provider.
- **RuleBasedJudge là fallback tất định** để chạy không cần API key; production nên
  dùng `LLMJudge` với model thật.
- Nhận dạng tiếng Việt dựa trên lexicon + heuristic, chưa phủ hết teencode/vùng miền.
- Chưa xử lý: prompt-injection nâng cao, out-of-order webhook, đa bot đối thoại
  vòng lặp (đã nêu trong thiết kế nhưng ngoài phạm vi bản này).

Không phải lời khuyên vận hành. MIT License.
