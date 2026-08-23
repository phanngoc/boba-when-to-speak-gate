from boba_gate.gate import signals as s
from boba_gate.models import Intent, Thread


def test_is_question_vietnamese():
    assert s.is_question("tối nay đi đâu ăn ta?")
    assert s.is_question("mấy giờ tập trung")       # "mấy giờ" without '?'
    assert s.is_question("ai đi không")             # "ai", "không"
    assert not s.is_question("đói quá")
    assert not s.is_question("ok chốt nha")


def test_detect_intent():
    assert s.detect_intent("tối nay đi đâu ăn ta?") == Intent.PLANNING
    assert s.detect_intent("boba im đi") == Intent.DISMISS
    assert s.detect_intent("vẽ giúp cái poster") == Intent.EXPLICIT_REQUEST
    assert s.detect_intent("sao cũng được, ai quyết đi") == Intent.DECISION_DEADLOCK
    assert s.detect_intent("haha ông này hài vãi") == Intent.CHITCHAT


def test_no_false_explicit_request_on_substring():
    # "về" (ve) must NOT trigger the 'vẽ' (draw) request cue
    assert s.detect_intent("trời ơi về nhà thôi") != Intent.EXPLICIT_REQUEST


def test_mentions_and_dismiss():
    assert s.mentions_boba("@Boba giúp với")
    assert s.mentions_boba("boba ơi")
    assert s.is_dismiss("boba im đi ồn quá")
    assert not s.is_dismiss("boba giúp mình nhé")


def test_looks_like_resolution():
    assert s.looks_like_resolution("thôi chốt quán Bụi đi")
    assert s.looks_like_resolution("ăn cơm tấm đầu ngõ đi")
    assert s.looks_like_resolution("ok chốt luôn")
    assert not s.looks_like_resolution("đói quá")


def test_addressed_target():
    t = Thread("x")
    assert s.addressed_target("Nam ơi mai rảnh không", t) == "individual"
    assert s.addressed_target("tối nay đi đâu ăn ta?", t) == "group"
    assert s.addressed_target("@Boba giúp với", t) == "boba"
