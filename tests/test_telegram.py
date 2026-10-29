import unittest

from saradi.clock import FixedClock, ist
from saradi.db import DB
from saradi.engine import Engine
from saradi.messaging import TelegramMessenger
from saradi.voice import SimulatedVoice

DAY = (2026, 10, 20)


class FakeTelegram:
    """Stands in for api.telegram.org: records what the bot sends, serves queued updates."""

    def __init__(self):
        self.sent, self.updates = [], []

    def __call__(self, method, payload):
        if method == "getMe":
            return {"ok": True, "result": {"username": "SaradiBot"}}
        if method == "getUpdates":
            offset = payload.get("offset", 0)
            return {"ok": True, "result": [u for u in self.updates if u["update_id"] >= offset]}
        if method == "sendMessage":
            self.sent.append((str(payload["chat_id"]), payload["text"]))
            return {"ok": True}
        return None

    def user_says(self, update_id, chat_id, text):
        self.updates.append({"update_id": update_id, "message": {"chat": {"id": chat_id}, "text": text}})


def setup():
    db, tg = DB(":memory:"), FakeTelegram()
    messenger = TelegramMessenger("token", db, transport=tg)
    engine = Engine(db, FixedClock(ist(*DAY, 12, 10)), SimulatedVoice(), messenger)
    vid = engine.create_visit(dict(
        elder_name="Ajji", elder_phone="+919800000001", family_name="Suvyakth", family_phone="+358400000001",
        doctor_name="Dr. Rao", hospital="Manipal", appointment_at=ist(*DAY, 13), travel_min=40))
    return engine, messenger, tg, vid


def code_of(messenger):
    return messenger.link_url("+358400000001").split("start=")[1]


class TelegramLinking(unittest.TestCase):
    def test_alerts_wait_until_family_connects(self):
        engine, messenger, tg, vid = setup()
        engine.tick()  # leave time already reached, so family messages go out
        status = engine.db.one("SELECT status FROM messages ORDER BY id LIMIT 1")["status"]
        self.assertEqual(status, "not connected")
        self.assertEqual(tg.sent, [])

    def test_start_with_code_links_chat_and_alerts_arrive(self):
        engine, messenger, tg, vid = setup()
        self.assertFalse(messenger.is_linked("+358400000001"))
        tg.user_says(1, 555, f"/start {code_of(messenger)}")
        messenger.poll()
        self.assertTrue(messenger.is_linked("+358400000001"))
        self.assertIn("Connected", tg.sent[-1][1])
        self.assertEqual(tg.sent[-1][0], "555")
        status = messenger.send("+358400000001", "hello")
        self.assertEqual(status, "sent")
        self.assertEqual(tg.sent[-1], ("555", "hello"))

    def test_link_url_contains_random_code_not_phone_number(self):
        _, messenger, _, _ = setup()
        url = messenger.link_url("+358400000001")
        self.assertTrue(url.startswith("https://t.me/SaradiBot?start="))
        self.assertNotIn("358400000001", url)

    def test_bad_code_and_stolen_code_are_refused(self):
        engine, messenger, tg, vid = setup()
        tg.user_says(1, 777, "/start nonsense")
        messenger.poll()
        self.assertIn("isn't valid", tg.sent[-1][1])
        self.assertFalse(messenger.is_linked("+358400000001"))
        code = code_of(messenger)
        tg.user_says(2, 555, f"/start {code}")
        tg.user_says(3, 888, f"/start {code}")
        messenger.poll()
        self.assertIn("already connected", tg.sent[-1][1])
        self.assertEqual(messenger.send("+358400000001", "x"), "sent")
        self.assertEqual(tg.sent[-1][0], "555")

    def test_bare_start_explains_how_to_connect(self):
        _, messenger, tg, _ = setup()
        tg.user_says(1, 555, "/start")
        messenger.poll()
        self.assertIn("connect link", tg.sent[-1][1])

    def test_same_family_member_keeps_one_code_across_visits(self):
        engine, messenger, tg, vid = setup()
        first = code_of(messenger)
        engine.create_visit(dict(
            elder_name="Thatha", elder_phone="+919800000002", family_name="Suvyakth",
            family_phone="+358400000001", doctor_name="Dr. Rao", hospital="Manipal",
            appointment_at=ist(*DAY, 14), travel_min=30))
        self.assertEqual(code_of(messenger), first)


if __name__ == "__main__":
    unittest.main()
