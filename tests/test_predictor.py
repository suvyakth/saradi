import unittest

from saradi.predictor import MIN, DoctorHistory, Observation, VisitInput, blend, predict, PRIOR_DELAY_MIN

APPT = 1_000_000.0


def visit(**kw):
    base = dict(appointment_at=APPT, patient_token=21, travel_min=40, buffer_min=15, weekday=1)
    base.update(kw)
    return VisitInput(**base)


class ColdStart(unittest.TestCase):
    def test_no_data_means_leave_as_usual(self):
        p = predict(visit(), DoctorHistory())
        self.assertEqual(p.source, "prior")
        # With nothing known, the safe plan is the normal one: arrive for the appointment.
        self.assertEqual(p.turn_p10, APPT)
        self.assertEqual(p.leave_at, APPT - 55 * MIN)
        self.assertGreater(p.turn_p90, p.turn_p50)

    def test_one_reported_wait_shifts_estimate_but_not_fully(self):
        h = DoctorHistory(delays=[(-1, 120.0)])
        p = predict(visit(), h)
        self.assertEqual(p.source, "history")
        self.assertGreater(p.turn_p50, APPT + PRIOR_DELAY_MIN["p50"] * MIN)
        self.assertLess(p.turn_p50, APPT + 120 * MIN)

    def test_blend_moves_toward_data_with_more_samples(self):
        few = blend([120.0], PRIOR_DELAY_MIN)["p50"]
        many = blend([120.0] * 20, PRIOR_DELAY_MIN)["p50"]
        self.assertLess(few, many)
        self.assertLess(many, 120.0)


class LiveData(unittest.TestCase):
    def test_token_running_gives_live_window(self):
        obs = [Observation("token_now", 14, APPT + 60 * MIN)]
        p = predict(visit(observations=obs), DoctorHistory())
        self.assertEqual(p.source, "live")
        # 7 patients ahead, prior 4-12 min each
        self.assertAlmostEqual(p.turn_p10, APPT + 60 * MIN + 7 * 4 * MIN)
        self.assertAlmostEqual(p.turn_p90, APPT + 60 * MIN + 7 * 12 * MIN)

    def test_two_token_readings_learn_todays_pace(self):
        obs = [Observation("token_now", 10, APPT), Observation("token_now", 14, APPT + 60 * MIN)]
        p = predict(visit(observations=obs), DoctorHistory())
        # 15 min per patient today pulls the median above the 7-min prior
        self.assertGreater(p.turn_p50, APPT + 60 * MIN + 7 * 7 * MIN)

    def test_token_already_passed_means_now(self):
        obs = [Observation("token_now", 25, APPT)]
        p = predict(visit(observations=obs), DoctorHistory())
        self.assertEqual(p.turn_p10, APPT)

    def test_patients_ahead_without_token(self):
        obs = [Observation("patients_ahead", 3, APPT + 30 * MIN)]
        p = predict(visit(patient_token=None, observations=obs), DoctorHistory())
        self.assertEqual(p.source, "live")
        self.assertAlmostEqual(p.turn_p10, APPT + 30 * MIN + 3 * 4 * MIN)

    def test_doctor_not_in_pushes_window_later(self):
        late = APPT + 90 * MIN
        p = predict(visit(observations=[Observation("doctor_in", 0, late)]), DoctorHistory())
        self.assertGreaterEqual(p.turn_p10, late + 5 * MIN)
        self.assertLessEqual(p.turn_p10, p.turn_p50)
        self.assertLessEqual(p.turn_p50, p.turn_p90)


if __name__ == "__main__":
    unittest.main()
