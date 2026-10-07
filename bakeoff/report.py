"""Render the full and public report editions (spec 001 B10, B11)."""

import html
import json
from pathlib import Path

from .questions import QUESTIONS, questions_version
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


def dataset_note(dataset_meta: dict | None, models: dict[str, str]) -> str:
    """Spec 002 B5: say the data is synthetic and who made it, from the frozen dataset's record."""
    if not dataset_meta:
        return '<p class="warn">Dataset: no record of how it was made was found.</p>'
    gen = dataset_meta.get("generator", "an unrecorded model")
    size = dataset_meta.get("size", "?")
    note = f"Dataset: {size} synthetic messages, written by <code>{_e(gen)}</code> to match labels chosen first."
    vendor = gen.split("/", 1)[0] if "/" in gen else None
    same = sorted(name for name, model in models.items() if vendor and model.startswith(vendor + "/"))
    if same:
        note += (
            f' <span class="warn">The generator\'s vendor ({_e(vendor)}) also makes variants in this run '
            f"({_e(', '.join(same))}), which the wording of the data may favor.</span>"
        )
    return f"<p>{note}</p>"


def render(
    meta: dict,
    scores: list[VariantScore],
    public: bool,
    withheld: list[dict],
    dataset_meta: dict | None = None,
    conclusions_html: str | None = None,
    label_dependence: dict[str, tuple[float, float]] | None = None,
    relabel: dict | None = None,
) -> str:
    hidden_cost = {w["variant"] for w in withheld if w["figure"] == "cost"} if public else set()
    by_name = {s.name: s for s in scores}
    # Spec 003 B4: every section in rank order; nothing ordered by one question's accuracy.
    complete = sorted((s for s in scores if s.complete), key=lambda s: (s.rank or 0, s.tier or 0))
    others = [s for s in scores if not s.complete]

    def cost_cell(s: VariantScore) -> str:
        if s.name in hidden_cost:
            return "withheld"
        if not s.price_known:
            return "unknown (no price)"
        mark = ' <span class="warn">lower bound</span>' if s.cost_is_lower_bound else ""
        return _e(_usd(s.cost_per_message, s.cost_is_lower_bound)) + mark

    def rank_cell(s: VariantScore) -> str:
        # A withheld cost must not leak through its position inside a tier (spec 001 B11).
        if s.name in hidden_cost:
            return f"tier {s.tier}, position withheld"
        mark = ' <span class="warn">order unconfirmed</span>' if s.order_unconfirmed else ""
        return f"{s.rank}{mark}"

    parts = [
        f"<h1>Lead triage classifier bakeoff</h1>",
        f'<p class="muted">{"Public" if public else "Full"} edition · run <code>{_e(meta["run_id"])}</code> · '
        f'{_e(meta["started_at"][:10])} · dataset <code>{_e(meta["dataset_version"])}</code> · '
        f'questions <code>{_e(meta.get("questions_version", "not recorded"))}</code> · '
        f'cap ${meta["cap_usd"]:.2f} per variant</p>',
    ]
    if meta.get("questions_version") != questions_version():
        parts.append(
            '<p class="warn">This run used different question text from the current code '
            f'(current <code>{_e(questions_version())}</code>), or did not record which, so rerunning '
            "today would not reproduce these numbers.</p>"
        )
    if not public:
        parts.append('<p class="warn">Full edition: never commit this file (constitution Principle 6).</p>')
    parts.append(dataset_note(dataset_meta, meta.get("models", {})))

    # Spec 003 B3: rank 1 and the rule, before any table.
    parts.append("<h2>Ranking</h2>")
    if complete:
        top = [s for s in complete if s.rank == 1]
        names = " and ".join(f"<b>{_e(s.name)}</b>" for s in top)
        same = " (identical answers on every question)" if len(top) > 1 else ""
        parts.append(f"<p>Rank 1: {names}{same}.</p>")
    else:
        parts.append("<p>No variant classified every message, so nothing is ranked.</p>")
    parts.append(
        '<p class="muted">Rule: complete variants are ranked by the share of messages with all four answers right. '
        "A variant whose 95% paired interval against the top remaining variant includes zero shares its tier. "
        "Within a tier, cheaper ranks first, then faster at p50. Variants with identical answers share a rank. "
        "The rule was set after the first published run and is not retuned.</p>"
    )

    if conclusions_html:
        parts.append("<h2>Conclusions</h2>")
        parts.append(
            f'<p class="muted">Written analysis by the repository owner for run <code>{_e(meta["run_id"])}</code>, '
            "not generated output. Every figure it quotes was checked against this report.</p>"
        )
        parts.append(f'<div class="conclusions">{conclusions_html}</div>')

    # Head-to-head, complete variants only, in rank order (spec 001 B9, spec 003 B4).
    rows = []
    for s in complete:
        rows.append(
            [
                rank_cell(s),
                str(s.tier),
                _e(s.name),
                f"{_pct(s.all_four / s.classified)} <span class='muted'>({_ci(s.all_four_ci)})</span>",
                f"{_pct(s.accuracy('intent'))} <span class='muted'>({_ci(s.intent_ci)})</span>",
                _pct(s.invalid_rate()),
                cost_cell(s),
                _secs(s.latency_p50),
                _secs(s.latency_p95),
            ]
        )
    parts.append("<h2>Head-to-head</h2>")
    parts.append(
        '<p class="muted">Complete variants only, in rank order. Brackets are 95% intervals. '
        "Cost and latency are per classified message; a message's latency sums every attempt it took. "
        "\"Order unconfirmed\" marks a variant placed above another on a cost that is only a lower bound.</p>"
    )
    parts.append(
        '<div class="scroll">'
        + _table(
            ["Rank", "Tier", "Variant", "All four correct", "Intent", "Invalid or refused", "Cost / message", "p50", "p95"],
            rows,
        )
        + "</div>"
    )

    # Paired comparison against the rank 1 reference (spec 003 B4).
    if complete:
        ref = complete[0]
        rows = []
        for s in complete:
            m4, lo4, hi4 = s.paired_all_four
            mi, loi, hii = s.paired
            reading = "reference" if s is ref else ("within noise" if lo4 <= 0 <= hi4 else "below the reference")
            rows.append(
                [
                    _e(s.name),
                    f"{100 * m4:+.1f}",
                    f"{100 * lo4:+.1f} to {100 * hi4:+.1f}",
                    f"{100 * mi:+.1f}",
                    f"{100 * loi:+.1f} to {100 * hii:+.1f}",
                    reading,
                ]
            )
        parts.append("<h2>Against rank 1</h2>")
        parts.append(
            f'<p class="muted">Paired over the same {ref.total_messages} messages, points of accuracy versus the rank 1 '
            f"variant <b>{_e(ref.name)}</b>, with 95% bootstrap intervals. An interval that includes zero means the "
            "difference is within noise at this sample size.</p>"
        )
        parts.append(
            '<div class="scroll">'
            + _table(["Variant", "All four, difference", "95% interval", "Intent, difference", "95% interval", "Reading"], rows)
            + "</div>"
        )

    # Cost ranking (spec 001 B7, B11).
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

    # Spec 003 B6: how much each result depends on the pre-freeze label edits.
    if label_dependence:
        rows = []
        for s in complete:
            if s.name in label_dependence:
                before, after = label_dependence[s.name]
                rows.append([_e(s.name), _pct(before), _pct(after), f"{100 * (after - before):+.1f}"])
        parts.append("<h2>Dependence on the label edits</h2>")
        review = (dataset_meta or {}).get("label_review") or {}
        who = review.get("summary")
        parts.append(
            f"<p>{_e(who) if who else 'Who proposed and approved the label edits is not recorded.'}</p>"
            '<p class="muted">All four correct under the labels as generated and as frozen. This shows how much each '
            "result depends on the edits. It does not test whether the review was biased: every variant was given the "
            "revised definitions, so the change mostly measures how well each model follows that wording on the edited "
            "messages. Only an independent relabeling of those messages can test the review itself.</p>"
        )
        parts.append(
            '<div class="scroll">' + _table(["Variant", "As generated", "As frozen", "Change"], rows) + "</div>"
        )

    # Spec 004 B3-B5: the independent relabeling, or a plain statement that none exists.
    parts.append("<h2>Independent relabeling</h2>")
    if not relabel:
        parts.append("<p>No independent check of the edited labels has been made yet.</p>")
    else:
        rec = relabel["record"]
        parts.append(
            f"<p>A blind second opinion from <code>{_e(rec['rater_model'])}</code> ({_e(rec['rater_vendor'])}), a vendor with "
            f"no variant in this run, on {rec['blind_set']['messages']} messages: every message with an edited label plus "
            f"{rec['blind_set']['controls']} without, shuffled, with no label shown. It is one model's single pass, not "
            "ground truth, and it was given the same definitions the labels were edited to fit, so it tests whether the "
            "edits apply those definitions, not whether the definitions are neutral.</p>"
        )
        if rec.get("failed"):
            parts.append(f'<p class="warn">{len(rec["failed"])} messages got no answer and are left out of everything below.</p>')
        rows = []
        for q in QUESTIONS:
            a = relabel["agreement"][q.name]
            if not a["edited"]:
                continue
            base = f"{a['control_agree']} of {a['control']} ({_pct(a['control_agree'] / a['control'])})" if a["control"] else "n/a"
            rows.append([_e(q.name), str(a["edited"]), f"{a['frozen']} ({_pct(a['frozen'] / a['edited'])})",
                         f"{a['generated']} ({_pct(a['generated'] / a['edited'])})", f"{a['neither']} ({_pct(a['neither'] / a['edited'])})", base])
        parts.append("<p class='muted'>Edited labels, per question: which version the outside model agreed with, beside its "
                     "agreement with the frozen labels on that question across the controls.</p>")
        parts.append('<div class="scroll">' + _table(
            ["Question", "Edited labels", "Agrees with frozen", "Agrees with generated", "Neither", "Control agreement"], rows) + "</div>")
        alt = {s.name: s for s in relabel["ranked"]}
        rows, same = [], True
        for s in complete:
            t = alt.get(s.name)
            if t is None:
                continue
            same &= (t.rank == s.rank and t.tier == s.tier)
            rows.append([_e(s.name), f"{s.rank} (tier {s.tier})", _pct(s.all_four / s.classified),
                         f"{t.rank} (tier {t.tier})", _pct(t.all_four / t.classified)])
        top_now = {s.name for s in complete if s.rank == 1}
        top_alt = {s.name for s in relabel["ranked"] if s.rank == 1}
        verdict = ("Rank 1 and every variant's rank and tier are the same under the outside model's labels."
                   if same else ("Rank 1 is the same under the outside model's labels, but some ranks or tiers change."
                                 if top_now == top_alt else "Rank 1 changes under the outside model's labels."))
        parts.append(f"<p><b>{_e(verdict)}</b> Only the {relabel['edited_count']} edited labels were replaced; every other label is as frozen.</p>")
        parts.append('<div class="scroll">' + _table(
            ["Variant", "Rank, frozen labels", "All four, frozen", "Rank, outside labels on the edits", "All four, outside"], rows) + "</div>")

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
