"""Local web server: family dashboard, check-in API, Bolna webhook, and the background loop."""
from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import clinic_link
from .clock import IST, Clock, hhmm
from .db import DB
from .engine import ACTIVE_STATES, Engine
from .messaging import SimulatedMessenger, TelegramMessenger, WhatsAppCloudMessenger
from .voice import BolnaVoice, SimulatedVoice, parse_bolna_webhook

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"
BOLNA_POLL_SEC = 5
TELEGRAM_POLL_SEC = 2
STATIC = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/style.css": ("style.css", "text/css")}


def load_env(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


def build_app() -> "App":
    load_env(ROOT / ".env")
    voice = SimulatedVoice()
    if os.environ.get("SARADI_VOICE") == "bolna":
        key, agent = os.environ.get("BOLNA_API_KEY", "").strip(), os.environ.get("BOLNA_AGENT_ID", "").strip()
        if key and agent:
            voice = BolnaVoice(key, agent, os.environ.get("BOLNA_FROM_NUMBER") or None)
        else:
            print("[saradi] SARADI_VOICE=bolna but BOLNA_API_KEY / BOLNA_AGENT_ID are empty: using simulated calls")
    db = DB(os.environ.get("SARADI_DB", str(ROOT / "data" / "saradi.db")))
    messenger = SimulatedMessenger()
    if os.environ.get("SARADI_MESSENGER") == "whatsapp":
        messenger = WhatsAppCloudMessenger(os.environ["WA_TOKEN"], os.environ["WA_PHONE_NUMBER_ID"],
                                           os.environ.get("WA_API_VERSION", "v21.0"))
    elif os.environ.get("SARADI_MESSENGER") == "telegram":
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        if token:
            messenger = TelegramMessenger(token, db)
        else:
            print("[saradi] SARADI_MESSENGER=telegram but TELEGRAM_BOT_TOKEN is empty: using simulated messages")
    return App(Engine(db, Clock(), voice, messenger))


class App:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.link_checked: dict[int, float] = {}
        self.bolna_polled = 0.0
        self.telegram_polled = 0.0

    @property
    def clock(self):
        return self.engine.clock

    def loop(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                self.engine.tick()
                self.poll_clinic_links()
                self.poll_bolna_calls()
                self.poll_telegram()
            except Exception as e:  # keep the loop alive; show the problem in the console
                print(f"[saradi] loop error: {e!r}")
            stop.wait(1.0)

    def poll_clinic_links(self) -> None:
        now = self.clock.now()
        marks = ",".join("?" * len(ACTIVE_STATES))
        rows = self.engine.db.all(
            f"SELECT id, clinic_link FROM visits WHERE clinic_link IS NOT NULL AND state IN ({marks})", ACTIVE_STATES)
        for row in rows:
            if now - self.link_checked.get(row["id"], 0) < clinic_link.POLL_EVERY_MIN * 60:
                continue
            self.link_checked[row["id"]] = now
            token = clinic_link.read_token(row["clinic_link"])
            if token is not None:
                self.engine.check_in(row["id"], "token_now", token, source="clinic link")

    def poll_telegram(self) -> None:
        messenger = self.engine.messenger
        if not hasattr(messenger, "poll") or time.time() - self.telegram_polled < TELEGRAM_POLL_SEC:
            return
        self.telegram_polled = time.time()
        messenger.poll()

    def poll_bolna_calls(self) -> None:
        """Ask Bolna for results of open calls every few real seconds (works without a webhook)."""
        voice = self.engine.voice
        if not hasattr(voice, "fetch_execution") or time.time() - self.bolna_polled < BOLNA_POLL_SEC:
            return
        self.bolna_polled = time.time()
        for call in self.engine.db.all(
                "SELECT id, external_id FROM calls WHERE provider = 'bolna' AND response IS NULL AND external_id IS NOT NULL"):
            payload = voice.fetch_execution(call["external_id"])
            if not payload:
                continue
            status = payload.get("status")
            if status:
                self.engine.db.execute("UPDATE calls SET status = ? WHERE id = ?", (status, call["id"]))
            _, response = parse_bolna_webhook(payload)
            if response:
                self.engine.call_result(call["id"], response)

    # ---- API ----------------------------------------------------------------------

    def state(self) -> dict:
        db, now = self.engine.db, self.clock.now()
        visits = []
        for row in db.all("SELECT id FROM visits ORDER BY appointment_at, id"):
            v = self.engine.visit(row["id"])
            p = self.engine.predict(v["id"]) if v["state"] not in ("done", "cancelled") else None
            visits.append({
                "id": v["id"], "elder_name": v["elder_name"], "family_name": v["family_name"],
                "doctor_name": v["doctor_name"], "hospital": v["hospital"], "language": v["language"],
                "appointment": hhmm(v["appointment_at"]), "patient_token": v["patient_token"],
                "travel_min": v["travel_min"], "state": v["state"], "clinic_link": v["clinic_link"],
                "family_link": self._family_link(v["family_phone"]),
                "prediction": None if p is None else {
                    "source": p.source, "basis": p.basis, "samples": p.samples,
                    "leave_at": hhmm(p.leave_at), "turn_p10": hhmm(p.turn_p10), "turn_p50": hhmm(p.turn_p50),
                    "turn_p90": hhmm(p.turn_p90), "leave_in_min": round((p.leave_at - now) / 60),
                },
                "events": [{"at": hhmm(e["at"]), "text": e["text"]} for e in
                           db.all("SELECT * FROM events WHERE visit_id = ? ORDER BY id DESC LIMIT 12", (v["id"],))],
            })
        calls = db.all("""SELECT c.*, v.elder_name, v.language FROM calls c JOIN visits v ON v.id = c.visit_id
                          ORDER BY c.id DESC LIMIT 20""")
        messages = db.all("""SELECT m.*, v.family_name FROM messages m JOIN visits v ON v.id = m.visit_id
                             ORDER BY m.id DESC LIMIT 30""")
        doctors = db.all("SELECT * FROM doctors ORDER BY name")
        for d in doctors:
            d["history_samples"] = len(self.engine.history(d["id"]).delays)
        families: dict[str, dict] = {}
        for row in db.all("SELECT elder_name, family_name, family_phone FROM visits ORDER BY id"):
            fam = families.setdefault(row["family_phone"], {
                "phone": row["family_phone"], "name": row["family_name"], "elders": [],
                "prefs": self.engine.family_prefs(row["family_phone"]),
                "link": self._family_link(row["family_phone"]),
            })
            if row["elder_name"] not in fam["elders"]:
                fam["elders"].append(row["elder_name"])
        return {
            "families": list(families.values()),
            "now": hhmm(now), "date": datetime.fromtimestamp(now, IST).strftime("%a %d %b"),
            "speed": self.clock.speed, "voice": self.engine.voice.name, "messenger": self.engine.messenger.name,
            "visits": visits, "doctors": doctors,
            "calls": [{**c, "at": hhmm(c["at"])} for c in calls],
            "messages": [{**m, "at": hhmm(m["at"])} for m in messages],
        }

    def _family_link(self, family_phone: str) -> dict | None:
        m = self.engine.messenger
        if not hasattr(m, "link_url"):
            return None
        return {"connected": m.is_linked(family_phone), "url": m.link_url(family_phone)}

    def create_visit(self, data: dict) -> int:
        data = dict(data)
        data["appointment_at"] = self._parse_time(data.pop("appointment_time"))
        required = ("elder_name", "elder_phone", "family_name", "family_phone", "doctor_name", "hospital")
        missing = [k for k in required if not str(data.get(k, "")).strip()]
        if missing:
            raise ValueError("missing: " + ", ".join(missing))
        visit_id = self.engine.create_visit(data)
        self.engine.tick()
        return visit_id

    def _parse_time(self, value: str) -> float:
        m = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", value or "")
        if not m:
            raise ValueError("appointment_time must be HH:MM")
        today = datetime.fromtimestamp(self.clock.now(), IST)
        return today.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0).timestamp()

    def demo(self) -> None:
        """Cold start: an empty database, 10:00 on a weekday morning, one visit at 13:00."""
        db = self.engine.db
        for table in ("events", "messages", "calls", "observations", "reported_waits", "visits", "doctors", "family_prefs"):
            db.execute(f"DELETE FROM {table}")
        self.link_checked.clear()
        today = datetime.fromtimestamp(time.time(), IST).replace(hour=10, minute=0, second=0, microsecond=0)
        self.engine.clock = Clock(start=today.timestamp(), speed=1.0)
        self.create_visit({
            # With real calls on, set these in .env to a relative's number who agreed to the demo.
            "elder_name": os.environ.get("SARADI_DEMO_ELDER_NAME") or "Ajji",
            "elder_phone": os.environ.get("SARADI_DEMO_ELDER_PHONE") or "+919800000001",
            "language": os.environ.get("SARADI_DEMO_LANGUAGE") or "kannada",
            "family_name": os.environ.get("SARADI_DEMO_FAMILY_NAME") or "Suvyakth",
            "family_phone": os.environ.get("SARADI_DEMO_FAMILY_PHONE") or "+358400000001",
            "doctor_name": "Dr. Rao", "hospital": "Manipal Old Airport Road", "department": "Cardiology",
            "appointment_time": "13:00", "patient_token": 21, "travel_min": 40,
        })


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            if not self.path.startswith("/api/state"):
                super().log_message(fmt, *args)

        def do_GET(self):
            if self.path in STATIC:
                name, ctype = STATIC[self.path]
                return self._send(200, (WEB / name).read_bytes(), ctype + "; charset=utf-8")
            if self.path == "/api/state":
                return self._json(200, app.state())
            self._json(404, {"error": "not found"})

        def do_POST(self):
            try:
                data = self._body()
                path = self.path
                if path == "/api/visits":
                    return self._json(200, {"id": app.create_visit(data)})
                if m := re.fullmatch(r"/api/visits/(\d+)/checkin", path):
                    app.engine.check_in(int(m.group(1)), data["kind"], float(data.get("value", 1)),
                                        source=data.get("source", "family"))
                    return self._json(200, {"ok": True})
                if m := re.fullmatch(r"/api/visits/(\d+)/cancel", path):
                    app.engine.cancel(int(m.group(1)))
                    return self._json(200, {"ok": True})
                if m := re.fullmatch(r"/api/calls/(\d+)/respond", path):
                    app.engine.call_result(int(m.group(1)), data["response"])
                    app.engine.tick()
                    return self._json(200, {"ok": True})
                if path == "/api/prefs":
                    phone = str(data.pop("family_phone", "")).strip()
                    if not phone:
                        raise ValueError("missing: family_phone")
                    return self._json(200, {"prefs": app.engine.set_family_prefs(phone, data)})
                if path == "/api/clock":
                    if "advance_min" in data:
                        app.clock.advance(float(data["advance_min"]))
                    if "speed" in data:
                        app.clock.set_speed(float(data["speed"]))
                    app.engine.tick()
                    return self._json(200, {"ok": True})
                if path == "/api/demo":
                    app.demo()
                    return self._json(200, {"ok": True})
                if path == "/webhooks/bolna":
                    execution_id, response = parse_bolna_webhook(data)
                    if execution_id and response:
                        try:
                            app.engine.call_result_by_external(execution_id, response)
                        except KeyError:
                            pass
                    return self._json(200, {"ok": True})
                self._json(404, {"error": "not found"})
            except (KeyError, ValueError, json.JSONDecodeError) as e:
                self._json(400, {"error": str(e)})

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(length) or b"{}") if length else {}

        def _json(self, code: int, obj) -> None:
            self._send(code, json.dumps(obj).encode(), "application/json")

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

    return Handler


def main() -> None:
    app = build_app()
    port = int(os.environ.get("SARADI_PORT", "8765"))
    stop = threading.Event()
    threading.Thread(target=app.loop, args=(stop,), daemon=True).start()
    host = os.environ.get("SARADI_HOST", "").strip() or "127.0.0.1"  # 0.0.0.0 lets a phone on the same Wi-Fi connect
    server = ThreadingHTTPServer((host, port), make_handler(app))
    print(f"[saradi] http://{host}:{port}  voice={app.engine.voice.name} messenger={app.engine.messenger.name}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        server.server_close()
