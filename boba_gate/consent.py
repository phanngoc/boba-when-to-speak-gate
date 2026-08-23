"""PDPL consent gating (Vietnam).

A group-chat AI that reads every message is **high-risk personal-data
processing** under Vietnam's PDPL (Law 91/2025, effective 2026-01-01). Before
processing a group's messages we must have explicit consent, honor revocation,
and minimize data when consent is absent.

This is a minimal, real model of that boundary:
  * `ConsentStore` tracks per-thread consent state.
  * When wired into `Gate(consent=...)`, messages from a non-consented thread are
    NOT stored/processed (data minimization) — the gate only listens for an
    explicit opt-in phrase that grants consent.

See COMPLIANCE_VN.md for the full data model, retention, and data-subject rights.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Optional

from .gate import signals


class ConsentState(str, Enum):
    PENDING = "pending"
    GRANTED = "granted"
    REVOKED = "revoked"


@dataclass
class ConsentRecord:
    thread_id: str
    state: ConsentState = ConsentState.PENDING
    granted_by: Optional[str] = None
    granted_ts: Optional[float] = None
    revoked_ts: Optional[float] = None
    purpose: str = "group coordination assistant"
    retention_days: int = 90


# Opt-in / opt-out phrases (accent-insensitive). In production, prefer an
# out-of-band admin flow; a chat phrase is the bootstrap fallback.
_OPTIN = ["boba dong y", "dong y cho boba", "/consent", "bat boba", "cho phep boba"]
_OPTOUT = ["boba tat di", "/revoke", "rut dong y", "xoa du lieu boba"]


def is_optin(text: str) -> bool:
    return signals._wany(signals.norm(text), _OPTIN)


def is_optout(text: str) -> bool:
    return signals._wany(signals.norm(text), _OPTOUT)


class ConsentStore:
    def __init__(self):
        self._c: Dict[str, ConsentRecord] = {}

    def record(self, thread_id: str) -> ConsentRecord:
        return self._c.setdefault(thread_id, ConsentRecord(thread_id))

    def is_allowed(self, thread_id: str) -> bool:
        r = self._c.get(thread_id)
        return r is not None and r.state == ConsentState.GRANTED

    def grant(self, thread_id: str, by: str, ts: float) -> ConsentRecord:
        r = self.record(thread_id)
        r.state = ConsentState.GRANTED
        r.granted_by = by
        r.granted_ts = ts
        return r

    def revoke(self, thread_id: str, ts: float) -> ConsentRecord:
        r = self.record(thread_id)
        r.state = ConsentState.REVOKED
        r.revoked_ts = ts
        return r
