"""Adapters. Every variant goes through OpenRouter with one key (spec 001 B3).

Jev and Decisions share OpenRouter's Decisions endpoint and so receive the same
request shape. Claude goes through OpenRouter's chat completions. Each request
is pinned to the model's own vendor with no fallback, so a variant's answers
always come from the model it names.

There are no client-level retries here: the runner retries, so every attempt is
recorded (B5) and every variant gets the same retry rule.
"""

import json
import os
from dataclasses import dataclass
from typing import Protocol

import httpx2

from .questions import Question
from .recording import RecordingTransport

OPENROUTER_BASE = "https://openrouter.ai/api"
TIMEOUT_SECONDS = 30.0


class MalformedResponse(Exception):
    """An HTTP 200 whose body is not the documented shape. Retried, never scored."""


class HTTPStatusError(Exception):
    def __init__(self, status: int, body: str):
        super().__init__(f"HTTP {status}: {body[:300]}")
        self.status = status


@dataclass
class Answer:
    status: str  # "answered" | "invalid" | "refused"
    label: str | None
    raw: object = None


def judge(question: Question, value: object) -> Answer:
    """A label outside the allowed set is invalid, not an error (constitution P2)."""
    if isinstance(value, str) and value in question.labels:
        return Answer("answered", value, value)
    return Answer("invalid", None, value)


class Provider(Protocol):
    transport: RecordingTransport
    settings: dict

    def ask(self, text: str, questions: list[Question]) -> dict[str, Answer]: ...


class _OpenRouter:
    def __init__(self, inner: httpx2.BaseTransport | None = None):
        key = os.environ.get("OPENROUTER_API_KEY", "").strip()
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        self.transport = RecordingTransport(inner)
        self.http = httpx2.Client(
            transport=self.transport,
            timeout=TIMEOUT_SECONDS,
            headers={"Authorization": f"Bearer {key}", "X-Title": "classifier-bakeoff"},
        )

    def post(self, path: str, body: dict) -> dict:
        response = self.http.post(f"{OPENROUTER_BASE}{path}", json=body)
        if response.status_code >= 400:
            raise HTTPStatusError(response.status_code, response.text)
        try:
            body = response.json()
        except ValueError:
            raise MalformedResponse("response body is not JSON") from None
        if not isinstance(body, dict):
            raise MalformedResponse("response body is not a JSON object")
        return body


# --- Jev and Decisions: OpenRouter's Decisions endpoint ----------------------


def decisions_request(text: str, questions: list[Question]) -> dict:
    """Everything a Decisions-endpoint model is told, without model or routing fields."""
    return {
        "state": text,
        "questions": {
            q.name: {"type": "choice", "instructions": q.text, "criteria": {label: None for label in q.labels}}
            for q in questions
        },
    }


class DecisionsRouterProvider(_OpenRouter):
    def __init__(self, model: str, vendor: str, inner: httpx2.BaseTransport | None = None):
        super().__init__(inner)
        self.model = model
        self.vendor = vendor
        self.settings = {"model": model, "provider": vendor, "endpoint": "/api/alpha/decisions"}

    def ask(self, text: str, questions: list[Question]) -> dict[str, Answer]:
        body = self.post(
            "/alpha/decisions",
            {
                "model": self.model,
                **decisions_request(text, questions),
                "provider": {"only": [self.vendor], "allow_fallbacks": False},
            },
        )
        answers = body.get("answers")
        if not isinstance(answers, dict):
            raise MalformedResponse("no answers object in the response")
        out = {}
        for q in questions:
            a = answers.get(q.name)
            if not isinstance(a, dict):
                out[q.name] = Answer("invalid", None, a)
            elif a.get("type") == "refusal":
                out[q.name] = Answer("refused", None, a)
            else:
                out[q.name] = judge(q, a.get("choice"))
        return out


# --- Claude: OpenRouter chat completions ------------------------------------

CLAUDE_INSTRUCTION = "Read the message and answer each question with exactly one of its labels."


def claude_system_prompt(questions: list[Question]) -> str:
    lines = [CLAUDE_INSTRUCTION, "", "Questions:"]
    for q in questions:
        labels = ", ".join(q.labels)
        lines.append(f"- {q.name}: {q.text} Labels: {labels}")
    return "\n".join(lines)


def claude_schema(questions: list[Question]) -> dict:
    return {
        "type": "object",
        "properties": {q.name: {"type": "string", "enum": list(q.labels)} for q in questions},
        "required": [q.name for q in questions],
        "additionalProperties": False,
    }


# Least reasoning each model allows (spec 001 Assumptions). OpenRouter rejects
# effort "none" for Sonnet 5.5 ("Reasoning is mandatory for this endpoint"), and
# "minimal" returned 0 reasoning tokens on a smoke call on 2026-10-07.
REASONING = {
    "anthropic/claude-sonnet-5.5": {"effort": "minimal"},
    "anthropic/claude-haiku-4.5": {"effort": "none"},
}


def claude_request(text: str, questions: list[Question]) -> dict:
    """Everything a Claude variant is told, without model, reasoning or routing fields
    (reasoning is recorded per variant in its settings)."""
    return {
        "max_tokens": 256,
        "messages": [
            {"role": "system", "content": claude_system_prompt(questions)},
            {"role": "user", "content": text},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "labels", "strict": True, "schema": claude_schema(questions)},
        },
    }


class ClaudeProvider(_OpenRouter):
    def __init__(self, model: str, inner: httpx2.BaseTransport | None = None):
        super().__init__(inner)
        self.model = model
        self.reasoning = REASONING.get(model, {"effort": "none"})
        self.settings = {"model": model, "provider": "anthropic", "reasoning": self.reasoning}

    def ask(self, text: str, questions: list[Question]) -> dict[str, Answer]:
        body = self.post(
            "/v1/chat/completions",
            {
                "model": self.model,
                **claude_request(text, questions),
                "reasoning": self.reasoning,
                "provider": {"only": ["anthropic"], "allow_fallbacks": False},
            },
        )
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise MalformedResponse("no choices in the response")
        choice = choices[0]
        message = choice.get("message") or {}
        if choice.get("finish_reason") in ("content_filter", "refusal") or message.get("refusal"):
            return {q.name: Answer("refused", None, message.get("refusal")) for q in questions}
        try:
            data = json.loads(message.get("content") or "")
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        return {q.name: judge(q, data.get(q.name)) for q in questions}
