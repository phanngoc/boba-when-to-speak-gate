import asyncio

from boba_gate.models import SenderKind
from boba_gate.transport import (LoggingGateway, TelegramGateway, ZaloOAGateway,
                                 parse_telegram_update, parse_zalo_event)


def test_parse_group_message_with_mention():
    update = {"message": {"message_id": 5, "date": 1000,
                          "chat": {"id": -100, "type": "supergroup"},
                          "from": {"id": 42, "username": "an", "is_bot": False},
                          "text": "@boba_bot tối nay đi đâu ăn ta?"}}
    m = parse_telegram_update(update, bot_username="boba_bot")
    assert m.thread_id == "-100" and m.sender_id == "42"
    assert m.mention is True and m.sender_kind == SenderKind.HUMAN


def test_parse_reply_to_bot_sets_mention():
    update = {"message": {"message_id": 6, "date": 1001, "chat": {"id": -100},
                          "from": {"id": 42, "is_bot": False}, "text": "ừ ok",
                          "reply_to_message": {"message_id": 3,
                                               "from": {"username": "boba_bot", "is_bot": True}}}}
    m = parse_telegram_update(update, "boba_bot")
    assert m.mention is True and m.reply_to == "3"


def test_parse_plain_group_message_not_mention():
    update = {"message": {"message_id": 7, "date": 1002, "chat": {"id": -100},
                          "from": {"id": 9, "is_bot": False}, "text": "haha vui thật"}}
    m = parse_telegram_update(update, "boba_bot")
    assert m.mention is False


def test_parse_non_message_returns_none():
    assert parse_telegram_update({"update_id": 1}, "boba_bot") is None


def test_send_posts_expected_payload():
    captured = {}

    def fake_post(url, payload):
        captured["url"] = url
        captured["payload"] = payload
        return {"ok": True}

    gw = TelegramGateway("TOKEN", "boba_bot", http_post=fake_post)
    asyncio.run(gw.send("-100", "chào cả nhà"))
    assert captured["payload"] == {"chat_id": "-100", "text": "chào cả nhà"}
    assert "/botTOKEN/sendMessage" in captured["url"]


def test_logging_gateway_sink():
    out = []
    asyncio.run(LoggingGateway(sink=out.append).send("t", "hi"))
    assert out and "hi" in out[0]


# --- Zalo OA ----------------------------------------------------------------
def test_parse_zalo_text_event():
    ev = {"event_name": "user_send_text", "sender": {"id": "U123"},
          "timestamp": 1690000000000,
          "message": {"text": "đặt bàn tối nay được không", "msg_id": "m1"}}
    m = parse_zalo_event(ev)
    assert m.thread_id == "U123" and m.sender_id == "U123"
    assert m.mention is True and abs(m.ts - 1690000000.0) < 1


def test_parse_zalo_non_user_event_is_none():
    assert parse_zalo_event({"event_name": "oa_send_text"}) is None


def test_zalo_send_payload_and_token_header():
    captured = {}

    def fake_post(url, payload, headers, timeout=10.0):
        captured.update(url=url, payload=payload, headers=headers)
        return {"error": 0}

    gw = ZaloOAGateway(access_token=lambda: "TOK", http_post=fake_post)
    asyncio.run(gw.send("U123", "xin chào"))
    assert captured["payload"] == {"recipient": {"user_id": "U123"},
                                   "message": {"text": "xin chào"}}
    assert captured["headers"]["access_token"] == "TOK"
