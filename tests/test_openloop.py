from boba_gate.gate import openloop
from boba_gate.models import Message, SenderKind, Thread


def boba(text, ts):
    return Message("t", "boba", text, ts, sender_kind=SenderKind.BOBA, msg_id=f"b{int(ts)}")


def human(text, ts):
    return Message("t", "u", text, ts, sender_kind=SenderKind.HUMAN, msg_id=f"h{int(ts)}")


def _open(th, text, ts=100):
    m = boba(text, ts)
    th.append(m)
    return openloop.register_from_boba(th, m)


def test_register_choice_loop():
    th = Thread("t")
    lp = _open(th, "mọi người muốn ăn khu nào?")
    assert lp is not None and lp.kind == "choice" and th.open_boba_loop() is lp


def test_register_time_loop():
    th = Thread("t")
    lp = _open(th, "mấy giờ tập trung được?")
    assert lp.kind == "time"


def test_no_loop_for_statement():
    th = Thread("t")
    assert _open(th, "ok chốt nha.") is None


def test_is_answer_choice():
    th = Thread("t")
    _open(th, "ăn khu nào?")
    assert openloop.is_answer(human("quán hải sản gần biển đi", 110), th) is not None


def test_is_answer_time():
    th = Thread("t")
    _open(th, "mấy giờ tập trung?")
    assert openloop.is_answer(human("7h tối nhé", 110), th) is not None


def test_is_answer_confirm():
    th = Thread("t")
    _open(th, "đi ăn luôn được không?")
    assert openloop.is_answer(human("ừ ok", 110), th) is not None


def test_question_is_not_a_choice_answer():
    th = Thread("t")
    _open(th, "ăn khu nào?")
    assert openloop.is_answer(human("khu nào ngon vậy?", 110), th) is None


def test_resolve_and_human_answered_since():
    th = Thread("t")
    lp = _open(th, "ăn khu nào?")
    ans = human("hải sản đi", 110)
    th.append(ans)
    assert openloop.human_answered_since(th, 105.0)
    openloop.resolve(th, lp, SenderKind.HUMAN, 110)
    assert lp.status == "resolved" and th.open_boba_loop() is None
