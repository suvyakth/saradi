"""Read the "now serving" token from a live queue link the family forwards to us.

Some clinics already send patients a live token page (queue tools such as TOKENN or OPDly).
We read the one link the patient received, on the patient's behalf, at most every few minutes.
Page formats differ and are unknown until we see real ones: this is a best-effort regex reader
that returns None rather than guess. Check each tool's terms before relying on it.
"""
from __future__ import annotations

import html
import re
import urllib.error
import urllib.request

PATTERNS = [
    r"now\s+serving\D{0,20}(\d{1,4})",
    r"current(?:ly)?\s+(?:serving|token)\D{0,20}(\d{1,4})",
    r"serving\s+token\D{0,20}(\d{1,4})",
    r"token\s+(?:no\.?\s*)?(\d{1,4})\s+(?:is\s+)?(?:running|in\s+progress|being\s+served)",
]
POLL_EVERY_MIN = 5


def extract_token(page: str) -> int | None:
    text = re.sub(r"<[^>]+>", " ", page)
    text = html.unescape(re.sub(r"\s+", " ", text)).lower()
    for pattern in PATTERNS:
        m = re.search(pattern, text)
        if m:
            return int(m.group(1))
    return None


def read_token(url: str, timeout: float = 10) -> int | None:
    if not url.startswith(("http://", "https://")):
        return None
    req = urllib.request.Request(url, headers={"User-Agent": "Saradi/0.1 (patient's own queue link)"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return extract_token(resp.read(500_000).decode(errors="replace"))
    except (urllib.error.URLError, TimeoutError, ValueError):
        return None
