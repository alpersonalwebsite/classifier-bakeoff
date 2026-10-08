"""Spec 007: blind human labeling for anyone who clones the repository."""

import json
import re

import pytest

from bakeoff import dataset as ds
from bakeoff import labeling, relabel
from bakeoff.questions import QUESTIONS


@pytest.fixture(scope="module")
def frozen():
    return ds.load_frozen()[0]


def _data(page):
    return json.loads(page.split("const DATA = ", 1)[1].split(";\n", 1)[0])


def test_b1_edits_set_is_spec_004s_72_in_a_new_order(frozen):
    mine = labeling.blind_set(frozen, "edits")
    rater = relabel.blind_set(frozen, relabel.edited_labels())
    assert sorted(i["message_id"] for i in mine) == sorted(i["message_id"] for i in rater)
    assert [i["message_id"] for i in mine] != [i["message_id"] for i in rater]


def test_b1_unseen_set_is_60_unexcluded_and_stable(frozen):
    a, b = labeling.blind_set(frozen, "unseen"), labeling.blind_set(frozen, "unseen")
    assert a == b and len(a) == 60
    skip = labeling.excluded()
    assert len(skip) == 93 and not {i["message_id"] for i in a} & skip


@pytest.mark.parametrize("set_name", labeling.SETS)
def test_b2_page_has_no_id_definition_or_answer(frozen, set_name):
    page = labeling.first_page(labeling.blind_set(frozen, set_name), set_name)
    assert not re.search(r"\bm\d{3}\b", page)
    for q in QUESTIONS:
        assert q.text not in page and labeling.PLAIN[q.name] in page
    data = _data(page)
    assert all(set(i) == {"id", "text"} for i in data["items"])
    assert {f["name"]: f["max"] for f in data["fieldList"]} == {"intent": 2, "timeline": 1, "wants_contact": 1, "urgency": 1}


def test_b3_no_network_code_and_progress_saved(frozen):
    page = labeling.first_page(labeling.blind_set(frozen, "edits"), "edits")
    for banned in ("fetch(", "XMLHttpRequest", "http://", "https://", "<link", "src="):
        assert banned not in page, banned
    assert "localStorage.setItem" in page


def test_b4_page_asks_what_was_read_and_import_requires_it(frozen):
    page = labeling.first_page(labeling.blind_set(frozen, "edits"), "edits")
    assert _data(page)["askExposure"] is True and list(_data(page)["exposureOptions"]) == ["none", "report", "specs-or-code", "review"]
    assert "pick the furthest you have gone" in page
    items = labeling.blind_set(frozen, "unseen")
    good = {"intent": ["buy"], "timeline": ["unknown"], "wants_contact": ["yes"], "urgency": ["normal"]}
    saved = {"set": "unseen", "exposure": "none", "answers": {i["blind_id"]: good for i in items}}
    rec = labeling.import_first(frozen, saved, "fresh-reader")
    assert rec["exposure"] == "none" and rec["set"] == "unseen" and len(rec["labels"]) == 60
    with pytest.raises(ValueError):
        labeling.import_first(frozen, dict(saved, exposure=None), "x")
    with pytest.raises(ValueError):
        labeling.import_first(frozen, {**saved, "answers": {**saved["answers"], items[0]["blind_id"]: dict(good, urgency=["high", "normal"])}}, "x")


def test_b4_names_are_kept_apart_and_validated(tmp_path, monkeypatch):
    monkeypatch.setattr(labeling, "HUMAN_DIR", tmp_path)
    assert labeling.record_path("ann") != labeling.record_path("bob")
    for bad in ("", "Ann", "../x", "a b"):
        with pytest.raises(ValueError):
            labeling.record_path(bad)


def test_b5_edits_agreement_counts_frozen_generated_neither(frozen):
    edits = relabel.edited_labels()
    (mid, q), (old, new) = next((k, v) for k, v in edits.items() if k[1] == "urgency")
    row = {qq.name: next(m for m in frozen if m["id"] == mid)["truth"][qq.name] for qq in QUESTIONS}
    rec = {"set": "edits", "labels": {mid: {**row, q: list(old)}}}
    a = labeling.edits_agreement(rec, frozen, edits)
    assert a["urgency"]["generated"] == 1 and a["urgency"]["frozen"] == 0


def test_b6_second_look_shows_definition_and_counts(frozen):
    items = labeling.blind_set(frozen, "unseen")[:1]
    truth = {m["id"]: m["truth"] for m in frozen}[items[0]["message_id"]]
    wrong = "normal" if truth["urgency"] == ["high"] else "high"
    rows = labeling.disagreements(items, {items[0]["blind_id"]: {**{q.name: truth[q.name][:1] for q in QUESTIONS}, "urgency": [wrong]}}, frozen)
    assert [r["question"] for r in rows] == ["urgency"]
    assert next(q.text for q in QUESTIONS if q.name == "urgency") in labeling.second_page(rows)
    assert labeling.second_look_counts({"answers": {rows[0]["id"]: {"decision": ["keep frozen"]}}})["urgency"]["keep frozen"] == 1


def test_b7_edits_set_replaces_only_edited_labels(frozen):
    edits = relabel.edited_labels()
    mid, q = next(iter(edits))
    other = next(qq.name for qq in QUESTIONS if (mid, qq.name) not in edits)
    rec = {"set": "edits", "labels": {mid: {qq.name: ["x-" + qq.name] for qq in QUESTIONS}}}
    out = {m["id"]: m for m in labeling.with_labels(frozen, rec, edits)}
    before = {m["id"]: m for m in frozen}
    assert out[mid]["truth"][q] == ["x-" + q] and out[mid]["truth"][other] == before[mid]["truth"][other]


def test_b8_report_points_to_the_readme_when_none_is_on_record():
    from bakeoff.report import render

    meta = {"run_id": "r", "started_at": "2026-10-08T00:00:00Z", "dataset_version": "d", "cap_usd": 2.0, "prices": {}, "models": {}}
    page = render(meta, [], public=True, withheld=[])
    assert "No human blind labeling is on record" in page and "Check the labels yourself" in page


def test_b8_labelings_with_different_declarations_are_grouped_apart():
    from bakeoff.report import render

    meta = {"run_id": "r", "started_at": "2026-10-08T00:00:00Z", "dataset_version": "d", "cap_usd": 2.0, "prices": {}, "models": {}}
    agree = {q.name: 1 for q in QUESTIONS}
    human = [
        {"record": {"labeler": "fresh", "set": "unseen", "exposure": "none", "imported_at": "2026-10-08"}, "agree": agree, "n": 2, "ranked": [], "second": None},
        {"record": {"labeler": "reader", "set": "unseen", "exposure": "report", "imported_at": "2026-10-08"}, "agree": agree, "n": 2, "ranked": [], "second": None},
    ]
    page = render(meta, [], public=True, withheld=[], human=human)
    a, b = page.index("Had read: nothing about this project"), page.index("Had read: the published report")
    assert a < page.index("<b>fresh</b>") < b < page.index("<b>reader</b>")
