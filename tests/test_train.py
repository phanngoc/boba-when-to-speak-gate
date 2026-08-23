from boba_gate import Conversation, Gate, Message, SenderKind, Thread
from boba_gate.gate.stage1_classifier import TrainedLinearClassifier
from boba_gate.train import (DEFAULT_DATA, example_to_signals, save_weights,
                             train_from_jsonl)


def test_weights_have_sane_signs():
    m = train_from_jsonl(DEFAULT_DATA)
    w = m["weights"]
    assert m["bias"] < 0                                  # default lean silent
    assert w["planning"] > 0
    assert w["explicit_request"] > 0
    assert w["deadlock"] > 0
    assert w["mentions_boba"] > 0


def test_trained_classifier_ranks_speak_over_silent():
    m = train_from_jsonl(DEFAULT_DATA)
    clf = TrainedLinearClassifier(m["weights"], m["bias"])
    speak = example_to_signals({"text": "tối nay đi đâu ăn ta?", "context": [],
                                "addressed": "group"})
    silent = example_to_signals({"text": "haha ông này hài vãi", "context": [],
                                 "addressed": "group"})
    p_speak, _ = clf.predict(speak)
    p_silent, _ = clf.predict(silent)
    assert p_speak > 0.5 > p_silent


def test_load_and_plug_into_gate(tmp_path):
    p = tmp_path / "w.json"
    save_weights(train_from_jsonl(DEFAULT_DATA), p)
    clf = TrainedLinearClassifier.load(p)
    g = Gate(classifier=clf)
    th = Thread("g", group_size=5)
    c = Conversation(g, th)
    evs = c.feed(Message("g", "a", "haha ông này hài vãi", 1000,
                         sender_kind=SenderKind.HUMAN, msg_id="a1"))
    assert evs[0].kind == "silent"
