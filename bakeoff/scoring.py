"""Score saved call records against ground truth (spec 001 B6, B7, B9, B10).

Reads only saved records, so a report can be rebuilt with no network access.
"""

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from .costing import flatten_usage
from .questions import QUESTIONS


def load_run(run_dir: Path) -> tuple[dict, list[dict]]:
    meta = json.loads((run_dir / "run.json").read_text())
    with (run_dir / "calls.jsonl").open(encoding="utf-8") as f:
        records = [json.loads(line) for line in f if line.strip()]
    return meta, records


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def paired_diff_ci(a: list[int], b: list[int], resamples: int = 10_000, seed: int = 0) -> tuple[float, float, float]:
    """Mean of a - b over the same messages, with a 95% bootstrap interval."""
    n = len(a)
    diffs = [x - y for x, y in zip(a, b)]
    mean = sum(diffs) / n if n else 0.0
    rng = random.Random(seed)
    stats = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples)) if n else [0.0]
    return mean, stats[int(0.025 * len(stats))], stats[min(len(stats) - 1, int(0.975 * len(stats)))]


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


@dataclass
class VariantScore:
    name: str
    status: str
    reason: str
    total_messages: int
    detail: str = ""
    classified: int = 0
    calls: int = 0
    completed_calls: int = 0
    unknown_token_calls: int = 0
    unknown_cost_calls: int = 0
    correct: dict[str, int] = field(default_factory=dict)
    invalid: dict[str, int] = field(default_factory=dict)
    intent_ci: tuple[float, float] = (0.0, 0.0)
    all_four: int = 0
    all_four_ci: tuple[float, float] = (0.0, 0.0)
    tokens: dict[str, float] = field(default_factory=dict)  # per classified message
    cost_total: float | None = None
    cost_per_message: float | None = None
    cost_is_lower_bound: bool = False
    price_known: bool = True
    latency_p50: float | None = None
    latency_p95: float | None = None
    models: list[str] = field(default_factory=list)
    served_by: list[str] = field(default_factory=list)
    settings: dict = field(default_factory=dict)
    intent_vector: dict[str, int] = field(default_factory=dict)  # message id -> 1/0
    paired: tuple[float, float, float] | None = None  # vs best, intent accuracy

    @property
    def coverage(self) -> float:
        return self.classified / self.total_messages if self.total_messages else 0.0

    @property
    def complete(self) -> bool:
        return self.status != "not run" and self.classified == self.total_messages

    def accuracy(self, question: str) -> float:
        return self.correct.get(question, 0) / self.classified if self.classified else 0.0

    def invalid_rate(self) -> float:
        answers = self.classified * len(QUESTIONS)
        return sum(self.invalid.values()) / answers if answers else 0.0


def score_variant(name: str, meta_variant: dict, price: dict | None, records: list[dict], dataset: list[dict]) -> VariantScore:
    vs = VariantScore(
        name=name,
        status=meta_variant.get("status", "complete"),
        reason=meta_variant.get("reason", ""),
        detail=meta_variant.get("detail", ""),
        total_messages=len(dataset),
        settings=meta_variant.get("settings", {}),
        price_known=price is not None,
    )
    mine = [r for r in records if r["variant"] == name]
    vs.calls = len(mine)
    vs.completed_calls = sum(r["outcome"] == "completed" for r in mine)
    vs.unknown_token_calls = sum(r["usage"] is None for r in mine)
    vs.unknown_cost_calls = sum(r["cost_usd"] is None for r in mine)
    vs.price_known = price is not None or any(r["cost_usd"] is not None for r in mine)
    vs.served_by = sorted({r["served_by"] for r in mine if r.get("served_by")})
    vs.models = sorted({r["model"] for r in mine if r.get("model")})

    final: dict[str, dict[str, dict]] = {}  # message -> question -> answer
    latency: dict[str, float] = {}
    for r in mine:
        # B7: everything a caller waits, retry backoff included.
        latency[r["message_id"]] = latency.get(r["message_id"], 0.0) + r["latency_s"] + r.get("waited_before_s", 0.0)
        if r["outcome"] == "completed":
            final.setdefault(r["message_id"], {}).update(r["answers"])

    truth = {m["id"]: m["truth"] for m in dataset}
    classified_ids = [mid for mid in truth if mid in final and all(q.name in final[mid] for q in QUESTIONS)]
    vs.classified = len(classified_ids)
    for q in QUESTIONS:
        vs.correct[q.name] = 0
        vs.invalid[q.name] = 0
    for mid in classified_ids:
        all_ok = True
        for q in QUESTIONS:
            a = final[mid][q.name]
            ok = a["status"] == "answered" and a["label"] in truth[mid][q.name]
            vs.correct[q.name] += ok
            vs.invalid[q.name] += a["status"] in ("invalid", "refused")
            all_ok &= ok
            if q.name == "intent":
                vs.intent_vector[mid] = int(ok)
        vs.all_four += all_ok
    vs.intent_ci = wilson(vs.correct["intent"], vs.classified)
    vs.all_four_ci = wilson(vs.all_four, vs.classified)

    if vs.classified:
        totals: dict[str, float] = {}
        for r in mine:
            for k, v in flatten_usage(r["usage"] or {}).items():
                if "tokens" in k.rsplit(".", 1)[-1]:  # token counts only, not cost fields
                    totals[k] = totals.get(k, 0) + v
        vs.tokens = {k: v / vs.classified for k, v in sorted(totals.items())}
        lat = [latency[mid] for mid in classified_ids]
        vs.latency_p50, vs.latency_p95 = percentile(lat, 0.5), percentile(lat, 0.95)
        if vs.price_known:
            vs.cost_total = sum(r["cost_usd"] or 0.0 for r in mine)
            vs.cost_per_message = vs.cost_total / vs.classified
            vs.cost_is_lower_bound = vs.unknown_cost_calls > 0
    # The runner decides "not run" (B9: nothing ever answered). Here a variant that
    # finished its loop with unclassified messages is partial, whatever its call count.
    if vs.status == "complete" and not vs.complete:
        vs.status = "partial"
    return vs


def score_run(meta: dict, records: list[dict], dataset: list[dict]) -> list[VariantScore]:
    scores = [
        score_variant(name, mv, meta["prices"].get(name), records, dataset) for name, mv in meta["variants"].items()
    ]
    complete = [s for s in scores if s.complete]
    if complete:
        best = max(complete, key=lambda s: s.correct["intent"])
        ids = sorted(best.intent_vector)
        for s in complete:
            s.paired = paired_diff_ci([s.intent_vector[i] for i in ids], [best.intent_vector[i] for i in ids])
    return scores
