"""Spec 006: intent states the rule the dataset was generated under."""

import json

from bakeoff import dataset as ds
from bakeoff import report
from bakeoff.questions import BY_NAME, questions_version
from bakeoff.report import render

META = {"run_id": "old-run", "started_at": "2026-10-07T00:00:00Z", "dataset_version": "d", "cap_usd": 2.0, "prices": {}, "models": {}}


def test_b1_intent_states_the_generators_rule():
    text = BY_NAME["intent"].text
    assert "anything that is not a real estate inquiry" in text
    assert "such as spam, a vendor pitch, or a wrong number" in text
    assert "neither is clearly the main one, either one is correct" in text
    assert "not a lead such as spam, a vendor pitch, or a wrong number" in (ds.GENERATOR_PROMPT)


def test_b1_messages_labeled_not_a_lead_include_ones_outside_the_examples():
    rows = {m["id"]: m for m in ds.load_frozen()[0]}
    for mid in ("m176", "m197"):
        assert rows[mid]["truth"]["intent"] == ["not a lead"]  # covered by "anything that is not a real estate inquiry"


def test_b2_frozen_dataset_unchanged():
    assert ds.load_frozen()[1] == "sha256:8c43a059d800a559"


def test_b3_question_version_moved():
    assert questions_version() != "sha256:2db74e1065302281"


def test_b5_report_names_where_the_definitions_come_from():
    assert "Claude-assisted drafting" in render(META, [], public=True, withheld=[])
