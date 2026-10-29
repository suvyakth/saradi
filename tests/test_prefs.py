import unittest

from saradi.clock import FixedClock, ist
from saradi.db import DB
from saradi.engine import Engine
from saradi.voice import SimulatedVoice
from tests.test_engine import DAY, new_visit

FAMILY = "+358400000001"


class SpyMessenger:
    name = "spy"

    def __init__(self):
        self.sent = []

    def send(self, to, body):
        self.sent.append(body)
        return "sent"


def make(start_hour=10):
    clock = FixedClock(ist(*DAY, start_hour))
    spy = SpyMessenger()
    return Engine(DB(":memory:"), clock, SimulatedVoice(), spy), clock, spy


def statuses(engine):
    return [m["status"] for m in engine.db.all("SELECT status FROM messages ORDER BY id")]


class Preferences(unittest.TestCase):
    def test_defaults_send_everything(self):
        e, clock, spy = make()
        self.assertEqual(e.family_prefs(FAMILY)["plan"], True)
        self.assertFalse(e.family_prefs(FAMILY)["quiet"])

    def test_muted_kind_is_recorded_but_not_sent(self):
        e, clock, spy = make()
        e.set_family_prefs(FAMILY, {"plan": False})
        new_visit(e)
        clock.advance(5)
        e.tick()  # morning plan would go out now
        self.assertEqual(spy.sent, [])
        self.assertTrue(statuses(e)[0].startswith("muted: you turned off"))

    def test_other_kinds_still_sent_when_one_is_muted(self):
        e, clock, spy = make()
        e.set_family_prefs(FAMILY, {"plan": False})
        vid = new_visit(e)
        e.check_in(vid, "done")
        self.assertEqual(len(spy.sent), 1)
        self.assertIn("is done", spy.sent[0])

    def test_urgent_always_sent_even_with_everything_off(self):
        e, clock, spy = make()
        e.set_family_prefs(FAMILY, {"plan": False, "update": False, "left": False, "done": False,
                                    "quiet": True, "quiet_from": "00:00", "quiet_to": "23:59"})
        vid = new_visit(e)
        clock.advance(125)
        e.tick()
        call = e.db.one("SELECT id FROM calls WHERE purpose = 'leave'")
        e.call_result(call["id"], "unwell")
        self.assertEqual(len(spy.sent), 1)
        self.assertIn("URGENT", spy.sent[0])

    def test_urgent_cannot_be_switched_off(self):
        e, _, _ = make()
        with self.assertRaises(ValueError):
            e.set_family_prefs(FAMILY, {"urgent": False})

    def test_quiet_hours_same_day_window(self):
        e, clock, spy = make(start_hour=14)
        e.set_family_prefs(FAMILY, {"quiet": True, "quiet_from": "13:00", "quiet_to": "15:00"})
        vid = new_visit(e)
        e.check_in(vid, "done")
        self.assertEqual(spy.sent, [])
        self.assertIn("quiet hours 13:00 to 15:00", statuses(e)[0])
        clock.advance(70)  # 15:10, outside the window
        vid2 = new_visit(e, elder_name="Appa")
        e.check_in(vid2, "done")
        self.assertEqual(len(spy.sent), 1)

    def test_quiet_hours_across_midnight(self):
        e, clock, spy = make(start_hour=23)
        e.set_family_prefs(FAMILY, {"quiet": True, "quiet_from": "22:00", "quiet_to": "07:00"})
        vid = new_visit(e, appointment_at=ist(*DAY, 23, 50))
        e.check_in(vid, "done")
        self.assertEqual(spy.sent, [])  # 23:00 is inside 22:00-07:00
        clock.advance(9 * 60)  # 08:00 next day
        vid2 = new_visit(e, elder_name="Appa", appointment_at=ist(*DAY, 23, 50))
        e.check_in(vid2, "done")
        self.assertEqual(len(spy.sent), 1)

    def test_quiet_hours_off_by_default_even_with_times_set(self):
        e, clock, spy = make(start_hour=23)
        e.set_family_prefs(FAMILY, {"quiet_from": "22:00", "quiet_to": "07:00"})
        vid = new_visit(e, appointment_at=ist(*DAY, 23, 50))
        e.check_in(vid, "done")
        self.assertEqual(len(spy.sent), 1)

    def test_empty_window_never_mutes(self):
        e, clock, spy = make()
        e.set_family_prefs(FAMILY, {"quiet": True, "quiet_from": "10:00", "quiet_to": "10:00"})
        vid = new_visit(e)
        e.check_in(vid, "done")
        self.assertEqual(len(spy.sent), 1)

    def test_validation(self):
        e, _, _ = make()
        for bad in ({"plan": "yes"}, {"quiet_from": "25:00"}, {"quiet_to": "7pm"}, {"colour": True}):
            with self.assertRaises(ValueError, msg=str(bad)):
                e.set_family_prefs(FAMILY, bad)
        self.assertEqual(e.family_prefs(FAMILY)["quiet_from"], "22:00")  # nothing was half-saved

    def test_prefs_are_per_family_member(self):
        e, clock, spy = make()
        e.set_family_prefs(FAMILY, {"done": False})
        vid = new_visit(e, family_phone="+358400000002", family_name="Other")
        e.check_in(vid, "done")
        self.assertEqual(len(spy.sent), 1)

    def test_prefs_persist(self):
        e, _, _ = make()
        e.set_family_prefs(FAMILY, {"left": False})
        e.set_family_prefs(FAMILY, {"quiet": True})
        p = e.family_prefs(FAMILY)
        self.assertFalse(p["left"])
        self.assertTrue(p["quiet"])


class DemoReset(unittest.TestCase):
    def test_demo_restores_default_notification_settings(self):
        from saradi.server import App
        e, _, _ = make()
        e.set_family_prefs(FAMILY, {"plan": False, "done": False, "quiet": True})
        App(e).demo()
        self.assertTrue(e.family_prefs(FAMILY)["plan"])
        self.assertTrue(e.family_prefs(FAMILY)["done"])
        self.assertFalse(e.family_prefs(FAMILY)["quiet"])

    def test_demo_survives_blank_env_values(self):
        import os
        from unittest import mock
        from saradi.server import App
        blank = {k: "" for k in ("SARADI_DEMO_ELDER_NAME", "SARADI_DEMO_ELDER_PHONE", "SARADI_DEMO_LANGUAGE",
                                 "SARADI_DEMO_FAMILY_NAME", "SARADI_DEMO_FAMILY_PHONE")}
        e, _, _ = make()
        with mock.patch.dict(os.environ, blank):
            App(e).demo()  # used to fail with "missing: family_phone"
        self.assertEqual(len(e.db.all("SELECT id FROM visits")), 1)


if __name__ == "__main__":
    unittest.main()
