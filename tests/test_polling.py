import unittest

from saradi.clock import FixedClock, ist
from saradi.db import DB
from saradi.engine import Engine
from saradi.messaging import SimulatedMessenger
from saradi.server import App


class FakeBolna:
    name = "bolna"

    def __init__(self):
        self.results = {}

    def place_call(self, call_id, phone, variables):
        return f"exec-{call_id}", "queued"

    def fetch_execution(self, execution_id):
        return self.results.get(execution_id, {"id": execution_id, "status": "ringing"})


class BolnaPolling(unittest.TestCase):
    def test_polled_result_moves_visit(self):
        voice = FakeBolna()
        clock = FixedClock(ist(2026, 10, 20, 12, 10))
        engine = Engine(DB(":memory:"), clock, voice, SimulatedMessenger())
        vid = engine.create_visit(dict(
            elder_name="Ajji", elder_phone="+919800000001", family_name="S", family_phone="+358400000001",
            doctor_name="Dr. Rao", hospital="Manipal", appointment_at=ist(2026, 10, 20, 13), travel_min=40))
        engine.tick()
        self.assertEqual(engine.visit(vid)["state"], "calling")
        app = App(engine)

        app.poll_bolna_calls()
        self.assertEqual(engine.visit(vid)["state"], "calling")  # still ringing

        call = engine.db.one("SELECT external_id FROM calls ORDER BY id DESC LIMIT 1")
        voice.results[call["external_id"]] = {
            "id": call["external_id"], "status": "completed", "extracted_data": {"elder_response": "leaving"}}
        app.bolna_polled = 0
        app.poll_bolna_calls()
        self.assertEqual(engine.visit(vid)["state"], "en_route")


if __name__ == "__main__":
    unittest.main()
