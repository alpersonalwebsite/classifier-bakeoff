"""Shared fixtures.

These tests exercise parsing, scoring, recording and report code. The HTTP
responses below are hand-written from OpenRouter's documented shapes, so a
passing adapter test shows the code reads that shape, not that OpenRouter
sends it. Only a real run can show that (constitution Principle 3).
"""

import json

import httpx2
import pytest

from bakeoff.questions import QUESTIONS

FAKE_KEY = "sk-or-test-0000000000000000"


@pytest.fixture(autouse=True)
def fake_key(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", FAKE_KEY)


def mock(handler):
    return httpx2.MockTransport(handler)


def json_response(body: dict, status: int = 200) -> httpx2.Response:
    return httpx2.Response(status, json=body)


def make_dataset(n: int = 4) -> list[dict]:
    return [
        {
            "id": f"m{i + 1:03d}",
            "text": f"Hi, I want to buy a house. Call me at 206-555-01{i % 10}0.",
            "truth": {"intent": ["buy"], "timeline": ["unknown"], "wants_contact": ["yes"], "urgency": ["normal"]},
        }
        for i in range(n)
    ]


ALL_RIGHT = {"intent": "buy", "timeline": "unknown", "wants_contact": "yes", "urgency": "normal"}


def chat_body(answers: dict, cost: float | None = 0.00022, finish_reason: str = "stop") -> dict:
    usage = {"prompt_tokens": 120, "completion_tokens": 20, "total_tokens": 140}
    if cost is not None:
        usage["cost"] = cost
    return {
        "id": "gen-test",
        "model": "anthropic/claude-haiku-4.5",
        "provider": "Anthropic",
        "choices": [{"index": 0, "finish_reason": finish_reason, "message": {"role": "assistant", "content": json.dumps(answers)}}],
        "usage": usage,
    }


def decisions_body(answers: dict, cost: float = 0.000008) -> dict:
    return {
        "id": "gen-dec-test",
        "model": "openai/gpt-6-luna-decisions",
        "provider": "OpenAI",
        "answers": answers,
        "usage": {"input_tokens": 80, "output_tokens": 0, "cost": cost},
    }


def choice(label: str) -> dict:
    return {"type": "choice", "choice": label, "confidence": 0.9, "probabilities": {label: 0.9}}


def question_names() -> list[str]:
    return [q.name for q in QUESTIONS]
