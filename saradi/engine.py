"""The visit lifecycle: brief the elder, watch the queue, call when it's time, escalate to family.

States
  scheduled      created, nobody contacted yet
  watching       elder briefed; waiting for the leave time (estimate keeps updating)
  calling        "leave now" call placed, waiting for the elder's answer
  retry          elder asked to call later, or didn't pick up; next call at next_action_at
  needs_family   elder unwell / unreachable / confused; family has been alerted
  en_route       elder has left
  arrived, called_in, done, cancelled
"""
from __future__ import annotations

import functools
import json
import re
import secrets
import threading
from datetime import datetime

from . import scripts
from .clock import IST, weekday
from .db import DB
from .predictor import MIN, DoctorHistory, Observation, Prediction, VisitInput, live_consult_rate, predict

BRIEF_LEAD_MIN = 120          # brief the elder this long before the usual leave time
RETRY_NO_ANSWER_MIN = 3
RETRY_CALL_LATER_MIN = 5
MAX_NO_ANSWER = 2
UPDATE_THRESHOLD_MIN = 20     # tell the family if the leave time moves this much
DOCTOR_LEVEL_KINDS = ("token_now", "doctor_in")  # shared by every patient of the doctor that day
VISIT_LEVEL_KINDS = ("patients_ahead",)
ELDER_RESPONSES = ("leaving", "already_left", "unwell", "call_later", "confused", "no_answer")
CHECKIN_KINDS = DOCTOR_LEVEL_KINDS + VISIT_LEVEL_KINDS + ("left", "arrived", "called_in", "done")
# What the family can hear about. "urgent" (unwell, unreachable, confused) is always sent.
NOTIFY_KINDS = {
    "plan": "Morning plan",
    "update": "Leave time changes",
    "left": "Elder has left",
    "done": "Visit summary",
}
DEFAULT_PREFS = {"plan": True, "update": True, "left": True, "done": True,
                 "quiet": False, "quiet_from": "22:00", "quiet_to": "07:00"}
ACTIVE_STATES = ("scheduled", "watching", "calling", "retry", "needs_family", "en_route", "arrived", "called_in")


def _locked(method):
    """The background loop and web requests both drive the engine; one at a time."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return wrapper


class Engine:
    def __init__(self, db: DB, clock, voice, messenger):
        self.db, self.clock, self.voice, self.messenger = db, clock, voice, messenger
        self.lock = threading.RLock()

    # ---- creating and reading visits ------------------------------------------------

    @_locked
    def create_visit(self, data: dict) -> int:
        doctor_id = self.db.doctor_id(data["doctor_name"], data["hospital"], data.get("department", ""))
        visit_id = self.db.execute(
            """INSERT INTO visits (doctor_id, elder_name, elder_phone, language, family_name, family_phone,
                   appointment_at, patient_token, travel_min, buffer_min, clinic_link, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (doctor_id, data["elder_name"], data["elder_phone"], data.get("language", "kannada"),
             data["family_name"], data["family_phone"], float(data["appointment_at"]),
             _int_or_none(data.get("patient_token")), float(data.get("travel_min", 30)),
             float(data.get("buffer_min", 15)), data.get("clinic_link") or None, self.clock.now()),
        )
        # A random code (never the phone number) lets this family member link their Telegram.
        self.db.execute("INSERT OR IGNORE INTO family_links (family_phone, code) VALUES (?, ?)",
                        (data["family_phone"], secrets.token_urlsafe(6)))
        past_wait = data.get("past_wait_min")
        if past_wait not in (None, ""):
            # Cold start: the family's memory of the last visit is our first data point.
            self.db.execute(
                "INSERT INTO reported_waits (doctor_id, weekday, delay_min, reported_by, at) VALUES (?, ?, ?, ?, ?)",
                (doctor_id, None, float(past_wait), "family at sign-up", self.clock.now()),
            )
        self._event(visit_id, "Visit created")
        return visit_id

    def visit(self, visit_id: int) -> dict:
        v = self.db.one(
            """SELECT v.*, d.name AS doctor_name, d.hospital, d.department
               FROM visits v JOIN doctors d ON d.id = v.doctor_id WHERE v.id = ?""",
            (visit_id,),
        )
        if v is None:
            raise KeyError(visit_id)
        return v

    def history(self, doctor_id: int, exclude_visit: int | None = None) -> DoctorHistory:
        h = DoctorHistory()
        visits = self.db.all(
            "SELECT id, appointment_at FROM visits WHERE doctor_id = ? AND id IS NOT ?",
            (doctor_id, exclude_visit),
        )
        for pv in visits:
            called = self.db.one(
                "SELECT at FROM observations WHERE visit_id = ? AND kind = 'called_in' ORDER BY at LIMIT 1",
                (pv["id"],),
            )
            if called:
                h.delays.append((weekday(pv["appointment_at"]), (called["at"] - pv["appointment_at"]) / MIN))
        for r in self.db.all("SELECT weekday, delay_min FROM reported_waits WHERE doctor_id = ?", (doctor_id,)):
            h.delays.append((r["weekday"] if r["weekday"] is not None else -1, r["delay_min"]))
        for day in self._session_days(doctor_id, exclude_visit):
            rate = live_consult_rate([Observation(o["kind"], o["value"], o["at"]) for o in day])
            if rate is not None:
                h.consult_rates.append(rate)
        return h

    def predict(self, visit_id: int) -> Prediction:
        v = self.visit(visit_id)
        obs = self._observations_for(v)
        vi = VisitInput(v["appointment_at"], v["patient_token"], v["travel_min"], v["buffer_min"],
                        weekday(v["appointment_at"]), obs)
        return predict(vi, self.history(v["doctor_id"], exclude_visit=visit_id))

    # ---- inputs from families, clinics and the voice agent ----------------------------

    @_locked
    def check_in(self, visit_id: int, kind: str, value: float = 1, source: str = "family") -> None:
        if kind not in CHECKIN_KINDS:
            raise ValueError(f"unknown check-in: {kind}")
        v = self.visit(visit_id)
        now = self.clock.now()
        self.db.execute(
            "INSERT INTO observations (visit_id, doctor_id, kind, value, source, at) VALUES (?, ?, ?, ?, ?, ?)",
            (visit_id, v["doctor_id"], kind, float(value), source, now),
        )
        self._event(visit_id, f"Check-in from {source}: {_describe(kind, value)}")
        if kind == "left" and v["state"] in ("scheduled", "watching", "calling", "retry", "needs_family"):
            self._set_state(visit_id, "en_route")
        elif kind in ("arrived", "called_in", "done"):
            self._set_state(visit_id, kind)
            if kind == "done":
                self._send_family(v, scripts.family_done(v, self._waited_min(visit_id)), "done")
        self.tick()

    @_locked
    def call_result(self, call_id: int, response: str) -> None:
        if response not in ELDER_RESPONSES:
            raise ValueError(f"unknown response: {response}")
        call = self.db.one("SELECT * FROM calls WHERE id = ?", (call_id,))
        if call is None:
            raise KeyError(call_id)
        if call["response"]:
            return  # already handled (webhooks can repeat)
        self.db.execute("UPDATE calls SET status = 'completed', response = ? WHERE id = ?", (response, call_id))
        v = self.visit(call["visit_id"])
        self._event(v["id"], f"{v['elder_name']} answered the {call['purpose']} call: {response.replace('_', ' ')}")
        if call["purpose"] == "brief":
            if response == "unwell":
                self._send_family(v, scripts.family_unwell(v), "urgent")
            return
        now = self.clock.now()
        if response in ("leaving", "already_left"):
            self._send_family(v, scripts.family_left(v), "left")
            self._set_state(v["id"], "en_route")
        elif response == "unwell":
            self._send_family(v, scripts.family_unwell(v), "urgent")
            self._set_state(v["id"], "needs_family")
        elif response == "confused":
            self._send_family(v, scripts.family_confused(v), "urgent")
            self._set_state(v["id"], "needs_family")
        elif response == "call_later":
            self._set_state(v["id"], "retry", now + RETRY_CALL_LATER_MIN * MIN)
        elif response == "no_answer":
            missed = self.db.one(
                "SELECT COUNT(*) AS n FROM calls WHERE visit_id = ? AND purpose = 'leave' AND response = 'no_answer'",
                (v["id"],),
            )["n"]
            if missed >= MAX_NO_ANSWER:
                self._send_family(v, scripts.family_no_answer(v), "urgent")
                self._set_state(v["id"], "needs_family")
            else:
                self._set_state(v["id"], "retry", now + RETRY_NO_ANSWER_MIN * MIN)

    @_locked
    def call_result_by_external(self, external_id: str, response: str) -> None:
        call = self.db.one("SELECT id FROM calls WHERE external_id = ?", (external_id,))
        if call is None:
            raise KeyError(external_id)
        self.call_result(call["id"], response)

    @_locked
    def cancel(self, visit_id: int) -> None:
        self._set_state(visit_id, "cancelled")

    # ---- the loop -------------------------------------------------------------------

    @_locked
    def tick(self) -> None:
        marks = ",".join("?" * len(ACTIVE_STATES))
        for row in self.db.all(f"SELECT id FROM visits WHERE state IN ({marks})", ACTIVE_STATES):
            self._step(row["id"])

    def _step(self, visit_id: int) -> None:
        v = self.visit(visit_id)
        p = self.predict(visit_id)
        now = self.clock.now()
        state = v["state"]

        if state == "scheduled":
            brief_at = p.leave_at - BRIEF_LEAD_MIN * MIN
            if now >= brief_at:
                if now < p.leave_at:
                    self._call(v, "brief", scripts.brief_call(v, p), p)
                self._send_family(v, scripts.family_brief(v, p), "plan")
                self.db.execute("UPDATE visits SET told_leave_at = ? WHERE id = ?", (p.leave_at, visit_id))
                self._set_state(visit_id, "watching")
                state = "watching"

        if state == "watching":
            told = v["told_leave_at"]
            if told is not None and abs(p.leave_at - told) >= UPDATE_THRESHOLD_MIN * MIN and p.leave_at > now:
                self._send_family(v, scripts.family_update(v, p, told), "update")
                self.db.execute("UPDATE visits SET told_leave_at = ? WHERE id = ?", (p.leave_at, visit_id))
            if now >= p.leave_at:
                self._call(v, "leave", scripts.leave_call(v, p), p)
                self._set_state(visit_id, "calling")

        elif state == "retry" and v["next_action_at"] is not None and now >= v["next_action_at"]:
            self._call(v, "leave", scripts.leave_call(v, p), p)
            self._set_state(visit_id, "calling")

    # ---- helpers --------------------------------------------------------------------

    def _call(self, v: dict, purpose: str, script: str, p: Prediction) -> int:
        attempt = 1 + self.db.one(
            "SELECT COUNT(*) AS n FROM calls WHERE visit_id = ? AND purpose = ?", (v["id"], purpose)
        )["n"]
        call_id = self.db.execute(
            "INSERT INTO calls (visit_id, purpose, script, provider, status, attempt, at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (v["id"], purpose, script, self.voice.name, "placing", attempt, self.clock.now()),
        )
        variables = {
            "elder_name": v["elder_name"], "family_name": v["family_name"], "doctor_name": v["doctor_name"],
            "hospital": v["hospital"], "language": v["language"], "purpose": purpose, "script": script,
            "travel_min": str(int(v["travel_min"])), "basis": p.basis,
        }
        external_id, status = self.voice.place_call(call_id, v["elder_phone"], variables)
        self.db.execute("UPDATE calls SET external_id = ?, status = ? WHERE id = ?", (external_id, status, call_id))
        self._event(v["id"], f"Calling {v['elder_name']} ({purpose}, attempt {attempt})")
        return call_id

    def family_prefs(self, family_phone: str) -> dict:
        row = self.db.one("SELECT prefs FROM family_prefs WHERE family_phone = ?", (family_phone,))
        return {**DEFAULT_PREFS, **(json.loads(row["prefs"]) if row else {})}

    @_locked
    def set_family_prefs(self, family_phone: str, patch: dict) -> dict:
        prefs = self.family_prefs(family_phone)
        for key, value in patch.items():
            if key == "urgent":
                raise ValueError("Urgent alerts can't be turned off")
            if key in NOTIFY_KINDS or key == "quiet":
                if not isinstance(value, bool):
                    raise ValueError(f"{key} must be true or false")
            elif key in ("quiet_from", "quiet_to"):
                if not isinstance(value, str) or not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", value):
                    raise ValueError(f"{key} must be HH:MM")
            else:
                raise ValueError(f"unknown setting: {key}")
            prefs[key] = value
        self.db.execute(
            "INSERT INTO family_prefs (family_phone, prefs) VALUES (?, ?) "
            "ON CONFLICT(family_phone) DO UPDATE SET prefs = excluded.prefs",
            (family_phone, json.dumps(prefs)),
        )
        return prefs

    def _muted_reason(self, prefs: dict, kind: str) -> str | None:
        if kind == "urgent":
            return None
        if kind in NOTIFY_KINDS and not prefs.get(kind, True):
            return f"you turned off \"{NOTIFY_KINDS[kind]}\""
        if prefs.get("quiet"):
            at = datetime.fromtimestamp(self.clock.now(), IST)
            minute = at.hour * 60 + at.minute
            start, end = (_minutes(prefs["quiet_from"]), _minutes(prefs["quiet_to"]))
            inside = start <= minute < end if start <= end else (minute >= start or minute < end)
            if start != end and inside:
                return f"quiet hours {prefs['quiet_from']} to {prefs['quiet_to']}"
        return None

    def _send_family(self, v: dict, body: str, kind: str = "update") -> None:
        reason = self._muted_reason(self.family_prefs(v["family_phone"]), kind)
        status = f"muted: {reason}" if reason else self.messenger.send(v["family_phone"], body)
        self.db.execute(
            "INSERT INTO messages (visit_id, to_phone, body, channel, status, at) VALUES (?, ?, ?, ?, ?, ?)",
            (v["id"], v["family_phone"], body, self.messenger.name, status, self.clock.now()),
        )

    def _set_state(self, visit_id: int, state: str, next_action_at: float | None = None) -> None:
        self.db.execute("UPDATE visits SET state = ?, next_action_at = ? WHERE id = ?", (state, next_action_at, visit_id))
        self._event(visit_id, f"State: {state.replace('_', ' ')}")

    def _event(self, visit_id: int, text: str) -> None:
        self.db.execute("INSERT INTO events (visit_id, text, at) VALUES (?, ?, ?)", (visit_id, text, self.clock.now()))

    def _observations_for(self, v: dict) -> list[Observation]:
        day = _ist_date(v["appointment_at"])
        rows = self.db.all(
            "SELECT * FROM observations WHERE doctor_id = ? AND kind IN ('token_now', 'doctor_in', 'patients_ahead')",
            (v["doctor_id"],),
        )
        out = []
        for o in rows:
            if _ist_date(o["at"]) != day:
                continue
            if o["kind"] in VISIT_LEVEL_KINDS and o["visit_id"] != v["id"]:
                continue
            out.append(Observation(o["kind"], o["value"], o["at"]))
        return out

    def _session_days(self, doctor_id: int, exclude_visit: int | None) -> list[list[dict]]:
        rows = self.db.all(
            "SELECT * FROM observations WHERE doctor_id = ? AND kind = 'token_now' AND visit_id IS NOT ? ORDER BY at",
            (doctor_id, exclude_visit),
        )
        days: dict[str, list[dict]] = {}
        for o in rows:
            days.setdefault(_ist_date(o["at"]), []).append(o)
        return list(days.values())

    def _waited_min(self, visit_id: int) -> float | None:
        arrived = self.db.one("SELECT at FROM observations WHERE visit_id = ? AND kind = 'arrived'", (visit_id,))
        called = self.db.one("SELECT at FROM observations WHERE visit_id = ? AND kind = 'called_in'", (visit_id,))
        if arrived and called:
            return max((called["at"] - arrived["at"]) / MIN, 0)
        return None


def _minutes(hhmm_text: str) -> int:
    hours, minutes = hhmm_text.split(":")
    return int(hours) * 60 + int(minutes)


def _ist_date(ts: float) -> str:
    return datetime.fromtimestamp(ts, IST).date().isoformat()


def _int_or_none(x) -> int | None:
    return None if x in (None, "") else int(x)


def _describe(kind: str, value: float) -> str:
    return {
        "token_now": f"token {int(value)} is running",
        "patients_ahead": f"{int(value)} patients ahead",
        "doctor_in": "doctor is in" if value else "doctor not in yet",
        "left": "left home",
        "arrived": "arrived at hospital",
        "called_in": "called in to see the doctor",
        "done": "visit done",
    }[kind]
