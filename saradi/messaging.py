"""Messages to the family. `sim` shows them in the dashboard's WhatsApp feed; `whatsapp` uses Meta's Cloud API."""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


class SimulatedMessenger:
    name = "sim"

    def send(self, to: str, body: str) -> str:
        return "shown"


class TelegramMessenger:
    """Family alerts through a Telegram bot. No public URL needed: the app polls Telegram for new chats.

    Linking: each family member gets a link like t.me/<bot>?start=<random code>. Opening it and pressing
    Start ties their Telegram chat to their phone number in family_links, and alerts go there.
    """

    name = "telegram"

    def __init__(self, token: str, db, transport=None, timeout: float = 15):
        self.token, self.db, self.timeout = token, db, timeout
        self.transport = transport or self._http
        self.offset: int | None = None
        self._username: str | None = None
        self._username_tried = 0.0
        self._warned = False

    def _http(self, method: str, payload: dict) -> dict | None:
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/{method}",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            if not self._warned:
                self._warned = True
                print(f"[saradi] Telegram {method} failed: HTTP {e.code} (check TELEGRAM_BOT_TOKEN)")
            return None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None

    def bot_username(self) -> str | None:
        if self._username is None and time.time() - self._username_tried > 30:
            self._username_tried = time.time()
            res = self.transport("getMe", {})
            if res and res.get("ok"):
                self._username = res["result"].get("username")
        return self._username

    def link_url(self, family_phone: str) -> str | None:
        row = self.db.one("SELECT code FROM family_links WHERE family_phone = ?", (family_phone,))
        username = self.bot_username()
        return f"https://t.me/{username}?start={row['code']}" if row and username else None

    def is_linked(self, family_phone: str) -> bool:
        row = self.db.one("SELECT chat_id FROM family_links WHERE family_phone = ?", (family_phone,))
        return bool(row and row["chat_id"])

    def send(self, to: str, body: str) -> str:
        row = self.db.one("SELECT chat_id FROM family_links WHERE family_phone = ?", (to,))
        if not row or not row["chat_id"]:
            return "not connected"
        res = self.transport("sendMessage", {"chat_id": row["chat_id"], "text": body[:4000]})
        return "sent" if res and res.get("ok") else "error: Telegram did not accept the message"

    def poll(self) -> None:
        payload = {"timeout": 0, "allowed_updates": ["message"]}
        if self.offset is not None:
            payload["offset"] = self.offset
        res = self.transport("getUpdates", payload)
        for update in (res or {}).get("result", []):
            self.offset = update["update_id"] + 1
            if "message" in update:
                self._handle(update["message"])

    def _reply(self, chat_id, text: str) -> None:
        self.transport("sendMessage", {"chat_id": chat_id, "text": text})

    def _handle(self, msg: dict) -> None:
        text = (msg.get("text") or "").strip()
        chat_id = str(msg["chat"]["id"])
        if not text.startswith("/start"):
            return
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            self._reply(chat_id, "Hi, this is Saradi. Open the connect link shown on your Saradi page to get alerts here.")
            return
        row = self.db.one("SELECT * FROM family_links WHERE code = ?", (parts[1].strip(),))
        if row is None:
            self._reply(chat_id, "That link isn't valid. Use the connect link from your Saradi page.")
        elif row["chat_id"] and row["chat_id"] != chat_id:
            self._reply(chat_id, "That link is already connected to another Telegram account.")
        else:
            self.db.execute("UPDATE family_links SET chat_id = ?, linked_at = strftime('%s','now') WHERE family_phone = ?",
                            (chat_id, row["family_phone"]))
            visit = self.db.one("SELECT elder_name FROM visits WHERE family_phone = ? ORDER BY id DESC LIMIT 1",
                                (row["family_phone"],))
            who = f"{visit['elder_name']}'s" if visit else "your family's"
            self._reply(chat_id, f"Connected. You'll get updates about {who} doctor visits here.")


class WhatsAppCloudMessenger:
    """Free-form text only reaches users who messaged you in the last 24 hours.
    Outside that window Meta requires an approved template; add templates before real use."""

    name = "whatsapp"

    def __init__(self, token: str, phone_number_id: str, api_version: str = "v21.0", timeout: float = 15):
        self.url = f"https://graph.facebook.com/{api_version}/{phone_number_id}/messages"
        self.token, self.timeout = token, timeout

    def send(self, to: str, body: str) -> str:
        payload = {
            "messaging_product": "whatsapp",
            "to": to.lstrip("+"),
            "type": "text",
            "text": {"body": body},
        }
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode(),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout):
                return "sent"
        except (urllib.error.URLError, TimeoutError) as e:
            return f"error: {e}"
