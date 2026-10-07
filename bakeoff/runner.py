"""Run variants over the frozen dataset and save every call (spec 001 B4, B5, B8, B9)."""

import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from .costing import call_cost, usage_from_response
from .questions import QUESTIONS
from .variants import DEFAULT_CAP_USD, MAX_ATTEMPTS, Variant, make_provider

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
RETRYABLE_STATUSES = {408, 409, 429}
AUTH_STATUSES = {401, 403}

# Cap projection before any call has completed: a generous request and a full
# output budget. Used only to decide whether the next call may start.
_INITIAL_INPUT_TOKENS = 2000
_INITIAL_OUTPUT_TOKENS = 256


@dataclass
class VariantOutcome:
    variant: str
    status: str = "complete"  # complete | partial | not run
    reason: str = ""
    calls: int = 0
    completed_calls: int = 0
    unknown_token_calls: int = 0
    unknown_cost_calls: int = 0
    spend_known_usd: float = 0.0
    spend_projected_usd: float = 0.0
    settings: dict = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _retryable(status: int | None) -> bool:
    # No HTTP status means the request never got an answer: timeout or connection error.
    return status is None or status in RETRYABLE_STATUSES or status >= 500


class _Writer:
    def __init__(self, path: Path):
        self._file = path.open("a", encoding="utf-8")
        self._lock = threading.Lock()

    def write(self, record: dict) -> None:
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            self._file.write(line + "\n")
            self._file.flush()

    def close(self) -> None:
        self._file.close()


def run_variant(
    variant: Variant,
    dataset: list[dict],
    writer: _Writer,
    run_id: str,
    price: dict | None,
    cap_usd: float,
    provider=None,
    sleep=time.sleep,
) -> VariantOutcome:
    out = VariantOutcome(variant.name)
    try:
        provider = provider or make_provider(variant)
    except Exception as exc:  # missing key, bad config
        out.status, out.reason = "not run", f"client could not start: {type(exc).__name__}: {exc}"
        return out
    out.settings = dict(provider.settings)

    shapes = [list(QUESTIONS)] if variant.batched else [[q] for q in QUESTIONS]
    first_attempt_calls = len(dataset) * len(shapes)
    # B8: with no known price, a call count that can never cut a full run short is the
    # backstop until the first reported cost lets the dollar cap take over.
    max_calls = None if price is not None else first_attempt_calls * MAX_ATTEMPTS
    initial_estimate = (
        call_cost({"input_tokens": _INITIAL_INPUT_TOKENS, "output_tokens": _INITIAL_OUTPUT_TOKENS}, price)
        if price is not None
        else None
    )
    worst_call = 0.0

    for message in dataset:
        for request_index, questions in enumerate(shapes):
            for attempt in range(1, MAX_ATTEMPTS + 1):
                if max_calls is not None and out.calls >= max_calls:
                    out.status, out.reason = "partial", f"call cap of {max_calls} reached"
                    return out
                # Dollar cap: projected from the price list before any cost is known,
                # then from the costliest call so far.
                if price is not None or worst_call > 0:
                    next_cost = max(worst_call, initial_estimate or 0.0)
                    if out.spend_projected_usd + next_cost > cap_usd:
                        out.status = "partial"
                        out.reason = f"spend cap of ${cap_usd:.2f} reached"
                        return out

                provider.transport.reset()
                started_at = _now()
                t0 = time.perf_counter()
                answers, error = None, None
                try:
                    answers = provider.ask(message["text"], questions)
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                latency = time.perf_counter() - t0

                ex = provider.transport.last
                status = ex.status if ex else None
                body = ex.response_body if ex else None
                usage = usage_from_response(body) if answers is not None or status else None
                cost = call_cost(usage, price)
                out.calls += 1
                if answers is not None:
                    out.completed_calls += 1
                if usage is None:
                    out.unknown_token_calls += 1
                if cost is None:
                    out.unknown_cost_calls += 1
                if cost is not None:
                    out.spend_known_usd += cost
                    out.spend_projected_usd += cost
                    worst_call = max(worst_call, cost)
                elif price is not None or worst_call > 0:
                    # Unknown cost: count the call at its projection so the cap still holds.
                    out.spend_projected_usd += max(worst_call, initial_estimate or 0.0)

                writer.write(
                    {
                        "run_id": run_id,
                        "variant": variant.name,
                        "message_id": message["id"],
                        "request_index": request_index,
                        "questions": [q.name for q in questions],
                        "attempt": attempt,
                        "outcome": "completed" if answers is not None else "failed",
                        "answers": {k: {"status": a.status, "label": a.label, "raw": a.raw} for k, a in answers.items()}
                        if answers is not None
                        else None,
                        "error": error,
                        "http_status": status,
                        "latency_s": round(latency, 4),
                        "started_at": started_at,
                        "request_url": ex.url if ex else None,
                        "request_headers": ex.request_headers if ex else None,
                        "request": ex.request_body if ex else None,
                        "response": body,
                        "usage": usage,
                        "cost_usd": cost,
                        "model": body.get("model") if isinstance(body, dict) else None,
                        "served_by": body.get("provider") if isinstance(body, dict) else None,
                    }
                )

                if answers is not None:
                    break
                if status in AUTH_STATUSES:
                    out.status = "not run" if out.completed_calls == 0 else "partial"
                    out.reason = f"authentication refused (HTTP {status}): {error}"
                    return out
                if not _retryable(status) or attempt == MAX_ATTEMPTS:
                    if out.completed_calls == 0:
                        # B9: never reached the provider at all.
                        out.status, out.reason = "not run", f"no call completed; last error: {error}"
                        return out
                    break
                sleep(2 ** (attempt - 1))
    return out


def run(
    variants: list[Variant],
    dataset: list[dict],
    dataset_version: str,
    prices: dict[str, dict],
    cap_usd: float = DEFAULT_CAP_USD,
    results_dir: Path = RESULTS_DIR,
) -> Path:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    run_dir = results_dir / run_id
    run_dir.mkdir(parents=True)
    writer = _Writer(run_dir / "calls.jsonl")
    started = _now()
    # Variants run at the same time; calls inside one variant run one at a time.
    with ThreadPoolExecutor(max_workers=len(variants)) as pool:
        futures = {
            v.name: pool.submit(run_variant, v, dataset, writer, run_id, prices.get(v.model), cap_usd)
            for v in variants
        }
        outcomes = {name: f.result() for name, f in futures.items()}
    writer.close()
    meta = {
        "run_id": run_id,
        "started_at": started,
        "finished_at": _now(),
        "dataset_version": dataset_version,
        "cap_usd": cap_usd,
        "billing_service": "OpenRouter",
        "prices": {v.name: prices.get(v.model) for v in variants},
        "models": {v.name: v.model for v in variants},
        "variants": {name: o.__dict__ for name, o in outcomes.items()},
    }
    (run_dir / "run.json").write_text(json.dumps(meta, indent=2))
    return run_dir
