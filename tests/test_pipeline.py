from boba_gate import Conversation, Gate, Message, SenderKind, Thread


def H(text, ts, sender="An"):
    return Message("g", sender, text, ts, sender_kind=SenderKind.HUMAN,
                   msg_id=f"{sender}{int(ts)}")


def kinds(events):
    return [e.kind for e in events]


def fresh():
    g = Gate()
    th = Thread("g", group_size=5)
    return g, th, Conversation(g, th)


def test_chitchat_is_silent():
    _, _, c = fresh()
    assert kinds(c.feed(H("haha ông này hài vãi 😂", 1000))) == ["silent"]


def test_individual_address_is_silent():
    _, _, c = fresh()
    assert kinds(c.feed(H("Nam ơi mai rảnh không", 1000))) == ["silent"]


def test_planning_defers_then_speaks_and_opens_loop():
    _, th, c = fresh()
    c.feed(H("tối nay đi đâu ăn ta?", 1000))
    assert th.pending_speak is not None                 # held during debounce
    evs = c.feed(H("còn ai on ko", 1010))               # window elapsed → fire
    assert "speak" in kinds(evs)
    assert th.open_boba_loop() is not None              # (iii) Boba opened a loop


def test_open_loop_continue_when_human_answers():
    _, th, c = fresh()
    c.feed(H("tối nay đi đâu ăn ta?", 1000))
    c.feed(H("còn ai on ko", 1010))                     # Boba suggests (opens loop)
    evs = c.feed(H("quán hải sản gần biển đi", 1030))   # human answers the loop
    assert "speak" in kinds(evs)
    assert th.open_boba_loop() is None                  # loop resolved


def test_debounce_yields_when_human_resolves_first():
    _, th, c = fresh()
    c.feed(H("trưa mai ăn gì nhỉ", 2000))
    assert th.pending_speak is not None
    evs = c.feed(H("thôi ăn cơm tấm đầu ngõ đi", 2003)) # within window, resolves
    assert "yield" in kinds(evs)
    assert th.pending_speak is None


def test_mention_speaks_immediately():
    _, _, c = fresh()
    assert "speak" in kinds(c.feed(H("@Boba giúp mình với", 5000)))


def test_dismiss_raises_threshold_and_then_silences_planning():
    g, th, c = fresh()
    base_high = th.theta_high
    c.feed(H("boba im đi phiền quá", 3000))
    assert th.theta_high > base_high and th.recently_ignored >= 2
    # a planning message that would normally pass is now suppressed
    assert kinds(c.feed(H("tối nay đi nhậu không", 3100))) == ["silent"]
