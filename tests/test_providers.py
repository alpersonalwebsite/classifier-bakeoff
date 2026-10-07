"""Adapters against hand-written OpenRouter responses (see conftest)."""

import json

from bakeoff.providers import ClaudeProvider, DecisionsRouterProvider
from bakeoff.questions import QUESTIONS

from .conftest import ALL_RIGHT, FAKE_KEY, chat_body, choice, decisions_body, json_response, mock


def test_claude_parses_labels_and_pins_provider():
    p = ClaudeProvider("anthropic/claude-haiku-4.5", inner=mock(lambda r: json_response(chat_body(ALL_RIGHT))))
    answers = p.ask("I want to buy.", list(QUESTIONS))
    assert {k: a.label for k, a in answers.items()} == ALL_RIGHT
    sent = p.transport.last.request_body
    assert sent["provider"] == {"only": ["anthropic"], "allow_fallbacks": False}
    assert sent["reasoning"] == {"effort": "none"}
    assert sent["response_format"]["json_schema"]["strict"] is True
    assert p.transport.last.response_body["usage"]["cost"] == 0.00022


def test_sonnet_uses_minimal_reasoning():
    p = ClaudeProvider("anthropic/claude-sonnet-5.5", inner=mock(lambda r: json_response(chat_body(ALL_RIGHT))))
    p.ask("x", list(QUESTIONS))
    assert p.transport.last.request_body["reasoning"] == {"effort": "minimal"}


def test_claude_refusal_marks_every_question_refused():
    body = chat_body({}, finish_reason="content_filter")
    p = ClaudeProvider("anthropic/claude-haiku-4.5", inner=mock(lambda r: json_response(body)))
    assert {a.status for a in p.ask("x", list(QUESTIONS)).values()} == {"refused"}


def test_decisions_maps_choice_invalid_and_missing():
    answers = {"intent": choice("buy"), "wants_contact": choice("maybe"), "timeline": {"type": "refusal"}}
    p = DecisionsRouterProvider("openai/gpt-6-luna-decisions", "openai", inner=mock(lambda r: json_response(decisions_body(answers))))
    out = p.ask("x", list(QUESTIONS))
    assert out["intent"].status == "answered" and out["intent"].label == "buy"
    assert out["timeline"].status == "refused"
    assert out["wants_contact"].status == "invalid"  # outside the allowed labels
    assert out["urgency"].status == "invalid"  # missing from the response
    assert p.transport.last.request_body["provider"] == {"only": ["openai"], "allow_fallbacks": False}


def test_jev_and_decisions_send_the_same_request_shape():
    bodies = {}
    for model, vendor in (("typesafe/jev-1.13", "typesafe"), ("openai/gpt-6-luna-decisions", "openai")):
        p = DecisionsRouterProvider(model, vendor, inner=mock(lambda r: json_response(decisions_body({}))))
        p.ask("same text", list(QUESTIONS))
        b = dict(p.transport.last.request_body)
        b.pop("model"), b.pop("provider")
        bodies[model] = b
    a, b = bodies.values()
    assert a == b


def test_b1_question_and_label_text_identical_across_kinds():
    raw = []
    for p in (
        ClaudeProvider("anthropic/claude-haiku-4.5", inner=mock(lambda r: (raw.append(r.content.decode()), json_response(chat_body(ALL_RIGHT)))[1])),
        DecisionsRouterProvider("typesafe/jev-1.13", "typesafe", inner=mock(lambda r: (raw.append(r.content.decode()), json_response(decisions_body({})))[1])),
    ):
        p.ask("x", list(QUESTIONS))
    for body in raw:
        text = json.dumps(json.loads(body), ensure_ascii=False)
        for q in QUESTIONS:
            assert q.text in text, q.name
            for label in q.labels:
                assert json.dumps(label) in text, label


def test_b5_no_key_in_recorded_request():
    for p in (
        ClaudeProvider("anthropic/claude-haiku-4.5", inner=mock(lambda r: json_response(chat_body(ALL_RIGHT)))),
        DecisionsRouterProvider("typesafe/jev-1.13", "typesafe", inner=mock(lambda r: json_response(decisions_body({})))),
    ):
        p.ask("x", list(QUESTIONS))
        recorded = json.dumps([p.transport.last.request_headers, p.transport.last.request_body])
        assert FAKE_KEY not in recorded
