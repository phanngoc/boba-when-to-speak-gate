# PDPL compliance model (Vietnam)

A group-chat agent that reads every message is **high-risk personal-data
processing** under Vietnam's **PDPL — Law 91/2025/QH15** (effective 2026-01-01,
guided by **Decree 356/2025/NĐ-CP**), on top of **data-localization** duties
(Cybersecurity Law 2025 + Decree 53/2022). This doc sketches the data model the
service must implement. `boba_gate/consent.py` is the runnable core of the
consent boundary. **Not legal advice — engage Vietnamese counsel.**

## Hard requirements (map to build tasks)

| Requirement | What it means here | Where |
|---|---|---|
| **Consent before processing** | Must have explicit, purpose-bound consent to read a group's messages | `ConsentStore`, gate gate in `pipeline.py` |
| **Data minimization** | If no consent → do **not** store/process messages | gate returns silent *without* appending to history |
| **Revocation** | A group can withdraw consent; stop processing + delete on request | `ConsentStore.revoke` + deletion job (prod) |
| **Retention limit** | Keep messages only as long as needed (`retention_days`) | `ConsentRecord.retention_days` + TTL in store |
| **Data-subject rights** | Access / correction / deletion per member | prod: identity + export/delete endpoints |
| **Localization** | Store VN-user data **in Vietnam**; set up a local entity/branch | infra choice: VNG Cloud / Viettel / FPT |
| **Purpose limitation** | Use data only for the stated assistant purpose; never sell/ad-target | policy + `ConsentRecord.purpose` |

## Consent lifecycle (implemented)

```
PENDING ──(opt-in phrase / admin grant)──▶ GRANTED ──(revoke / delete req)──▶ REVOKED
   │                                          │
   └── messages NOT stored (minimization)     └── messages processed within retention
```

Opt-in phrases (bootstrap; prefer an out-of-band admin flow in prod):
`boba đồng ý`, `đồng ý cho boba`, `/consent`, `cho phép boba`.
Opt-out: `boba tắt đi`, `/revoke`, `rút đồng ý`, `xoá dữ liệu boba`.

```python
from boba_gate import Gate, ConsentStore
gate = Gate(consent=ConsentStore())   # now Boba stays silent+non-storing until a group opts in
```

## Still to build for production (P0)

- **Storage in VN** with encryption at rest + access logging.
- **PII minimization/redaction** before any text reaches an LLM (esp. cross-border
  LLM APIs — a cross-border transfer that PDPL restricts; prefer in-region models
  or redaction + DPIA).
- **DPIA / impact assessment** and a **DPO** where thresholds require.
- **Deletion pipeline** honoring retention + subject requests, incl. derived data
  (vector memory, feedback labels).
- **Consent records are themselves personal data** — store and protect accordingly.
