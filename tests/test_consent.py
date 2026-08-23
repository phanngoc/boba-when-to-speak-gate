from boba_gate import Conversation, Gate, Message, SenderKind, Thread
from boba_gate.consent import ConsentStore


def H(text, ts):
    return Message("g", "a", text, ts, sender_kind=SenderKind.HUMAN, msg_id=f"a{int(ts)}")


def kinds(events):
    return [e.kind for e in events]


def test_blocks_and_does_not_store_without_consent():
    g = Gate(consent=ConsentStore())
    th = Thread("g", group_size=5)
    c = Conversation(g, th)
    evs = c.feed(H("tối nay đi đâu ăn ta?", 1000))
    assert kinds(evs) == ["silent"]
    assert len(th.history) == 0          # PDPL data minimization: nothing stored


def test_optin_grants_then_normal_gating_resumes():
    cs = ConsentStore()
    g = Gate(consent=cs)
    th = Thread("g", group_size=5)
    c = Conversation(g, th)

    evs = c.feed(H("Boba đồng ý nhé cả nhà", 1000))
    assert "speak" in kinds(evs)
    assert cs.is_allowed("g")

    c.feed(H("ok cảm ơn", 1100))                       # cooldown after confirm
    evs2 = c.feed(H("tối nay đi đâu ăn ta?", 1200))    # now processed normally
    assert evs2[0].kind in ("deferred", "speak")


def test_revoke_blocks_again():
    cs = ConsentStore()
    cs.grant("g", "admin", 1.0)
    g = Gate(consent=cs)
    th = Thread("g", group_size=5)
    c = Conversation(g, th)
    assert cs.is_allowed("g")
    cs.revoke("g", 2.0)
    assert kinds(c.feed(H("tối nay đi đâu ăn ta?", 1000))) == ["silent"]
