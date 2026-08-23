"""Transport abstraction + a real Telegram adapter.

The gate is channel-agnostic. A `Gateway` knows how to (a) turn an inbound
webhook payload into our `Message` and (b) send text back to a thread.

Why Telegram here (not iMessage/Zalo)? See VIETNAM_MARKET.md: Telegram is the
only widely-available channel whose **group** Bot API lets a bot read all
messages (privacy mode OFF) — which the "socially intelligent, hangs-back" model
requires. iMessage needs a Mac fleet; Zalo's dev surface is 1:1 OA/Mini-App only;
Messenger group bots can't read history.

Stdlib-only (urllib) so it runs with no dependencies; the HTTP poster is
injectable so it is unit-testable without a network or token.
"""
from __future__ import annotations

import asyncio
import json
import urllib.request
from typing import Callable, Optional, Protocol

from .models import Message, SenderKind


class Gateway(Protocol):
    async def send(self, thread_id: str, text: str) -> None: ...


# --- default local sink ------------------------------------------------------
class LoggingGateway:
    """Prints outbound messages. Useful for local runs and the demo."""

    def __init__(self, sink: Callable[[str], None] = print):
        self.sink = sink

    async def send(self, thread_id: str, text: str) -> None:
        self.sink(f"[SEND → {thread_id}] {text}")


# --- Telegram ---------------------------------------------------------------
def _urllib_post(url: str, payload: dict, timeout: float = 10.0) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # nosec - fixed host
        return json.loads(resp.read().decode("utf-8"))


def parse_telegram_update(update: dict, bot_username: str) -> Optional[Message]:
    """Normalize a Telegram `Update` into our `Message` (None if not a text msg).

    `thread_id` = chat id (a group chat id is negative). `mention` is True when
    the bot is @-mentioned or the message replies to the bot — the transport's
    job, since the bot's real @username is channel-specific.
    """
    m = update.get("message") or update.get("edited_message")
    if not m:
        return None
    chat = m.get("chat", {})
    frm = m.get("from", {})
    text = m.get("text", "") or m.get("caption", "") or ""

    handle = ("@" + bot_username).lower()
    mentioned = handle in text.lower()
    reply = m.get("reply_to_message")
    replies_to_bot = bool(reply and reply.get("from", {}).get("username", "").lower()
                          == bot_username.lower())

    return Message(
        thread_id=str(chat.get("id", "")),
        sender_id=str(frm.get("id", "unknown")),
        text=text,
        ts=float(m.get("date", 0)),
        msg_id=str(m.get("message_id", "")),
        sender_kind=SenderKind.BOT if frm.get("is_bot") else SenderKind.HUMAN,
        reply_to=str(reply["message_id"]) if reply else None,
        media_only=(not text) and any(k in m for k in ("photo", "sticker", "video", "document")),
        mention=mentioned or replies_to_bot,
    )


class TelegramGateway:
    """Sends messages via the Telegram Bot API.

    Setup for the group model: create the bot with @BotFather, then **disable
    privacy mode** (BotFather → Bot Settings → Group Privacy → Turn off) so the
    bot receives every group message, not only mentions. Set a webhook to your
    /webhook endpoint. `bot_username` is used only to detect mentions on inbound.
    """

    API = "https://api.telegram.org"

    def __init__(self, token: str, bot_username: str,
                 http_post: Callable[[str, dict], dict] = _urllib_post):
        self.token = token
        self.bot_username = bot_username
        self._post = http_post

    def parse(self, update: dict) -> Optional[Message]:
        return parse_telegram_update(update, self.bot_username)

    async def send(self, thread_id: str, text: str) -> None:
        url = f"{self.API}/bot{self.token}/sendMessage"
        await asyncio.to_thread(self._post, url, {"chat_id": thread_id, "text": text})
