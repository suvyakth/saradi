"""Check the Bolna setup, and optionally place one test call.

    python -m saradi.check_bolna                      # key works? balance?
    python -m saradi.check_bolna --call +91XXXXXXXXXX  # one "leave now" test call, waits for the result
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time

from .server import ROOT, load_env
from .voice import TERMINAL_NO_ANSWER, BolnaVoice, parse_bolna_webhook


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--call", metavar="E164", help="number to call, e.g. +919876543210 (only someone who agreed)")
    ap.add_argument("--language", default="kannada", choices=["kannada", "hindi", "english"])
    ap.add_argument("--name", default="Ajji", help="how the agent addresses the person")
    args = ap.parse_args()

    load_env(ROOT / ".env")
    key, agent = os.environ.get("BOLNA_API_KEY"), os.environ.get("BOLNA_AGENT_ID")
    if not key or not agent:
        print("Missing BOLNA_API_KEY or BOLNA_AGENT_ID in .env (copy .env.example to .env first).")
        return 1
    voice = BolnaVoice(key, agent, os.environ.get("BOLNA_FROM_NUMBER") or None)

    me = voice.whoami()
    if me is None:
        print("Bolna rejected the API key, or the network is down. Check the key has no extra spaces.")
        return 1
    print("API key works.", {k: me[k] for k in ("wallet", "concurrency") if k in me} or "")

    if not args.call:
        return 0
    if not re.fullmatch(r"\+[1-9]\d{6,14}", args.call):
        print("Number must be in E.164 format, like +919876543210.")
        return 1

    script = (f"{args.name}, it is time to leave now for Dr. Rao (token 16 running, you are 21). "
              "The journey takes about 40 minutes. Are you leaving now?")
    variables = {"elder_name": args.name, "family_name": "Suvyakth", "doctor_name": "Dr. Rao",
                 "hospital": "Manipal Old Airport Road", "language": args.language, "purpose": "leave",
                 "script": script, "travel_min": "40", "basis": "token 16 running, you are 21"}
    execution_id, status = voice.place_call(0, args.call, variables)
    if not execution_id:
        print(f"Call was not placed: {status}")
        return 1
    print(f"Call queued: {execution_id}. Waiting for the result (up to 3 min)...")

    last = None
    for _ in range(36):
        time.sleep(5)
        payload = voice.fetch_execution(execution_id) or {}
        status = payload.get("status")
        if status != last:
            print(f"  status: {status}")
            last = status
        _, response = parse_bolna_webhook(payload)
        if response:
            print(f"Elder response understood as: {response}")
            if payload.get("transcript"):
                print("Transcript:\n" + payload["transcript"][:1500])
            if status in TERMINAL_NO_ANSWER and payload.get("error_message"):
                print(f"Bolna says: {payload['error_message']}")
            return 0
    print("No final result after 3 minutes. Check the call in the Bolna dashboard's call history.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
