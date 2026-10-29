"""Calls to the elder. `sim` shows calls on the dashboard's "elder's phone"; `bolna` places real calls."""
from __future__ import annotations

import json
import urllib.error
import urllib.request

BOLNA_API = "https://api.bolna.ai"
BOLNA_CALL_URL = f"{BOLNA_API}/call"
TERMINAL_NO_ANSWER = {"no-answer", "busy", "failed", "canceled", "error", "stopped", "balance-low"}


class SimulatedVoice:
    """No phone call happens. The dashboard shows the call; you answer it as the elder."""

    name = "sim"

    def place_call(self, call_id: int, phone: str, variables: dict) -> tuple[str | None, str]:
        return f"sim-{call_id}", "ringing"


class BolnaVoice:
    """Outbound calls through Bolna. Results come back on POST /webhooks/bolna."""

    name = "bolna"

    def __init__(self, api_key: str, agent_id: str, from_number: str | None = None, timeout: float = 15):
        self.api_key, self.agent_id, self.from_number, self.timeout = api_key, agent_id, from_number, timeout

    def place_call(self, call_id: int, phone: str, variables: dict) -> tuple[str | None, str]:
        body = {"agent_id": self.agent_id, "recipient_phone_number": phone, "user_data": variables}
        if self.from_number:
            body["from_phone_number"] = self.from_number
        req = urllib.request.Request(
            BOLNA_CALL_URL,
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode() or "{}")
            return data.get("execution_id"), data.get("status", "queued")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            return None, f"error: {e}"

    def fetch_execution(self, execution_id: str) -> dict | None:
        """Poll a call's result. Same shape as the webhook payload, so no public URL is needed."""
        return self._get(f"{BOLNA_API}/executions/{execution_id}")

    def whoami(self) -> dict | None:
        return self._get(f"{BOLNA_API}/user/me")

    def _get(self, url: str) -> dict | None:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {self.api_key}"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode() or "{}")
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None


def parse_bolna_webhook(payload: dict) -> tuple[str | None, str | None]:
    """Return (execution_id, elder_response) once the call is final, else (execution_id, None).

    Bolna posts on every status change; only `completed` (or a no-answer type status) is final.
    The agent's extraction prompt must return a key named `elder_response` (prompts/extraction_prompt.md).
    """
    execution_id = payload.get("id") or payload.get("execution_id")
    status = (payload.get("status") or "").lower()
    if status in TERMINAL_NO_ANSWER or payload.get("answered_by_voice_mail"):
        return execution_id, "no_answer"
    if status != "completed":
        return execution_id, None
    response = _find_key(payload.get("extracted_data"), "elder_response")
    response = (str(response).strip().lower().replace(" ", "_") if response else "confused")
    allowed = {"leaving", "already_left", "unwell", "call_later", "confused", "no_answer"}
    return execution_id, response if response in allowed else "confused"


def _find_key(obj, key: str):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            found = _find_key(v, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _find_key(v, key)
            if found is not None:
                return found
    elif isinstance(obj, str) and key in obj:
        try:
            return _find_key(json.loads(obj), key)
        except json.JSONDecodeError:
            return None
    return None
