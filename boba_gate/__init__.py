"""Boba When-to-Speak Gate — reference implementation.

Public surface:
    from boba_gate import Gate, Conversation, Thread, Message, SenderKind
"""
from .config import DEFAULT, GateConfig
from .models import (Decision, Intent, Message, OpenLoop, ResponseType,
                     SenderKind, Signals, Stage, Thread)
from .gate.pipeline import Conversation, Event, Gate, TemplateResponder
from .store import ThreadStore

__all__ = [
    "Gate", "Conversation", "Event", "TemplateResponder", "ThreadStore",
    "Thread", "Message", "OpenLoop", "Signals", "Decision",
    "Intent", "ResponseType", "Stage", "SenderKind",
    "GateConfig", "DEFAULT",
]
