"""Narration layer: LLM prose over the finished structured plan, fail-open.

Contract (plan.md Phase 4):
- Input is the final ``Itinerary``; output is per-day prose + a trip summary.
- One OpenAI-compatible call whose prompt carries the structured plan only.
- The LLM can never add/remove/reorder places: the structured plan is never
  parsed out of LLM text (architectural guarantee), and the prose is validated
  to mention every scheduled stop (second layer).
- Any failure — missing key, timeout, HTTP error, bad JSON, validation miss —
  falls back to the template prose already on the itinerary.
"""

import json
import os

import httpx

from app import config
from app.models import Itinerary, TripRequest


class NarrationError(Exception):
    """Anything that should demote LLM prose back to template prose."""


def narrate_itinerary(
    day_summaries: list[str], trip_request: TripRequest, total_days: int
) -> str:
    """Template narration; the planner fills this so output is complete pre-LLM."""
    try:
        return build_template_narration(day_summaries, trip_request, total_days)
    except Exception:
        return "Your day-by-day plan is ready below."


def build_template_narration(
    day_summaries: list[str], trip_request: TripRequest, total_days: int
) -> str:
    """Deterministic trip summary from the finished structured plan."""
    interests = ", ".join(trip_request.interests)
    lines = [
        f"Your {total_days}-day Goa trip ({trip_request.pace.replace('_', ' ')} pace, "
        f"{trip_request.budget_level} budget) leans into {interests}."
    ]
    lines.extend(f"Day {index}: {summary}" for index, summary in enumerate(day_summaries, start=1))
    return " ".join(lines)


def is_llm_narration_enabled() -> bool:
    """Env-var driven: no key means templates only, never an error."""
    return bool(os.environ.get(config.LLM_API_KEY_ENV_VAR))


def enrich_itinerary_narration(itinerary: Itinerary) -> Itinerary:
    """Replace template prose with LLM prose; return template on any failure."""
    if not is_llm_narration_enabled():
        return itinerary
    try:
        payload = request_llm_narration(build_narration_prompt(itinerary))
        trip_summary, day_notes = validate_llm_narration(payload, itinerary)
    except NarrationError:
        return mark_template_fallback(itinerary)
    enriched_itinerary = itinerary.model_copy(deep=True)
    enriched_itinerary.summary.narration = combine_narration_text(
        trip_summary, day_notes
    )
    return enriched_itinerary


def build_narration_prompt(itinerary: Itinerary) -> list[dict]:
    """System + user messages; the user message is the structured plan only."""
    trip_request = itinerary.trip_request
    traveller_line = (
        f"{trip_request.traveller_type} party, {trip_request.pace.replace('_', ' ')} pace, "
        f"{trip_request.budget_level} budget, interests: {', '.join(trip_request.interests)}."
    )
    structured_days = [
        {
            "day": day.day_number,
            "theme": day.theme,
            "stops": [
                {
                    "name": activity.name,
                    "kind": activity.kind,
                    "time": f"{activity.start_time}-{activity.end_time}",
                    "why": activity.why,
                }
                for activity in day.activities
            ],
        }
        for day in itinerary.days
    ]
    return [
        {
            "role": "system",
            "content": (
                "You are a warm, concise travel writer. Turn the structured "
                "itinerary into inviting prose. Rules: never add, remove or "
                "reorder any stop; mention every sightseeing stop by its exact "
                "name in its day's note; keep each day to 2-3 sentences. "
                "Reply with JSON only: "
                '{"trip_summary": "...", "day_notes": ["...", ...]} '
                "with one note per day in order."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"traveller": traveller_line, "days": structured_days}
            ),
        },
    ]


def request_llm_narration(messages: list[dict]) -> dict:
    """Single OpenAI-compatible chat call; every failure mode raises NarrationError."""
    api_key = os.environ.get(config.LLM_API_KEY_ENV_VAR)
    if not api_key:
        raise NarrationError("missing LLM API key")
    base_url = os.environ.get(
        config.LLM_BASE_URL_ENV_VAR, config.LLM_DEFAULT_BASE_URL
    ).rstrip("/")
    model = os.environ.get(config.LLM_MODEL_ENV_VAR, config.LLM_DEFAULT_MODEL)
    try:
        response = httpx.post(
            f"{base_url}/chat/completions",
            json={
                "model": model,
                "messages": messages,
                "max_tokens": config.LLM_MAX_TOKENS,
                "temperature": config.LLM_TEMPERATURE,
            },
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise NarrationError(f"LLM request failed: {exc}") from exc
    # A 200 with null/empty content is still a failure — the fail-open
    # contract means this must fall back to templates, never raise TypeError.
    if not isinstance(content, str) or not content.strip():
        raise NarrationError("LLM returned empty narration content")
    return parse_narration_content(content)


def parse_narration_content(content: str) -> dict:
    """Parse the model's JSON, tolerating markdown code fences."""
    if not isinstance(content, str):
        raise NarrationError("LLM narration is not text")
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise NarrationError(f"LLM returned non-JSON prose: {exc}") from exc
    if not isinstance(payload, dict):
        raise NarrationError("LLM narration is not a JSON object")
    return payload


def validate_llm_narration(
    payload: dict, itinerary: Itinerary
) -> tuple[str, list[str]]:
    """Structural check: shape, per-day count, and every stop mentioned by name.

    Raises NarrationError so the caller falls back to templates. The structured
    itinerary is never modified — this only gates whether prose may replace it.
    """
    trip_summary = payload.get("trip_summary")
    day_notes = payload.get("day_notes")
    if not isinstance(trip_summary, str) or not trip_summary.strip():
        raise NarrationError("LLM narration lacks a trip summary")
    if not isinstance(day_notes, list) or len(day_notes) != len(itinerary.days):
        raise NarrationError("LLM narration day count mismatches the itinerary")
    if any(not isinstance(note, str) or not note.strip() for note in day_notes):
        raise NarrationError("LLM narration has an empty day note")

    for day, note in zip(itinerary.days, day_notes):
        lowered_note = note.lower()
        for activity in day.activities:
            if activity.kind != "place":
                continue
            if activity.name.lower() not in lowered_note:
                raise NarrationError(
                    f"day {day.day_number} note drops scheduled stop: {activity.name}"
                )

    combined_length = len(trip_summary) + sum(len(note) for note in day_notes)
    if combined_length > config.LLM_MAX_NARRATION_CHARS:
        raise NarrationError("LLM narration exceeds the length budget")
    return trip_summary.strip(), [note.strip() for note in day_notes]


def combine_narration_text(trip_summary: str, day_notes: list[str]) -> str:
    """Single narration string: summary plus one labelled note per day."""
    labelled_days = [
        f"Day {day_number}: {note}"
        for day_number, note in enumerate(day_notes, start=1)
    ]
    return " ".join([trip_summary, *labelled_days])


def mark_template_fallback(itinerary: Itinerary) -> Itinerary:
    """Keep the template prose and say so honestly in the assumptions."""
    fallback_itinerary = itinerary.model_copy(deep=True)
    if config.LLM_FALLBACK_ASSUMPTION not in fallback_itinerary.assumptions:
        fallback_itinerary.assumptions = sorted(
            [*fallback_itinerary.assumptions, config.LLM_FALLBACK_ASSUMPTION]
        )
    return fallback_itinerary
