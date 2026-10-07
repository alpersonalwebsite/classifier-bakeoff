"""Spec 002: written conclusions, the figure check, and the dataset note."""

import json

import pytest

from bakeoff import __main__ as cli
from bakeoff import conclusions
from bakeoff.report import render

from .test_runner_and_report import PRICE, _meta, _run, chat_body, json_response, make_dataset, ALL_RIGHT
from bakeoff.scoring import score_run

GEN = {"version": "sha256:test", "size": 200, "generator": "anthropic/claude-opus-5.5"}


def _report_inputs(tmp_path):
    data = make_dataset(4)
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:  # one timeout makes this variant's cost a lower bound
            import httpx2

            raise httpx2.ReadTimeout("t", request=request)
        return json_response(chat_body(ALL_RIGHT))

    outcome, records = _run(tmp_path, handler, data)
    meta = _meta({"haiku-batched": outcome}, {"haiku-batched": PRICE})
    meta["models"] = {"haiku-batched": "anthropic/claude-haiku-4.5"}
    scores = score_run(meta, records, data)
    return meta, scores


def _public(meta, scores, body=None):
    return render(meta, scores, public=True, withheld=[], dataset_meta=GEN, conclusions_html=body)


def test_b2_conclusions_shown_in_both_editions_naming_the_run(tmp_path):
    meta, scores = _report_inputs(tmp_path)
    body = conclusions.to_html("Haiku is fine for intent.")
    for public in (True, False):
        page = render(meta, scores, public=public, withheld=[], dataset_meta=GEN, conclusions_html=body)
        assert "<h2>Conclusions</h2>" in page and "Written analysis" in page and meta["run_id"] in page


def test_b2_no_conclusions_means_no_heading(tmp_path):
    meta, scores = _report_inputs(tmp_path)
    assert "<h2>Conclusions</h2>" not in _public(meta, scores)


def test_b1_conclusions_load_only_for_their_own_run(tmp_path):
    (tmp_path / "run-a.md").write_text("For run A.")
    assert conclusions.load("run-a", tmp_path) == "For run A."
    assert conclusions.load("run-b", tmp_path) is None


def test_b3_a_printed_figure_passes(tmp_path):
    meta, scores = _report_inputs(tmp_path)
    page = _public(meta, scores)
    assert "100.0%" in conclusions.page_text(page)
    assert conclusions.check("Intent accuracy was 100.0% here.", page) == []


def test_b3_an_unprinted_figure_fails_and_is_named(tmp_path):
    meta, scores = _report_inputs(tmp_path)
    problems = conclusions.check("Intent accuracy was 93.0%.", _public(meta, scores))
    assert problems and "93.0%" in problems[0]


def test_b3_a_figure_cannot_match_itself_in_the_conclusions(tmp_path):
    meta, scores = _report_inputs(tmp_path)
    text = "It reached 93.0%."
    with_itself = _public(meta, scores, conclusions.to_html(text))
    assert "93.0%" in conclusions.page_text(with_itself)  # would self-match if checked here
    assert conclusions.check(text, _public(meta, scores))  # the spec checks the page without them


def test_b3_figures_must_be_quoted_exactly_as_printed(tmp_path):
    meta, scores = _report_inputs(tmp_path)
    page = conclusions.page_text(_public(meta, scores))
    lo = page.split("(", 1)[1].split(" to ", 1)[0]  # first interval's low end, printed bare
    assert conclusions.check(f"The interval starts at {lo}%.", _public(meta, scores))


def test_b3_lower_bound_must_keep_its_marker(tmp_path):
    meta, scores = _report_inputs(tmp_path)
    page = _public(meta, scores)
    cost = next(s for s in scores).cost_per_message
    fig = f"${cost:.6f}"
    assert f"≥ {fig}" in conclusions.page_text(page)
    assert conclusions.check(f"It costs {fig} per message.", page)
    assert conclusions.check(f"It costs at least {fig} per message.", page) == []
    assert conclusions.check(f"It costs ≥ {fig} per message.", page) == []


def test_b3_dates_and_counts_are_not_figures():
    assert conclusions.figures("Run on 2026-10-07 over 200 messages and six variants.") == []


def test_b3_a_failing_check_writes_no_edition(tmp_path, monkeypatch):
    meta, scores = _report_inputs(tmp_path)
    monkeypatch.setattr(cli, "load_run", lambda d: (meta, []))
    monkeypatch.setattr(cli.ds, "load_frozen", lambda: (make_dataset(4), meta["dataset_version"]))
    monkeypatch.setattr(cli, "score_run", lambda m, r, d: scores)
    meta_file = tmp_path / "dataset.meta.json"
    meta_file.write_text(json.dumps(GEN))
    monkeypatch.setattr(cli.ds, "META_FILE", meta_file)
    monkeypatch.setattr(cli.ds, "LABEL_CHANGES_FILE", tmp_path / "no-label-log.md")
    monkeypatch.setattr(cli.relabel, "RELABEL_FILE", tmp_path / "no-relabel.json")
    monkeypatch.setattr(cli.definitions, "SET_FILE", tmp_path / "no-definitions.json")
    monkeypatch.setattr(cli, "FULL_DIR", tmp_path / "full")
    monkeypatch.setattr(cli, "PUBLIC_DIR", tmp_path / "public")
    (tmp_path / "concl").mkdir()
    (tmp_path / "concl" / f"{meta['run_id']}.md").write_text("Accuracy was 93.0%.")
    monkeypatch.setattr(conclusions, "CONCLUSIONS_DIR", tmp_path / "concl")
    with pytest.raises(conclusions.ConclusionsError, match="93.0%"):
        cli.write_reports(tmp_path)
    assert not (tmp_path / "full").exists() and not (tmp_path / "public").exists()


def test_b4_html_in_conclusions_is_shown_as_text():
    out = conclusions.to_html("Beware <script>alert(1)</script> and **bold** and *italic*.\n\n- one\n- two")
    assert "<script>" not in out and "&lt;script&gt;" in out
    assert "<strong>bold</strong>" in out and "<em>italic</em>" in out and "<li>two</li>" in out


def test_b5_report_states_synthetic_data_and_shared_vendor(tmp_path):
    meta, scores = _report_inputs(tmp_path)
    page = conclusions.page_text(_public(meta, scores))
    assert "synthetic" in page and "anthropic/claude-opus-5.5" in page
    assert "also makes variants in this run (haiku-batched)" in page


def test_b3_a_figure_must_match_a_whole_printed_figure_not_part_of_one(tmp_path):
    meta, scores = _report_inputs(tmp_path)
    page = _public(meta, scores)
    shown = conclusions.page_text(page)
    printed = {fig for fig, _ in conclusions.figures(shown)}
    # "00.0%" is the tail of the printed "100.0%" but is never printed on its own.
    assert "100.0%" in printed and "00.0%" not in printed and "00.0%" in shown
    assert conclusions.check("Intent was 00.0%.", page)
    cost = f"{scores[0].cost_per_message:.6f}"
    assert conclusions.check(f"It costs at least ${cost[:-1]}.", page)  # a truncated dollar figure


def test_reviewers_cases_against_the_published_report():
    """The three cases from the PR #5 review, on the real committed report."""
    from pathlib import Path

    pub = (Path(__file__).resolve().parent.parent / "reports/public/20261007T194642Z-ba611a.html").read_text()
    start = pub.index("<h2>Conclusions</h2>")
    without = pub[:start] + pub[pub.index("<h2>", start + 5):]
    for wrong in ("Jev trails by 4.0% on intent.", "Haiku reaches 5.5% on intent.", "Decisions costs $0.00006 per message."):
        assert conclusions.check(wrong, without), wrong
    assert conclusions.check("Decisions is 94.0% on intent at $0.000062.", without) == []


def test_b4_numbered_lists_render_as_ordered_lists():
    out = conclusions.to_html("1. first <b>\n2. second")
    assert out == "<ol><li>first &lt;b&gt;</li><li>second</li></ol>"
