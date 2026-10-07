"""Spec 004: the blind outside-model relabeling."""

import json
from pathlib import Path

import pytest

from bakeoff import dataset as ds
from bakeoff import relabel
from bakeoff.providers import claude_request
from bakeoff.questions import QUESTIONS

from .conftest import json_response, mock

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def frozen():
    rows, _ = ds.load_frozen()
    return rows


def test_b1_blind_set_is_the_edited_messages_plus_30_controls_every_time(frozen):
    edits = relabel.edited_labels()
    a, b = relabel.blind_set(frozen, edits), relabel.blind_set(frozen, edits)
    edited_ids = {mid for mid, _ in edits}
    assert a == b
    assert len(a) == len(edited_ids) + 30 == 72
    assert edited_ids <= {i["message_id"] for i in a}
    assert [i["blind_id"] for i in a] == [f"b{n:02d}" for n in range(1, 73)]


def test_b1_the_rater_is_sent_no_label_and_nothing_that_marks_an_edit(frozen):
    edits = relabel.edited_labels()
    item = next(i for i in relabel.blind_set(frozen, edits) if i["message_id"] in {m for m, _ in edits})
    sent = json.dumps(relabel.rater_request(item["text"]))
    truth = next(m for m in frozen if m["id"] == item["message_id"])["truth"]
    assert item["message_id"] not in sent and item["blind_id"] not in sent
    # The labels appear only as allowed choices, never as an answer: the user turn is the message alone.
    body = relabel.rater_request(item["text"])
    assert body["messages"][1] == {"role": "user", "content": item["text"]}
    assert all(t not in body["messages"][1]["content"] for t in ("truth", "frozen", "generated"))


def test_b1_question_and_label_wording_match_the_variants_word_for_word():
    body = relabel.rater_request("x")
    variant = claude_request("x", list(QUESTIONS))
    assert body["messages"] == variant["messages"] and body["response_format"] == variant["response_format"]
    assert body["max_tokens"] == 4096  # room to reason; the wording above is what must match


def test_b2_pinned_to_the_one_vertex_endpoint_with_no_fallback():
    body = relabel.rater_request("x")
    assert body["provider"] == {"only": ["google-vertex/global"], "allow_fallbacks": False}
    assert body["model"] == "google/gemini-3.1-pro-preview" and body["reasoning"] == {"effort": "low"}


def test_b2_the_rater_vendor_makes_no_variant():
    models = {"jev": "typesafe/jev-1.13", "sonnet": "anthropic/claude-sonnet-5.5", "dec": "openai/gpt-6-luna-decisions"}
    relabel.check_independent({"rater_vendor": "google"}, models)
    with pytest.raises(ValueError):
        relabel.check_independent({"rater_vendor": "anthropic"}, models)


def _answer(labels):
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(labels)}}],
            "model": "google/gemini-3.1-pro-preview", "provider": "Google", "usage": {"prompt_tokens": 600, "completion_tokens": 40, "cost": 0.002}}


def test_b2_an_unanswered_message_is_left_out_and_counted(tmp_path):
    from bakeoff.providers import _OpenRouter

    good = {"intent": "buy", "timeline": "unknown", "wants_contact": "yes", "urgency": "normal"}
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return json_response({"error": "boom"}, status=503) if calls["n"] <= 3 else json_response(_answer(good))

    record = relabel.run([{"blind_id": "b01", "message_id": "m001", "text": "a"}, {"blind_id": "b02", "message_id": "m002", "text": "b"}],
                         client=_OpenRouter(inner=mock(handler)), results_dir=tmp_path, sleep=lambda s: None)
    assert record["failed"] == ["m001"] and set(record["labels"]) == {"m002"}
    assert record["cost_usd"] == 0.002 and record["served_by"] == ["Google"]


def _rows(n=4):
    return [{"id": f"m{i:03d}", "text": "t", "truth": {"intent": ["buy"], "timeline": ["unknown"], "wants_contact": ["yes"], "urgency": ["normal"]}} for i in range(1, n + 1)]


def test_b3_frozen_generated_and_neither_each_count_and_baseline_is_per_question():
    rows = _rows(4)
    rows[3]["truth"]["intent"] = ["buy", "sell"]
    edits = {("m001", "urgency"): (["high"], ["normal"]), ("m002", "urgency"): (["high"], ["normal"]), ("m003", "urgency"): (["high"], ["normal"])}
    base = {"intent": "buy", "timeline": "unknown", "wants_contact": "yes"}
    record = {"labels": {
        "m001": {**base, "urgency": "normal"},   # frozen
        "m002": {**base, "urgency": "high"},     # generated
        "m003": {**base, "urgency": None},       # neither (invalid)
        "m004": {**base, "intent": "sell", "urgency": "high"},  # control: two-intent match, urgency miss
    }}
    a = relabel.agreement(record, rows, edits)
    assert a["urgency"] == {"edited": 3, "frozen": 1, "generated": 1, "neither": 1, "control": 1, "control_agree": 0}
    assert a["intent"]["control_agree"] == 1  # either intent of a two-intent message agrees


def test_b4_only_edited_labels_change(frozen):
    edits = relabel.edited_labels()
    some = next(iter(edits))
    other_q = next(q.name for q in QUESTIONS if (some[0], q.name) not in edits)
    record = {"labels": {some[0]: {q.name: ("rater-" + q.name) for q in QUESTIONS}}}
    out = relabel.with_rater_on_edits(frozen, record, edits)
    before = {m["id"]: m for m in frozen}[some[0]]["truth"]
    after = {m["id"]: m for m in out}[some[0]]["truth"]
    assert after[some[1]] == ["rater-" + some[1]]
    assert after[other_q] == before[other_q]
    assert [m for m in out if m["id"] != some[0]] == [m for m in frozen if m["id"] != some[0]]


def test_b5_report_says_no_check_yet_when_none_is_on_record():
    from bakeoff.report import render

    meta = {"run_id": "r", "started_at": "2026-10-07T00:00:00Z", "dataset_version": "d", "cap_usd": 2.0, "prices": {}, "models": {}}
    assert "No independent check of the edited labels has been made yet." in render(meta, [], public=True, withheld=[])


def test_b6_the_record_carries_what_a_rerun_needs(tmp_path):
    from bakeoff.providers import _OpenRouter

    good = {"intent": "buy", "timeline": "unknown", "wants_contact": "yes", "urgency": "normal"}
    record = relabel.run([{"blind_id": "b01", "message_id": "m001", "text": "a"}], client=_OpenRouter(inner=mock(lambda r: json_response(_answer(good)))),
                         results_dir=tmp_path, sleep=lambda s: None)
    for key in ("rater_model", "endpoint_requested", "settings", "request_shape", "blind_set", "date"):
        assert record[key], key
    assert record["blind_set"]["seed"] == relabel.SEED


def test_a_truncated_answer_is_retried_and_a_fenced_answer_is_read(tmp_path):
    from bakeoff.providers import _OpenRouter

    good = {"intent": "buy", "timeline": "unknown", "wants_contact": "yes", "urgency": "normal"}
    cut = {"choices": [{"finish_reason": "length", "message": {"content": "Here is the JSON requested:\n```"}}], "usage": {"cost": 0.001}}
    fenced = _answer(good)
    fenced["choices"][0]["message"]["content"] = "Here is the JSON requested:\n```json\n" + json.dumps(good) + "\n```"
    replies = iter([cut, fenced])
    record = relabel.run([{"blind_id": "b01", "message_id": "m001", "text": "a"}],
                         client=_OpenRouter(inner=mock(lambda r: json_response(next(replies)))), results_dir=tmp_path, sleep=lambda s: None)
    assert record["labels"]["m001"] == good and record["failed"] == []


def test_spec005_b1_the_drafting_request_holds_no_current_definition_label_log_or_message(frozen):
    from bakeoff import definitions
    from bakeoff.questions import QUESTIONS

    sent = json.dumps(definitions.drafting_request())
    for q in QUESTIONS:
        assert q.name in sent and all(json.dumps(l)[1:-1] in sent for l in q.labels)
        assert q.text not in sent  # no current definition text
    assert "label-changes" not in sent and "m001" not in sent
    assert not any(m["text"][:60] in sent for m in frozen)  # no dataset message


def test_spec005_an_unapproved_definition_set_cannot_be_loaded(tmp_path, monkeypatch):
    from bakeoff import questions

    monkeypatch.setattr(questions, "DEFINITIONS_DIR", tmp_path)
    (tmp_path / "x.json").write_text(json.dumps({"approved": False, "original": {q.name: "t" for q in questions.QUESTIONS}}))
    with pytest.raises(ValueError):
        questions.load_set("x")
    (tmp_path / "x.json").write_text(json.dumps({"approved": True, "original": {q.name: "t" for q in questions.QUESTIONS}, "final": None}))
    loaded = questions.load_set("x")
    assert [q.labels for q in loaded] == [q.labels for q in questions.QUESTIONS] and all(q.text == "t" for q in loaded)
    assert questions.questions_version(loaded) != questions.questions_version()


def test_spec005_b2_outside_labels_allow_two_intents_and_one_label_elsewhere():
    from bakeoff.questions import QUESTIONS
    good = {"intent": ["buy", "sell"], "timeline": "unknown", "wants_contact": "yes", "urgency": "normal"}
    body = {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(good)}}]}
    assert relabel._parse_outside(body, QUESTIONS) == {"intent": ["buy", "sell"], "timeline": ["unknown"], "wants_contact": ["yes"], "urgency": ["normal"]}
    bad = dict(good, urgency="maybe")
    assert relabel._parse_outside({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(bad)}}]}, QUESTIONS) is None
    req = relabel.outside_request("x", QUESTIONS)
    assert req["response_format"]["json_schema"]["schema"]["properties"]["intent"]["maxItems"] == 2
    assert req["messages"][1] == {"role": "user", "content": "x"}


def test_spec005_b2_the_frozen_dataset_is_unchanged_by_outside_labels(frozen):
    before = json.dumps(frozen, sort_keys=True)
    record = {"labels": {frozen[0]["id"]: {"intent": ["sell"], "timeline": ["unknown"], "wants_contact": ["yes"], "urgency": ["normal"]}}}
    out = relabel.outside_dataset(frozen, record)
    assert json.dumps(frozen, sort_keys=True) == before and len(out) == 1 and out[0]["truth"]["intent"] == ["sell"]
    assert ds.load_frozen()[1] == "sha256:8c43a059d800a559"
