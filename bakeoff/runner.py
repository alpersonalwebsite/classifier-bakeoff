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
from .providers import MalformedResponse
from .questions import QUESTIONS, questions_version
from .variants import DEFAULT_CAP_USD, MAX_ATTEMPTS, Variant, make_provider

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
RETRYABLE_STATUSES = {408, 409, 429}
# Statuses that end a variant at once, because no later call can succeed. 403 is
# deliberately absent: it may be a per-message refusal rather than an account problem
# (unverified for OpenRouter), so it fails that message and the run moves on.
STOP_STATUSES = {401: "authentication refused", 402: "out of credits"}
# A variant that fails this many messages in a row stops, so a broken request shape or
# a provider outage costs a handful of calls rather than the whole dataset.
MAX_CONSECUTIVE_FAILED_MESSAGES = 5

# Cap projection before any call has completed: a generous request and a full
# output budget. Used only to decide whether the next call may start.
_INITIAL_INPUT_TOKENS = 2000
_INITIAL_OUTPUT_TOKENS = 256


@dataclass
class VariantOutcome:
    variant: str
    status: str = "complete"  # complete | partial | not run
    reason: str = ""  # short and vendor-free: it is printed in the public edition
    detail: str = ""  # the last raw error, for the full edition only
    calls: int = 0
    completed_calls: int = 0
    unknown_token_calls: int = 0
    unknown_cost_calls: int = 0
    spend_known_usd: float = 0.0
    spend_projected_usd: float = 0.0
    settings: dict = field(default_factory=dict)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _retryable(status: int | None, malformed: bool) -> bool:
    # No HTTP status means the request never got an answer: timeout or connection error.
    # A 200 whose body is not the documented shape is retried too: it is a transport
    # problem, not the model's answer.
    return malformed or status is None or status in RETRYABLE_STATUSES or status >= 500


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
    questions=QUESTIONS,
) -> VariantOutcome:
    out = VariantOutcome(variant.name)
    try:
        provider = provider or make_provider(variant)
    except Exception as exc:  # missing key, bad config
        out.status, out.reason = "not run", f"client could not start: {type(exc).__name__}: {exc}"
        return out
    out.settings = dict(provider.settings)

    shapes = [list(questions)] if variant.batched else [[q] for q in questions]
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
    reached_provider = False  # any HTTP response at all (B9)
    consecutive_failed = 0

    def finish(kind: str, reason: str) -> VariantOutcome:
        # B9: "not run" only when nothing ever answered, or the key was refused outright.
        never_answered = out.completed_calls == 0 and (not reached_provider or kind == "auth")
        out.status = "not run" if never_answered else "partial"
        out.reason = reason
        return out

    for message in dataset:
        message_failed = False
        for request_index, questions in enumerate(shapes):
            waited = 0.0
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
                answers, error, malformed = None, None, False
                try:
                    answers = provider.ask(message["text"], questions)
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                    malformed = isinstance(exc, MalformedResponse)
                latency = time.perf_counter() - t0

                ex = provider.transport.last
                status = ex.status if ex else None
                reached_provider = reached_provider or status is not None
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
                        "waited_before_s": waited,  # retry backoff before this attempt (B7)
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
                out.detail = error or ""
                if status in STOP_STATUSES:
                    return finish("auth" if status == 401 else "stop", f"{STOP_STATUSES[status]} (HTTP {status})")
                if not _retryable(status, malformed) or attempt == MAX_ATTEMPTS:
                    message_failed = True
                    break
                pause = 2 ** (attempt - 1)
                sleep(pause)
                waited = float(pause)
        consecutive_failed = consecutive_failed + 1 if message_failed else 0
        if consecutive_failed >= MAX_CONSECUTIVE_FAILED_MESSAGES:
            last = f"HTTP {status}" if status is not None else "no response"
            return finish("stop", f"{consecutive_failed} messages in a row failed (last: {last})")
    return out


def _safe_run_variant(*args, **kwargs) -> VariantOutcome:
    """A crash in one variant must not lose the run summary for all of them."""
    try:
        return run_variant(*args, **kwargs)
    except Exception as exc:
        out = VariantOutcome(args[0].name, status="partial", reason=f"runner crashed ({type(exc).__name__})")
        out.detail = f"{type(exc).__name__}: {exc}"
        return out


def run(
    variants: list[Variant],
    dataset: list[dict],
    dataset_version: str,
    prices: dict[str, dict],
    cap_usd: float = DEFAULT_CAP_USD,
    results_dir: Path = RESULTS_DIR,
    question_set: str = "current",
) -> Path:
    from .questions import load_set

    questions = load_set(question_set)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    run_dir = results_dir / run_id
    run_dir.mkdir(parents=True)
    writer = _Writer(run_dir / "calls.jsonl")
    started = _now()
    try:
        # Variants run at the same time; calls inside one variant run one at a time.
        with ThreadPoolExecutor(max_workers=len(variants)) as pool:
            futures = {
                v.name: pool.submit(_safe_run_variant, v, dataset, writer, run_id, prices.get(v.model), cap_usd, questions=questions)
                for v in variants
            }
            outcomes = {name: f.result() for name, f in futures.items()}
    finally:
        writer.close()
    meta = {
        "run_id": run_id,
        "started_at": started,
        "finished_at": _now(),
        "dataset_version": dataset_version,
        "question_set": question_set,
        "questions_version": questions_version(questions),
        "cap_usd": cap_usd,
        "billing_service": "OpenRouter",
        "prices": {v.name: prices.get(v.model) for v in variants},
        "models": {v.name: v.model for v in variants},
        "variants": {name: o.__dict__ for name, o in outcomes.items()},
    }
    (run_dir / "run.json").write_text(json.dumps(meta, indent=2))
    return run_dir
