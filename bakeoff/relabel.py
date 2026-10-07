"""An independent, blind relabeling of the reviewed messages (spec 004).

A model from a vendor with no variant under test labels the messages that carry
an edited label, plus a fixed set of controls, without seeing any label. Its
answers are compared with the frozen and the generated labels per question
(B3), and the ranking is recomputed with its answer in place of each edited
label only (B4).
"""

import json
import random
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from .costing import call_cost, usage_from_response
from .dataset import LABEL_CHANGES_FILE, ROOT
from .providers import Answer, _OpenRouter, claude_request, judge
from .questions import QUESTIONS

RATER_MODEL = "google/gemini-3.1-pro-preview"
RATER_ENDPOINT = "google-vertex/global"
RATER_VENDOR = "google"
RATER_REASONING = {"effort": "low"}
# The variants' 256-token cap leaves no room for a reasoning model: on the first pass,
# 2026-10-07, Gemini spent about 243 of them reasoning and 36 of 72 answers were cut
# off (finish_reason "length"). Wording is unchanged; only the budget differs.
RATER_MAX_TOKENS = 4096
RATER_CAP_USD = 3.0
CONTROL_COUNT = 30
SEED = 4
RELABEL_DIR = ROOT / "data" / "relabel"
RELABEL_FILE = RELABEL_DIR / "gemini-3.1-pro-preview.json"
_ROW = re.compile(r"^\| (m\d{3}) \| (\w+) \| ([^|]+) \| ([^|]+) \|")


def edited_labels(changes_file: Path | None = None) -> dict[tuple[str, str], tuple[list[str], list[str]]]:
    """(message, question) -> (generated labels, frozen labels), from the committed log."""
    out = {}
    for line in (changes_file or LABEL_CHANGES_FILE).read_text(encoding="utf-8").splitlines():
        m = _ROW.match(line)
        if m:
            old = [x.strip() for x in m.group(3).split(" / ")]
            new = [x.strip() for x in m.group(4).split(" / ")]
            out[(m.group(1), m.group(2))] = (old, new)
    return out


def blind_set(dataset: list[dict], edits: dict, seed: int = SEED, controls: int = CONTROL_COUNT) -> list[dict]:
    """B1: every message with an edited label plus a fixed sample of the rest, shuffled,
    under opaque identifiers. Only the text goes to the rater; the mapping stays here."""
    edited_ids = sorted({mid for mid, _ in edits})
    rng = random.Random(seed)
    untouched = sorted(m["id"] for m in dataset if m["id"] not in set(edited_ids))
    chosen = edited_ids + sorted(rng.sample(untouched, controls))
    rng.shuffle(chosen)
    text = {m["id"]: m["text"] for m in dataset}
    return [{"blind_id": f"b{i + 1:02d}", "message_id": mid, "text": text[mid]} for i, mid in enumerate(chosen)]


def rater_request(text: str) -> dict:
    """The same request body every Claude variant gets for all four questions (spec 004
    B1: identical question and label wording), plus the rater's model, reasoning and
    endpoint pin."""
    return {
        "model": RATER_MODEL,
        **claude_request(text, list(QUESTIONS)),
        "max_tokens": RATER_MAX_TOKENS,
        "reasoning": RATER_REASONING,
        "provider": {"only": [RATER_ENDPOINT], "allow_fallbacks": False},
    }


def _parse(body: dict) -> dict[str, Answer]:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("no choices in the response")
    if choices[0].get("finish_reason") == "length":
        raise ValueError("answer cut off at the output limit")
    message = choices[0].get("message") or {}
    content = message.get("content") or ""
    # Strict JSON output is not enforced on this endpoint: answers can arrive inside a
    # markdown code fence, so read the first JSON object in the text.
    match = re.search(r"\{.*\}", content, flags=re.S)
    try:
        data = json.loads(match.group(0)) if match else {}
    except ValueError:
        data = {}
    data = data if isinstance(data, dict) else {}
    return {q.name: judge(q, data.get(q.name)) for q in QUESTIONS}


def run(items: list[dict], client: _OpenRouter | None = None, results_dir: Path | None = None, sleep=time.sleep) -> dict:
    """One labeling pass with retries and a spend cap. Raw responses go to results/,
    which never leaves the machine; the returned record is what gets committed."""
    client = client or _OpenRouter()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = (results_dir or ROOT / "results") / f"relabel-{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    labels, failed, served, models = {}, [], set(), set()
    spent, worst = 0.0, 0.0
    with (out_dir / "calls.jsonl").open("w", encoding="utf-8") as log:
        for item in items:
            done = False
            for attempt in range(1, 4):
                if spent + worst > RATER_CAP_USD:
                    break
                client.transport.reset()
                error = None
                try:
                    answers = _parse(client.post("/v1/chat/completions", rater_request(item["text"])))
                except Exception as exc:
                    answers, error = None, f"{type(exc).__name__}: {exc}"
                ex = client.transport.last
                body = ex.response_body if ex else None
                cost = call_cost(usage_from_response(body), None)
                if cost is not None:
                    spent += cost
                    worst = max(worst, cost)
                if isinstance(body, dict) and body.get("provider"):
                    served.add(body["provider"])
                if isinstance(body, dict) and body.get("model"):
                    models.add(body["model"])
                log.write(json.dumps({"blind_id": item["blind_id"], "attempt": attempt, "error": error, "request": ex.request_body if ex else None, "response": body, "cost_usd": cost}) + "\n")
                if answers is not None:
                    labels[item["message_id"]] = {k: a.label for k, a in answers.items()}
                    done = True
                    break
                sleep(2 ** (attempt - 1))
            if not done:
                failed.append(item["message_id"])
    return {
        "rater_model": RATER_MODEL,
        "rater_vendor": RATER_VENDOR,
        "models_reported": sorted(models),
        "endpoint_requested": RATER_ENDPOINT,
        "served_by": sorted(served),
        "settings": {"reasoning": RATER_REASONING, "max_tokens": RATER_MAX_TOKENS, "structured_output": "strict JSON schema requested, labels only; JSON read from a code fence when the endpoint adds one", "spend_cap_usd": RATER_CAP_USD},
        "request_shape": "the Claude variants' batched request body for each message, unchanged",
        "blind_set": {"seed": SEED, "controls": CONTROL_COUNT, "messages": len(items)},
        "date": stamp,
        "cost_usd": round(spent, 6),
        "labels": labels,
        "failed": failed,
    }


def load(path: Path | None = None) -> dict | None:
    p = path or RELABEL_FILE
    return json.loads(p.read_text()) if p.exists() else None


def agreement(record: dict, dataset: list[dict], edits: dict) -> dict:
    """B3: per question, on edited labels and on the controls."""
    truth = {m["id"]: m["truth"] for m in dataset}
    edited_ids = {mid for mid, _ in edits}
    out = {}
    for q in QUESTIONS:
        row = {"edited": 0, "frozen": 0, "generated": 0, "neither": 0, "control": 0, "control_agree": 0}
        for (mid, qn), (old, new) in edits.items():
            if qn != q.name or mid not in record["labels"]:
                continue
            ans = record["labels"][mid][q.name]
            row["edited"] += 1
            if ans in new:
                row["frozen"] += 1
            elif ans in old:
                row["generated"] += 1
            else:
                row["neither"] += 1
        for mid, ans in record["labels"].items():
            if mid in edited_ids:
                continue
            row["control"] += 1
            row["control_agree"] += ans[q.name] in truth[mid][q.name]
        out[q.name] = row
    return out


def with_rater_on_edits(dataset: list[dict], record: dict, edits: dict) -> list[dict]:
    """B4: the dataset with the rater's answer in place of each edited label only."""
    import copy

    out = copy.deepcopy(dataset)
    by_id = {m["id"]: m for m in out}
    for (mid, q), _ in edits.items():
        # An invalid answer from the rater keeps the frozen label rather than marking
        # every variant wrong on it.
        answer = record["labels"].get(mid, {}).get(q)
        if answer is not None:
            by_id[mid]["truth"][q] = [answer]
    return out


def check_independent(record: dict, models: dict[str, str]) -> None:
    """B2: the rater's vendor must not make any variant in the run."""
    vendors = {m.split("/", 1)[0] for m in models.values()}
    if record["rater_vendor"] in vendors:
        raise ValueError(f"rater vendor {record['rater_vendor']} also makes a variant in this run")
