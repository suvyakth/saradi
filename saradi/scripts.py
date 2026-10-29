"""What Saradi says. English source text; the Bolna agent speaks it in the elder's language.

Keep elder scripts short, concrete and in the elder's own terms: a time, a token, one action.
"""
from __future__ import annotations

from .clock import hhmm


def brief_call(v: dict, p) -> str:
    return (
        f"Namaskara {v['elder_name']}, this is Saradi calling for {v['family_name']}. "
        f"Your appointment with {v['doctor_name']} at {v['hospital']} is at {hhmm(v['appointment_at'])}. "
        f"Please be ready by {hhmm(p.leave_at)}. Don't leave yet. We will call you again when it is time to go."
    )


def leave_call(v: dict, p) -> str:
    where = f" ({p.basis})" if p.source == "live" else ""
    return (
        f"{v['elder_name']}, it is time to leave now for {v['doctor_name']}{where}. "
        f"The journey takes about {int(v['travel_min'])} minutes. Are you leaving now?"
    )


def family_brief(v: dict, p) -> str:
    lines = [
        f"Saradi: {v['elder_name']}'s visit to {v['doctor_name']} ({v['hospital']}), appointment {hhmm(v['appointment_at'])}.",
        f"Plan: be ready by {hhmm(p.leave_at)}. Likely seen between {hhmm(p.turn_p10)} and {hhmm(p.turn_p90)}.",
    ]
    if p.source != "prior":
        lines.append(f"Based on: {p.basis}.")
    if p.source == "prior":
        lines.append(
            "We have no data on this doctor yet, so this is the usual time. To do better today: "
            "forward the hospital's live token link if they send one, or call reception once when OPD starts "
            "and tell us the token that's running."
        )
    return "\n".join(lines)


def family_update(v: dict, p, old_leave: float) -> str:
    direction = "later" if p.leave_at > old_leave else "earlier"
    return (
        f"Saradi: update for {v['elder_name']}. Leave time moved {direction}: now {hhmm(p.leave_at)} "
        f"(was {hhmm(old_leave)}). Based on: {p.basis}."
    )


def family_left(v: dict) -> str:
    return f"Saradi: {v['elder_name']} has left for {v['doctor_name']}."


def family_unwell(v: dict) -> str:
    return f"Saradi URGENT: {v['elder_name']} said they are not feeling well. Please call them now: {v['elder_phone']}."


def family_no_answer(v: dict) -> str:
    return (
        f"Saradi: {v['elder_name']} did not answer twice. It is time to leave for {v['doctor_name']}. "
        f"Please call them: {v['elder_phone']}."
    )


def family_confused(v: dict) -> str:
    return (
        f"Saradi: {v['elder_name']} wasn't sure who was calling. Please call them and tell them to leave now "
        f"for {v['doctor_name']}: {v['elder_phone']}."
    )


def family_done(v: dict, waited_min: float | None) -> str:
    wait = f" Waited about {int(waited_min)} min at the hospital." if waited_min is not None else ""
    return (
        f"Saradi: {v['elder_name']}'s visit with {v['doctor_name']} is done.{wait} "
        f"This visit has been added to {v['doctor_name']}'s timing history, so the next visit's estimate gets better.\n"
        f"If you'd like, share your experience of {v['hospital']} on Google."
    )
