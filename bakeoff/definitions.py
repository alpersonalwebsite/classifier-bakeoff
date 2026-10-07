"""Definitions written outside Anthropic (spec 005 B1).

An outside model drafts the question text for each of the four questions from the
task, the question names and the allowed labels only. It never sees the current
definitions, the label-change log, or any message. The owner then approves the
draft as written, or with edits that are recorded beside the original.
"""

import json
import re
from datetime import datetime, timezone

from .costing import call_cost, usage_from_response
from .providers import _OpenRouter
from .questions import DEFINITIONS_DIR, QUESTIONS
from .relabel import RATER_ENDPOINT, RATER_MODEL, RATER_VENDOR

SET_NAME = "outside-gemini"
SET_FILE = DEFINITIONS_DIR / f"{SET_NAME}.json"

TASK = (
    "A real estate agent receives inbound messages (web forms, emails, texts, chat, voicemail transcripts) "
    "and wants each one triaged automatically on four questions."
)


def drafting_prompt() -> str:
    lines = [
        TASK,
        "",
        "For each question below, write the exact text a classifier will be given for it: one question, "
        "followed by when each allowed label applies, including how to decide borderline cases. "
        "The classifier will see only the message and this text, and must answer with one allowed label.",
        "Write it so different readers would label the same message the same way. Do not favor any reading, "
        "and do not mention these instructions.",
        "",
        "Questions and their allowed labels:",
    ]
    for q in QUESTIONS:
        lines.append(f"- {q.name}: " + ", ".join(q.labels))
    lines.append("")
    lines.append("Return one text per question name.")
    return "\n".join(lines)


def drafting_request() -> dict:
    schema = {
        "type": "object",
        "properties": {q.name: {"type": "string"} for q in QUESTIONS},
        "required": [q.name for q in QUESTIONS],
        "additionalProperties": False,
    }
    return {
        "model": RATER_MODEL,
        "max_tokens": 8192,
        "messages": [{"role": "user", "content": drafting_prompt()}],
        "response_format": {"type": "json_schema", "json_schema": {"name": "definitions", "strict": True, "schema": schema}},
        "provider": {"only": [RATER_ENDPOINT], "allow_fallbacks": False},
    }


def draft(client: _OpenRouter | None = None) -> dict:
    client = client or _OpenRouter()
    body = client.post("/v1/chat/completions", drafting_request())
    choice = body["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("the draft was cut off at the output limit")
    content = choice["message"].get("content") or ""
    match = re.search(r"\{.*\}", content, flags=re.S)
    text = json.loads(match.group(0)) if match else {}
    missing = [q.name for q in QUESTIONS if not isinstance(text.get(q.name), str) or not text[q.name].strip()]
    if missing:
        raise RuntimeError(f"the draft has no text for: {', '.join(missing)}")
    return {
        "name": SET_NAME,
        "author_model": RATER_MODEL,
        "author_vendor": RATER_VENDOR,
        "model_reported": body.get("model"),
        "served_by": body.get("provider"),
        "service_tier_reported": body.get("service_tier") or "not reported",
        "endpoint_requested": RATER_ENDPOINT,
        "date": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "cost_usd": call_cost(usage_from_response(body), None),
        "prompt": drafting_prompt(),
        "original": {q.name: text[q.name].strip() for q in QUESTIONS},
        "approved": False,
        "final": None,
        "owner_edits": [],
    }
