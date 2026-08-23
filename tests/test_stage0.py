from boba_gate.config import DEFAULT
from boba_gate.gate.stage0_rules import evaluate
from boba_gate.models import (Intent, Message, ResponseType, SenderKind,
                              Signals, Thread)


def mk(text="hi", **kw):
    return Message("t", "u", text, ts=100.0, sender_kind=SenderKind.HUMAN,
                   msg_id="m1", **kw)


def test_dismiss_blocks():
    d = evaluate(mk("boba im đi"), Thread("t"), Signals(is_dismiss=True), DEFAULT, 100.0)
    assert d is not None and not d.speak


def test_muted_blocks():
    th = Thread("t", muted=True)
    d = evaluate(mk(), th, Signals(mentions_boba=True), DEFAULT, 100.0)
    assert d is not None and not d.speak


def test_mention_allows_direct():
    d = evaluate(mk("@boba"), Thread("t"), Signals(mentions_boba=True), DEFAULT, 100.0)
    assert d.speak and d.response_type == ResponseType.DIRECT and d.defer_seconds == 0


def test_dm_allows():
    d = evaluate(mk(), Thread("t", is_dm=True), Signals(is_dm=True), DEFAULT, 100.0)
    assert d.speak


def test_open_loop_continue():
    d = evaluate(mk(), Thread("t"), Signals(answers_open_loop=True), DEFAULT, 100.0)
    assert d.speak and d.response_type == ResponseType.CONTINUE


def test_cooldown_silences():
    th = Thread("t")
    th.turns_since_boba = 1
    d = evaluate(mk(), th, Signals(), DEFAULT, 100.0)
    assert d is not None and not d.speak and "cooldown" in d.reason


def test_rate_cap_silences():
    th = Thread("t")
    th.turns_since_boba = 10
    th.boba_msgs_window = [98.0, 99.0]      # 2 within 300s window
    d = evaluate(mk(), th, Signals(), DEFAULT, 100.0)
    assert d is not None and not d.speak and "rate" in d.reason


def test_pass_returns_none():
    th = Thread("t")
    th.turns_since_boba = 10
    d = evaluate(mk(), th, Signals(intent=Intent.PLANNING), DEFAULT, 100.0)
    assert d is None
