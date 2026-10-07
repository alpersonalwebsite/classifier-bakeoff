"""Render the full and public report editions (spec 001 B10, B11)."""

import html
import json
from pathlib import Path

from .questions import QUESTIONS
from .scoring import VariantScore

ROOT = Path(__file__).resolve().parent.parent
WITHHELD_FILE = ROOT / "withheld.json"


# The only figure the public edition knows how to remove. Listing any other figure would
# print it under Withheld while still showing it, so that is refused rather than trusted.
WITHHOLDABLE = {"cost"}


def load_withheld(path: Path = WITHHELD_FILE) -> list[dict]:
    entries = json.loads(path.read_text()) if path.exists() else []
    unknown = sorted({w.get("figure") for w in entries} - WITHHOLDABLE)
    if unknown:
        raise ValueError(f"withheld.json lists figures the public edition cannot remove: {unknown}")
    return entries


def _e(x: object) -> str:
    return html.escape(str(x))


def _pct(x: float) -> str:
    return f"{100 * x:.1f}%"


def _ci(lo_hi: tuple[float, float]) -> str:
    return f"{100 * lo_hi[0]:.1f} to {100 * lo_hi[1]:.1f}"


def _usd(x: float | None, lower_bound: bool = False) -> str:
    if x is None:
        return "unknown"
    return ("≥ " if lower_bound else "") + f"${x:.6f}"


def _secs(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.2f} s"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    head = "".join(f"<th>{_e(h)}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


CSS = """
:root { --bg:#fff; --fg:#1d1d1f; --muted:#6b6b70; --line:#e2e2e6; --head:#f5f5f7; --warn:#9a5b00; }
@media (prefers-color-scheme: dark) { :root { --bg:#151517; --fg:#ececee; --muted:#a0a0a8; --line:#33333a; --head:#1f1f23; --warn:#f0b35a; } }
body { background:var(--bg); color:var(--fg); font:15px/1.5 -apple-system, system-ui, sans-serif; margin:0 auto; max-width:1100px; padding:24px 16px; }
h1 { font-size:24px; margin:0 0 4px; } h2 { font-size:18px; margin:32px 0 8px; }
.muted { color:var(--muted); } .warn { color:var(--warn); }
.scroll { overflow-x:auto; }
table { border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }
th, td { border-bottom:1px solid var(--line); padding:6px 10px; text-align:left; white-space:nowrap; }
th { background:var(--head); font-weight:600; }
code { font-size:13px; }
"""


def render(meta: dict, scores: list[VariantScore], public: bool, withheld: list[dict]) -> str:
    hidden_cost = {w["variant"] for w in withheld if w["figure"] == "cost"} if public else set()
    by_name = {s.name: s for s in scores}
    complete = sorted((s for s in scores if s.complete), key=lambda s: -s.correct["intent"])
    others = [s for s in scores if not s.complete]

    def cost_cell(s: VariantScore) -> str:
        if s.name in hidden_cost:
            return "withheld"
        if not s.price_known:
            return "unknown (no price)"
        mark = ' <span class="warn">lower bound</span>' if s.cost_is_lower_bound else ""
        return _e(_usd(s.cost_per_message, s.cost_is_lower_bound)) + mark

    parts = [
        f"<h1>Lead triage classifier bakeoff</h1>",
        f'<p class="muted">{"Public" if public else "Full"} edition · run <code>{_e(meta["run_id"])}</code> · '
        f'{_e(meta["started_at"][:10])} · dataset <code>{_e(meta["dataset_version"])}</code> · '
        f'cap ${meta["cap_usd"]:.2f} per variant</p>',
    ]
    if not public:
        parts.append('<p class="warn">Full edition: never commit this file (constitution Principle 6).</p>')

    # Head-to-head, complete variants only (B9).
    rows = []
    for s in complete:
        rows.append(
            [
                _e(s.name),
                f"{_pct(s.accuracy('intent'))} <span class='muted'>({_ci(s.intent_ci)})</span>",
                f"{_pct(s.all_four / s.classified)} <span class='muted'>({_ci(s.all_four_ci)})</span>",
                _pct(s.invalid_rate()),
                cost_cell(s),
                _secs(s.latency_p50),
                _secs(s.latency_p95),
            ]
        )
    parts.append("<h2>Head-to-head</h2>")
    parts.append(
        '<p class="muted">Complete variants only, by intent accuracy. Brackets are 95% intervals. '
        "Cost and latency are per classified message; a message's latency sums every attempt it took.</p>"
    )
    parts.append(
        '<div class="scroll">'
        + _table(
            ["Variant", "Intent accuracy", "All four correct", "Invalid or refused", "Cost / message", "p50", "p95"],
            rows,
        )
        + "</div>"
    )

    # Paired comparison against the best intent accuracy.
    if complete:
        best = complete[0]
        rows = []
        for s in complete:
            mean, lo, hi = s.paired
            verdict = "best" if s is best else ("not distinguishable" if lo <= 0 <= hi or lo > 0 else "worse")
            rows.append([_e(s.name), f"{100 * mean:+.1f}", f"{100 * lo:+.1f} to {100 * hi:+.1f}", verdict])
        parts.append("<h2>Intent accuracy against the best variant</h2>")
        parts.append(
            f'<p class="muted">Paired over the same {best.total_messages} messages, points of accuracy versus '
            f"<b>{_e(best.name)}</b>, with a 95% bootstrap interval. An interval that includes zero means the "
            "difference is within noise at this sample size.</p>"
        )
        parts.append('<div class="scroll">' + _table(["Variant", "Difference", "95% interval", "Reading"], rows) + "</div>")

    # Cost ranking (B7, B11).
    ranked = [s for s in complete if s.price_known and s.name not in hidden_cost]
    ranked.sort(key=lambda s: s.cost_per_message)
    excluded = [s.name for s in complete if s.name in hidden_cost or not s.price_known]
    parts.append("<h2>Cost ranking</h2>")
    if excluded:
        reasons = [f"{_e(n)} ({'cost withheld' if n in hidden_cost else 'no known price'})" for n in excluded]
        parts.append(f"<p>Excludes: {', '.join(reasons)}.</p>")
    rows = [[str(i + 1), _e(s.name), cost_cell(s)] for i, s in enumerate(ranked)]
    parts.append('<div class="scroll">' + _table(["Rank", "Variant", "Cost / message"], rows) + "</div>")
    if ranked and ranked[0].cost_is_lower_bound:
        parts.append(
            '<p class="warn">The cheapest variant is unconfirmed: its cost is a lower bound because some of its '
            "calls returned no cost.</p>"
        )

    # The success-criteria question.
    if complete and ranked:
        eligible = [s for s in ranked if s.paired and (s.paired[1] <= 0 <= s.paired[2] or s is complete[0])]
        parts.append("<h2>Cheapest variant within noise of the best</h2>")
        if eligible:
            w = eligible[0]
            parts.append(
                f"<p><b>{_e(w.name)}</b> at {cost_cell(w)} per message, p95 latency {_secs(w.latency_p95)}"
                f" (best accuracy variant: {_e(complete[0].name)}, p95 {_secs(complete[0].latency_p95)})."
                + (f" Excludes {', '.join(_e(n) for n in excluded)}." if excluded else "")
                + "</p>"
            )

    # Per-question accuracy, every variant that classified anything.
    rows = []
    for s in [*complete, *others]:
        if s.classified:
            rows.append([_e(s.name)] + [_pct(s.accuracy(q.name)) for q in QUESTIONS] + [_pct(s.coverage)])
    parts.append("<h2>Accuracy per question</h2>")
    parts.append('<div class="scroll">' + _table(["Variant", *[q.name for q in QUESTIONS], "Coverage"], rows) + "</div>")

    # Vendor-native tokens.
    rows = []
    for s in [*complete, *others]:
        if s.classified:
            cats = "<br>".join(f"<code>{_e(k)}</code>: {v:,.1f}" for k, v in s.tokens.items()) or "none reported"
            rows.append([_e(s.name), cats, str(s.unknown_token_calls), str(s.unknown_cost_calls), str(s.calls)])
    parts.append("<h2>Tokens per classified message</h2>")
    parts.append(
        f'<p class="warn">Reported by {_e(meta.get("billing_service", "the billing service"))} using each model\'s own tokenizer, '
        "so these numbers are not comparable across vendors.</p>"
    )
    parts.append(
        '<div class="scroll">' + _table(["Variant", "Reported tokens", "Calls with unknown tokens", "Calls with unknown cost", "Calls"], rows) + "</div>"
    )

    if others:
        # The public edition shows only the runner's short reason; the raw vendor error,
        # which may not be publishable (constitution Principle 6), is full edition only.
        rows = [
            [_e(s.name), _e(s.status), _pct(s.coverage), _e(s.reason or "some messages unclassified")]
            + ([] if public else [f"<code>{_e(s.detail[:300])}</code>" if s.detail else ""])
            for s in others
        ]
        parts.append("<h2>Partial and not-run variants</h2>")
        parts.append("<p class='muted'>Left out of the head-to-head comparison (constitution Principle 3).</p>")
        headers = ["Variant", "Status", "Coverage", "Reason"] + ([] if public else ["Last error"])
        parts.append('<div class="scroll">' + _table(headers, rows) + "</div>")

    rows = []
    for s in scores:
        price = meta["prices"].get(s.name)
        price_txt = "withheld" if s.name in hidden_cost else (_e(json.dumps(price)) if price else "unknown")
        rows.append([_e(s.name), _e(", ".join(s.models) or "none reported"), _e(", ".join(s.served_by) or "none reported"),
                     f"<code>{_e(json.dumps(s.settings))}</code>", price_txt])
    parts.append("<h2>Models, settings and prices used</h2>")
    parts.append(f'<p class="muted">Every call went through {_e(meta.get("billing_service", "the billing service"))}, which reported '
                 "each call's cost; the price list is only a fallback for calls without one.</p>")
    parts.append('<div class="scroll">' + _table(["Variant", "Model reported", "Served by", "Settings", "Fallback price (USD per million tokens)"], rows) + "</div>")

    if public and withheld:
        rows = [[_e(w["variant"]), _e(w["figure"]), _e(w["reason"])] for w in withheld if w["variant"] in by_name]
        parts.append("<h2>Withheld</h2>")
        parts.append("<p class='muted'>Figures left out of this edition. The list is fixed before a run (spec 001 B11).</p>")
        parts.append('<div class="scroll">' + _table(["Variant", "Figure", "Reason"], rows) + "</div>")

    title = "Bakeoff report" + (" (public)" if public else " (full)")
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1"><title>{title}</title>'
        f"<style>{CSS}</style></head><body>{''.join(parts)}</body></html>"
    )
