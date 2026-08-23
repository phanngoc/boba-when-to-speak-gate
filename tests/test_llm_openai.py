from boba_gate.config import DEFAULT
from boba_gate.gate.stage2_judge import LLMJudge
from boba_gate.llm_openai import make_openai_call
from boba_gate.models import Intent, Message, SenderKind, Signals, Thread


def _fake_ok(url, payload, api_key, timeout):
    # sanity: request is JSON-mode chat completion with two messages
    assert payload["response_format"] == {"type": "json_object"}
    assert len(payload["messages"]) == 2 and api_key == "KEY"
    return {"choices": [{"message": {"content":
            '{"should_speak": true, "intent": "planning", '
            '"confidence": 0.8, "defer_seconds": 5, "reason": "clear plan Q"}'}}]}


def _msg():
    return Message("g", "a", "tối nay đi đâu ăn ta?", 1000,
                   sender_kind=SenderKind.HUMAN, msg_id="a1")


def test_make_call_parses_json_content():
    out = make_openai_call("KEY", http_post=_fake_ok)("sys", "user")
    assert out["should_speak"] is True and out["intent"] == "planning"


def test_llm_judge_speaks_on_ok():
    judge = LLMJudge(make_openai_call("KEY", http_post=_fake_ok))
    sig = Signals(intent=Intent.PLANNING, is_question=True, addressed="group")
    dec = judge.evaluate(_msg(), Thread("g", group_size=5), sig, DEFAULT, 1000.0)
    assert dec.speak and dec.intent == Intent.PLANNING


def test_llm_judge_falls_back_on_error():
    def boom(*a, **k):
        raise RuntimeError("network down")

    judge = LLMJudge(make_openai_call("KEY", http_post=boom))
    sig = Signals(intent=Intent.PLANNING)
    dec = judge.evaluate(_msg(), Thread("g", group_size=5), sig, DEFAULT, 1000.0)
    assert dec.speak and "fallback" in dec.reason      # RuleBasedJudge kicked in
