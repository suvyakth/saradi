"""Turn-time prediction that works from zero data upward.

Signals, strongest first:
  live     - token / patients-ahead / doctor-in observations for this visit
  history  - this doctor's past delays (completed visits + what families told us)
  prior    - generic Indian OPD assumptions, used when we know nothing

Every estimate is a range (p10 / p50 / p90). We plan the "leave" time off p10 so
an elder is early rather than late; being wrong costs a short wait, not a missed turn.
"""
from __future__ import annotations

from dataclasses import dataclass, field

MIN = 60.0

# Assumptions, not measurements. Indian OPD studies report mean waits of roughly
# 30-100 min and consults of ~6-7 min; the spread here is deliberately wide.
PRIOR_DELAY_MIN = {"p10": 0.0, "p50": 45.0, "p90": 150.0}
PRIOR_CONSULT_MIN = {"p10": 4.0, "p50": 7.0, "p90": 12.0}
# How many "pseudo-visits" the prior is worth when blended with real samples.
PRIOR_WEIGHT = 3.0
SAME_WEEKDAY_MIN_SAMPLES = 5


@dataclass
class Observation:
    kind: str  # token_now | patients_ahead | doctor_in
    value: float
    at: float  # epoch seconds


@dataclass
class VisitInput:
    appointment_at: float
    patient_token: int | None
    travel_min: float
    buffer_min: float
    weekday: int
    observations: list[Observation] = field(default_factory=list)


@dataclass
class DoctorHistory:
    # (weekday, minutes from appointment to being called in)
    delays: list[tuple[int, float]] = field(default_factory=list)
    # minutes per patient seen in past sessions
    consult_rates: list[float] = field(default_factory=list)


@dataclass
class Prediction:
    source: str
    turn_p10: float
    turn_p50: float
    turn_p90: float
    leave_at: float
    basis: str
    samples: int

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def quantile(values: list[float], q: float) -> float:
    s = sorted(values)
    if not s:
        raise ValueError("no values")
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def blend(samples: list[float], prior: dict[str, float]) -> dict[str, float]:
    """Shrink small-sample quantiles toward the prior."""
    n = len(samples)
    if n == 0:
        return dict(prior)
    out = {}
    for key, q in (("p10", 0.1), ("p50", 0.5), ("p90", 0.9)):
        out[key] = (n * quantile(samples, q) + PRIOR_WEIGHT * prior[key]) / (n + PRIOR_WEIGHT)
    return out


def delay_quantiles(history: DoctorHistory, weekday: int) -> tuple[dict[str, float], int, str]:
    same_day = [d for wd, d in history.delays if wd == weekday]
    if len(same_day) >= SAME_WEEKDAY_MIN_SAMPLES:
        return blend(same_day, PRIOR_DELAY_MIN), len(same_day), "same weekday"
    all_days = [d for _, d in history.delays]
    return blend(all_days, PRIOR_DELAY_MIN), len(all_days), "all days"


def consult_quantiles(history: DoctorHistory, obs: list[Observation]) -> dict[str, float]:
    samples = list(history.consult_rates)
    live = live_consult_rate(obs)
    if live is not None:
        # The current session says more about today than any history does.
        samples += [live] * 3
    return blend(samples, PRIOR_CONSULT_MIN)


def live_consult_rate(obs: list[Observation]) -> float | None:
    tokens = sorted((o for o in obs if o.kind == "token_now"), key=lambda o: o.at)
    if len(tokens) < 2:
        return None
    first, last = tokens[0], tokens[-1]
    advanced = last.value - first.value
    if advanced < 2:
        return None
    return (last.at - first.at) / MIN / advanced


def predict(visit: VisitInput, history: DoctorHistory) -> Prediction:
    rate = consult_quantiles(history, visit.observations)
    latest = _latest_by_kind(visit.observations)

    token_obs = latest.get("token_now")
    ahead_obs = latest.get("patients_ahead")
    live = None
    if token_obs and visit.patient_token is not None:
        remaining = max(visit.patient_token - token_obs.value, 0)
        live = (token_obs.at, remaining, f"token {int(token_obs.value)} running, you are {visit.patient_token}")
    if ahead_obs and (live is None or ahead_obs.at > live[0]):
        live = (ahead_obs.at, max(ahead_obs.value, 0), f"{int(ahead_obs.value)} patients ahead")

    if live is not None:
        at, remaining, why = live
        p10 = at + remaining * rate["p10"] * MIN
        p50 = at + remaining * rate["p50"] * MIN
        p90 = at + remaining * rate["p90"] * MIN
        return _finish("live", p10, p50, p90, visit, why, len(history.consult_rates))

    delays, n, scope = delay_quantiles(history, visit.weekday)
    source = "history" if n else "prior"
    p10 = visit.appointment_at + delays["p10"] * MIN
    p50 = visit.appointment_at + delays["p50"] * MIN
    p90 = visit.appointment_at + delays["p90"] * MIN
    why = (f"this doctor's past delays ({n} visits, {scope})" if n
           else "no data yet for this doctor, using generic OPD assumptions")

    doctor_in = latest.get("doctor_in")
    if doctor_in is not None:
        position = max((visit.patient_token or 1) - 1, 0)
        if doctor_in.value:
            # Started by this time at the latest; nobody knows how far they've got.
            p10 = max(min(p10, doctor_in.at + position * rate["p10"] * MIN * 0.5), doctor_in.at)
            p90 = max(p90, doctor_in.at + position * rate["p90"] * MIN)
            why = "doctor is in" + (f", you are token {visit.patient_token}" if visit.patient_token else "")
        else:
            # Not started yet: nobody is seen before he arrives.
            floor = doctor_in.at + 5 * MIN + position * rate["p10"] * MIN
            p10 = max(p10, floor)
            p50 = max(p50, floor + position * (rate["p50"] - rate["p10"]) * MIN + 15 * MIN)
            p90 = max(p90, p50 + 60 * MIN)
            why = "doctor not in yet"
        source = "live"
    p50 = max(p50, p10)
    p90 = max(p90, p50)
    return _finish(source, p10, p50, p90, visit, why, n)


def _finish(source, p10, p50, p90, visit, why, samples) -> Prediction:
    leave_at = p10 - (visit.travel_min + visit.buffer_min) * MIN
    return Prediction(source, p10, p50, p90, leave_at, why, samples)


def _latest_by_kind(obs: list[Observation]) -> dict[str, Observation]:
    latest: dict[str, Observation] = {}
    for o in sorted(obs, key=lambda o: o.at):
        latest[o.kind] = o
    return latest
