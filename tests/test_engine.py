import unittest

from saradi.clock import FixedClock, ist
from saradi.db import DB
from saradi.engine import Engine
from saradi.messaging import SimulatedMessenger
from saradi.voice import SimulatedVoice, parse_bolna_webhook

DAY = (2026, 10, 20)  # a Tuesday


def make_engine(start_hour=10):
    clock = FixedClock(ist(*DAY, start_hour))
    return Engine(DB(":memory:"), clock, SimulatedVoice(), SimulatedMessenger()), clock


def new_visit(engine, **kw):
    data = dict(elder_name="Ajji", elder_phone="+919800000001", family_name="Suvyakth",
                family_phone="+358400000001", doctor_name="Dr. Rao", hospital="Manipal",
                appointment_at=ist(*DAY, 13), patient_token=21, travel_min=40)
    data.update(kw)
    return engine.create_visit(data)


def state(engine, vid):
    return engine.visit(vid)["state"]


def last_call(engine, vid):
    return engine.db.one("SELECT * FROM calls WHERE visit_id = ? ORDER BY id DESC LIMIT 1", (vid,))


def messages(engine):
    return [m["body"] for m in engine.db.all("SELECT body FROM messages ORDER BY id")]


class ColdStartFlow(unittest.TestCase):
    def test_brief_then_leave_call_at_usual_time(self):
        e, clock = make_engine()
        vid = new_visit(e)
        e.tick()
        self.assertEqual(state(e, vid), "scheduled")  # brief comes 2h before 12:05
        clock.advance(5)
        e.tick()
        self.assertEqual(state(e, vid), "watching")
        self.assertEqual(last_call(e, vid)["purpose"], "brief")
        self.assertTrue(any("no data on this doctor yet" in m for m in messages(e)))
        clock.advance(120)  # 12:05
        e.tick()
        self.assertEqual(state(e, vid), "calling")
        self.assertEqual(last_call(e, vid)["purpose"], "leave")

    def test_live_token_delays_the_leave_call(self):
        e, clock = make_engine()
        vid = new_visit(e, patient_token=30)
        clock.advance(5)
        e.tick()
        clock.advance(100)  # 11:45: token 2 running, 28 patients ahead of Ajji
        e.check_in(vid, "token_now", 2, source="family")
        clock.advance(20)  # 12:05: would be "leave now" without live data
        e.tick()
        self.assertEqual(state(e, vid), "watching")
        self.assertTrue(any("Leave time moved later" in m for m in messages(e)))

    def test_token_shared_across_patients_of_same_doctor(self):
        e, clock = make_engine()
        a = new_visit(e)
        b = new_visit(e, elder_name="Thatha", patient_token=30)
        e.check_in(a, "token_now", 5)
        self.assertEqual(e.predict(b).source, "live")


class ElderResponses(unittest.TestCase):
    def _at_leave_call(self):
        e, clock = make_engine(12)
        vid = new_visit(e)
        clock.advance(10)
        e.tick()
        self.assertEqual(state(e, vid), "calling")
        return e, clock, vid

    def test_leaving_tells_family(self):
        e, _, vid = self._at_leave_call()
        e.call_result(last_call(e, vid)["id"], "leaving")
        self.assertEqual(state(e, vid), "en_route")
        self.assertIn("has left", messages(e)[-1])

    def test_two_no_answers_alert_family(self):
        e, clock, vid = self._at_leave_call()
        e.call_result(last_call(e, vid)["id"], "no_answer")
        self.assertEqual(state(e, vid), "retry")
        clock.advance(3)
        e.tick()
        self.assertEqual(state(e, vid), "calling")
        e.call_result(last_call(e, vid)["id"], "no_answer")
        self.assertEqual(state(e, vid), "needs_family")
        self.assertIn("did not answer twice", messages(e)[-1])

    def test_unwell_is_urgent(self):
        e, _, vid = self._at_leave_call()
        e.call_result(last_call(e, vid)["id"], "unwell")
        self.assertEqual(state(e, vid), "needs_family")
        self.assertIn("URGENT", messages(e)[-1])

    def test_duplicate_webhook_is_ignored(self):
        e, _, vid = self._at_leave_call()
        cid = last_call(e, vid)["id"]
        e.call_result(cid, "leaving")
        e.call_result(cid, "unwell")
        self.assertEqual(state(e, vid), "en_route")


class Learning(unittest.TestCase):
    def test_completed_visit_becomes_history(self):
        e, clock = make_engine(12)
        vid = new_visit(e)
        clock.advance(60 + 150)  # called in at 15:30, 150 min late
        e.check_in(vid, "arrived")
        e.check_in(vid, "called_in")
        e.check_in(vid, "done")
        self.assertEqual(state(e, vid), "done")
        self.assertIn("added to Dr. Rao's timing history", messages(e)[-1])
        nxt = new_visit(e, appointment_at=ist(2026, 10, 27, 13))
        p = e.predict(nxt)
        self.assertEqual(p.source, "history")
        self.assertEqual(p.samples, 1)

    def test_reported_past_wait_seeds_history(self):
        e, _ = make_engine()
        vid = new_visit(e, past_wait_min=120)
        self.assertEqual(e.predict(vid).source, "history")


class BolnaWebhook(unittest.TestCase):
    def test_in_progress_is_ignored(self):
        self.assertEqual(parse_bolna_webhook({"id": "x", "status": "ringing"}), ("x", None))

    def test_no_answer_status(self):
        self.assertEqual(parse_bolna_webhook({"id": "x", "status": "no-answer"}), ("x", "no_answer"))

    def test_completed_reads_extracted_response(self):
        payload = {"id": "x", "status": "completed", "extracted_data": {"elder_response": "Leaving"}}
        self.assertEqual(parse_bolna_webhook(payload), ("x", "leaving"))

    def test_completed_unknown_response_is_confused(self):
        payload = {"id": "x", "status": "completed", "extracted_data": {"elder_response": "banana"}}
        self.assertEqual(parse_bolna_webhook(payload), ("x", "confused"))


if __name__ == "__main__":
    unittest.main()
