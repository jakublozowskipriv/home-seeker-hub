"""Telegram bot notifications (https://core.telegram.org/bots/api)."""

from __future__ import annotations

import logging

import httpx

log = logging.getLogger(__name__)

CAPTION_LIMIT = 1024
MESSAGE_LIMIT = 4096


class TelegramError(RuntimeError):
    pass


class Telegram:
    def __init__(
        self, token: str, chat_id: str | int | None = None, client: httpx.Client | None = None
    ):
        self.base = f"https://api.telegram.org/bot{token}"
        self.chat_id = chat_id
        self.client = client or httpx.Client(timeout=30)

    def _call(self, method: str, **payload) -> dict:
        resp = self.client.post(f"{self.base}/{method}", json=payload)
        data = resp.json()
        if not data.get("ok"):
            # Never log the URL: it contains the bot token.
            raise TelegramError(f"{method} failed: {data.get('description')}")
        return data["result"]

    def discover_chat_id(self) -> int | None:
        """Chat id of the latest private chat with the bot (a /start message or the
        'user started the bot' membership update)."""
        updates = self._call("getUpdates")
        for update in reversed(updates):
            for kind in ("message", "my_chat_member"):
                chat = (update.get(kind) or {}).get("chat") or {}
                if chat.get("type") == "private":
                    return chat["id"]
        log.warning("Telegram: no private chat found. %s", self.diagnostics(updates))
        return None

    def diagnostics(self, updates: list[dict] | None = None) -> str:
        """Which bot the token belongs to and what is waiting - no message contents."""
        parts = []
        try:
            me = self._call("getMe")
            parts.append(f"token belongs to @{me.get('username')}")
        except TelegramError as e:
            parts.append(f"getMe failed: {e}")
        try:
            webhook = self._call("getWebhookInfo")
            parts.append(
                "webhook is SET (blocks getUpdates)" if webhook.get("url") else "no webhook"
            )
        except TelegramError as e:
            parts.append(f"getWebhookInfo failed: {e}")
        if updates is not None:
            kinds = [k for u in updates for k in u if k != "update_id"]
            chats = [
                ((u.get(k) or {}).get("chat") or {}).get("type")
                for u in updates
                for k in u
                if isinstance(u.get(k), dict)
            ]
            parts.append(f"{len(updates)} pending updates, kinds={kinds}, chat types={chats}")
        return "; ".join(parts)

    def send_text(self, html: str) -> None:
        self._call(
            "sendMessage",
            chat_id=self.chat_id,
            text=html[:MESSAGE_LIMIT],
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

    def send_listing(self, html: str, photo_url: str | None) -> None:
        if photo_url and len(html) <= CAPTION_LIMIT:
            try:
                self._call(
                    "sendPhoto",
                    chat_id=self.chat_id,
                    photo=photo_url,
                    caption=html,
                    parse_mode="HTML",
                )
                return
            except TelegramError as e:
                log.warning("sendPhoto failed, falling back to text: %s", e)
        self.send_text(html)
