"""Runner, scoring and both report editions, driven through the real Claude SDK
with hand-written HTTP responses (see conftest)."""

import json
import subprocess
from pathlib import Path

import httpx2

from bakeoff.providers import ClaudeProvider
from bakeoff.report import render
from bakeoff.runner import _Writer, run_variant
from bakeoff.scoring import score_run
from bakeoff.variants import BY_NAME, load_prices

from .conftest import ALL_RIGHT, FAKE_KEY, chat_body, json_response, make_dataset, mock

ROOT = Path(__file__).resolve().parent.parent
HAIKU = BY_NAME["haiku-batched"]
PRICE = load_prices()["anthropic/claude-haiku-4.5"]


def _run(tmp_path, handler, dataset, price=PRICE, cap=2.0, name="haiku-batched"):
    writer = _Writer(tmp_path / "calls.jsonl")
    provider = ClaudeProvider("anthropic/claude-haiku-4.5", inner=mock(handler))
    outcome = run_variant(BY_NAME[name], dataset, writer, "test", price, cap, provider=provider, sleep=lambda s: None)
    writer.close()
    records = [json.loads(l) for l in (tmp_path / "calls.jsonl").read_text().splitlines()]
    return outcome, records


def _meta(outcomes: dict, prices: dict) -> dict:
    return {
        "run_id": "test",
        "started_at": "2026-10-07T00:00:00Z",
        "dataset_version": "sha256:test",
        "cap_usd": 2.0,
        "prices": prices,
        "variants": {name: o.__dict__ for name, o in outcomes.items()},
    }


def test_b5_timeout_then_success_keeps_both_attempts(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx2.ReadTimeout("simulated timeout", request=request)
        return json_response(chat_body(ALL_RIGHT))

    outcome, records = _run(tmp_path, handler, make_dataset(1))
    assert [r["attempt"] for r in records] == [1, 2]
    assert records[0]["outcome"] == "failed" and records[0]["usage"] is None
    assert records[1]["outcome"] == "completed" and records[1]["usage"]["prompt_tokens"] == 120
    assert outcome.unknown_token_calls == 1 and outcome.status == "complete"


def test_b6_invalid_label_is_wrong_but_classified(tmp_path):
    bad = {**ALL_RIGHT, "intent": "teleport"}
    data = make_dataset(2)
    outcome, records = _run(tmp_path, lambda r: json_response(chat_body(bad)), data)
    [s] = score_run(_meta({"haiku-batched": outcome}, {"haiku-batched": PRICE}), records, data)
    assert s.classified == 2 and s.accuracy("intent") == 0 and s.invalid_rate() > 0


def test_b8_low_cap_stops_and_reports_partial(tmp_path):
    data = make_dataset(20)
    outcome, records = _run(tmp_path, lambda r: json_response(chat_body(ALL_RIGHT)), data, cap=0.002)
    assert outcome.status == "partial" and "spend cap" in outcome.reason
    assert outcome.spend_projected_usd <= 0.002
    assert len(records) < 20


def test_b8_unknown_price_uses_call_cap_that_cannot_cut_a_full_run(tmp_path):
    data = make_dataset(5)
    outcome, records = _run(tmp_path, lambda r: json_response(chat_body(ALL_RIGHT, cost=None)), data, price=None)
    assert outcome.status == "complete" and len(records) == 5


def test_b9_invalid_key_is_not_run(tmp_path):
    body = {"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}
    outcome, records = _run(tmp_path, lambda r: json_response(body, status=401), make_dataset(3))
    assert outcome.status == "not run" and "401" in outcome.reason
    assert len(records) == 1


def test_b9_server_errors_retry_then_stop_after_five_failed_messages(tmp_path):
    outcome, records = _run(tmp_path, lambda r: json_response({"error": "boom"}, status=503), make_dataset(8))
    assert [r["attempt"] for r in records[:3]] == [1, 2, 3]
    assert len(records) == 15  # five messages, three attempts each, then stop
    # It reached the provider, so it is partial, not "not run" (B9).
    assert outcome.status == "partial" and "5 messages in a row" in outcome.reason


def test_b9_a_400_on_the_first_message_does_not_end_the_variant(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return json_response({"error": {"message": "bad request"}}, status=400)
        return json_response(chat_body(ALL_RIGHT))

    outcome, records = _run(tmp_path, handler, make_dataset(4))
    assert outcome.status == "complete" and len(records) == 4  # 400 is not retried, run continues


def test_402_out_of_credits_stops_the_variant_midway(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] > 2:
            return json_response({"error": {"message": "Insufficient credits"}}, status=402)
        return json_response(chat_body(ALL_RIGHT))

    outcome, records = _run(tmp_path, handler, make_dataset(10))
    assert outcome.status == "partial" and "out of credits" in outcome.reason and len(records) == 3


def test_malformed_200_is_retried_not_scored(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return json_response({"id": "x"}) if calls["n"] == 1 else json_response(chat_body(ALL_RIGHT))

    outcome, records = _run(tmp_path, handler, make_dataset(1))
    assert [r["outcome"] for r in records] == ["failed", "completed"]
    assert "MalformedResponse" in records[0]["error"]


def test_b7_latency_includes_retry_backoff(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx2.ReadTimeout("t", request=request)
        return json_response(chat_body(ALL_RIGHT))

    data = make_dataset(1)
    outcome, records = _run(tmp_path, handler, data)
    assert records[1]["waited_before_s"] == 1.0
    [s] = score_run(_meta({"haiku-batched": outcome}, {"haiku-batched": PRICE}), records, data)
    assert s.latency_p50 >= 1.0


def test_a_crashing_variant_still_yields_a_run_summary(tmp_path, monkeypatch):
    from bakeoff import runner

    def boom(*a, **k):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(runner, "run_variant", boom)
    run_dir = runner.run([HAIKU], make_dataset(1), "sha256:test", {}, results_dir=tmp_path)
    meta = json.loads((run_dir / "run.json").read_text())
    assert meta["variants"]["haiku-batched"]["status"] == "partial"
    assert "crashed" in meta["variants"]["haiku-batched"]["reason"]


def test_public_edition_omits_vendor_error_text(tmp_path):
    secret_text = "upstream says: internal routing id 7f3a"
    outcome, records = _run(tmp_path, lambda r: json_response({"error": {"message": secret_text}}, status=503), make_dataset(6))
    meta = _meta({"haiku-batched": outcome}, {"haiku-batched": PRICE})
    scores = score_run(meta, records, make_dataset(6))
    assert secret_text not in render(meta, scores, public=True, withheld=[])
    assert secret_text in render(meta, scores, public=False, withheld=[])


def test_withheld_list_refuses_figures_it_cannot_remove(tmp_path):
    from bakeoff.report import load_withheld

    f = tmp_path / "withheld.json"
    f.write_text(json.dumps([{"variant": "jev", "figure": "latency", "reason": "x"}]))
    try:
        load_withheld(f)
    except ValueError:
        return
    raise AssertionError("an unremovable figure was accepted")


def _report_fixture(tmp_path):
    data = make_dataset(4)
    good = lambda r: json_response(chat_body(ALL_RIGHT))
    jev_good = lambda r: json_response(chat_body(ALL_RIGHT, cost=0.0000061))
    (tmp_path / "a").mkdir(); (tmp_path / "b").mkdir()
    o_h, rec_h = _run(tmp_path / "a", good, data)
    jev_price = {"input": 0.05, "output": 0.0}
    o_j, rec_j = _run(tmp_path / "b", jev_good, data, price=jev_price, name="jev")  # stands in for Jev's records
    for r in rec_j:
        r["variant"] = "jev"
    meta = _meta({"haiku-batched": o_h, "jev": o_j}, {"haiku-batched": PRICE, "jev": jev_price})
    scores = score_run(meta, rec_h + rec_j, data)
    withheld = [{"variant": "jev", "figure": "cost", "reason": "confidential pricing"}]
    return meta, scores, withheld


def _section(page: str, title: str) -> str:
    start = page.index(f"<h2>{title}</h2>")
    nxt = page.find("<h2>", start + 4)
    return page[start : nxt if nxt != -1 else None]


def test_b11_public_withholds_jev_cost_full_keeps_it(tmp_path):
    meta, scores, withheld = _report_fixture(tmp_path)
    full = render(meta, scores, public=False, withheld=withheld)
    public = render(meta, scores, public=True, withheld=withheld)
    jev_cost = f"${[s for s in scores if s.name == 'jev'][0].cost_per_message:.6f}"
    assert jev_cost in full
    assert jev_cost not in public
    assert "0.05" not in public  # Jev's rate is not in the prices table either
    withheld_section = _section(public, "Withheld")
    assert "jev" in withheld_section and "confidential pricing" in withheld_section


def test_b11_public_cost_ranking_excludes_jev_entirely(tmp_path):
    meta, scores, withheld = _report_fixture(tmp_path)
    ranking = _section(render(meta, scores, public=True, withheld=withheld), "Cost ranking")
    table = ranking[ranking.index("<table>") :]
    assert "jev" not in table  # no row, not even a blanked one
    assert "Excludes: jev (cost withheld)" in ranking


def test_b7_lower_bound_cost_is_labeled(tmp_path):
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx2.ReadTimeout("t", request=request)
        return json_response(chat_body(ALL_RIGHT))

    data = make_dataset(2)
    outcome, records = _run(tmp_path, handler, data)
    scores = score_run(_meta({"haiku-batched": outcome}, {"haiku-batched": PRICE}), records, data)
    page = render(_meta({"haiku-batched": outcome}, {"haiku-batched": PRICE}), scores, public=False, withheld=[])
    assert scores[0].cost_is_lower_bound and scores[0].unknown_token_calls == 1
    assert "lower bound" in _section(page, "Head-to-head")
    assert "<td>1</td><td>1</td>" in _section(page, "Tokens per classified message")  # unknown tokens, unknown cost
    assert "cheapest variant is unconfirmed" in page


def test_b9_partial_coverage_shown_and_out_of_head_to_head(tmp_path):
    data = make_dataset(4)
    outcome, records = _run(tmp_path, lambda r: json_response(chat_body(ALL_RIGHT)), data[:3])
    meta = _meta({"haiku-batched": outcome}, {"haiku-batched": PRICE})
    scores = score_run(meta, records, data)
    page = render(meta, scores, public=True, withheld=[])
    assert scores[0].status == "partial" and scores[0].coverage == 0.75
    assert "haiku-batched" not in _section(page, "Head-to-head")
    assert "75.0%" in _section(page, "Partial and not-run variants")


def test_b5_no_key_anywhere_in_records_or_reports(tmp_path):
    meta, scores, withheld = _report_fixture(tmp_path)
    blobs = [(tmp_path / "a" / "calls.jsonl").read_text(), render(meta, scores, False, withheld), render(meta, scores, True, withheld)]
    for blob in blobs:
        assert FAKE_KEY not in blob


def test_b11_full_reports_and_results_are_git_ignored():
    for path in ("results/any/calls.jsonl", "results/any/run.json", "reports/full/any.html", "prices.local.json"):
        assert subprocess.run(["git", "check-ignore", "-q", path], cwd=ROOT).returncode == 0, path
    assert subprocess.run(["git", "check-ignore", "-q", "reports/public/any.html"], cwd=ROOT).returncode == 1


def test_reported_cost_beats_the_price_list(tmp_path):
    outcome, records = _run(tmp_path, lambda r: json_response(chat_body(ALL_RIGHT, cost=0.5)), make_dataset(1), cap=10.0)
    assert records[0]["cost_usd"] == 0.5  # the price list would give 0.00022


def test_b8_no_price_still_gets_a_dollar_cap_once_costs_are_reported(tmp_path):
    outcome, records = _run(tmp_path, lambda r: json_response(chat_body(ALL_RIGHT, cost=0.3)), make_dataset(20), price=None, cap=1.0)
    assert outcome.status == "partial" and "spend cap" in outcome.reason
    assert outcome.spend_known_usd <= 1.0 and len(records) == 3
