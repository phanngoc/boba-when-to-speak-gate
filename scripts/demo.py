"""Scripted Vietnamese group-chat demo of the When-to-Speak Gate.

Run:  python scripts/demo.py   (from repo root; pure stdlib, no deps)

Shows all three deliverables in one timeline:
  (i)   stage 0/1/2 decisions + debounce (deferred SPEAK, and yielding to humans)
  (ii)  the classifier/judge deciding silent vs speak on real VN messages
  (iii) open-loop tracking: Boba asks → a human answers → Boba follows through
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from boba_gate import Conversation, Gate, Message, SenderKind, Thread


def human(text: str, ts: float, sender: str) -> Message:
    return Message(thread_id="grp", sender_id=sender, text=text, ts=ts,
                   sender_kind=SenderKind.HUMAN, msg_id=f"{sender}-{int(ts)}")


SCRIPT = [
    (1000, "An",  "haha ông này hài vãi 😂"),           # chitchat → silent
    (1010, "Bình", "đói quá"),                          # chitchat → silent
    (1020, "An",  "tối nay đi đâu ăn ta?"),            # planning Q → deferred SPEAK
    (1030, "Dũng", "còn ai on ko"),                     # window elapsed → Boba speaks
    (1050, "An",  "quán hải sản gần biển đi"),          # answers Boba's open loop → continue
    (1070, "Chi", "nghe ổn đấy"),                       # cooldown → silent
    (1090, "Dũng", "ừ chuẩn"),                          # silent
    (1400, "An",  "trưa mai ăn gì nhỉ"),               # planning Q → deferred SPEAK
    (1404, "Bình", "thôi ăn cơm tấm đầu ngõ đi"),       # human resolves first → YIELD
    (1500, "Chi", "@Boba vẽ giúp cái poster cuối tuần đi"),  # mention → direct
    (1510, "Dũng", "boba im đi phiền quá"),             # dismiss → block + adapt
    (1540, "An",  "tối nay đi nhậu không"),             # same kind, now silenced
]


def main() -> None:
    gate = Gate()
    thread = Thread(thread_id="grp", is_dm=False, group_size=5)
    convo = Conversation(gate, thread)

    print("=" * 70)
    print("BOBA — When-to-Speak Gate — scripted group chat")
    print("=" * 70)
    for ts, sender, text in SCRIPT:
        print(f"\n[{ts:>4.0f}] {sender}: {text}")
        for ev in convo.feed(human(text, ts, sender)):
            print(f"        {ev.text}")
            if ev.boba_text:
                print(f"          └─ 🫧 Boba: {ev.boba_text}")

    print("\n" + "-" * 70)
    print(f"final θ_low={thread.theta_low:.2f}  θ_high={thread.theta_high:.2f}  "
          f"recently_ignored={thread.recently_ignored}")
    print(f"open loops: {[(l.kind, l.status) for l in thread.open_loops]}")


if __name__ == "__main__":
    main()
