"""Synthetic lead messages: generate, check, freeze (spec 001 B2).

Labels are chosen first and a message is then written to match them. The
generator is Claude Opus 5.5 through OpenRouter, which is not a variant under test;
generator bias toward Claude remains an open risk in the spec.
"""

import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path

from .questions import BY_NAME, QUESTIONS

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CANDIDATE_FILE = DATA_DIR / "candidate.jsonl"
DATASET_FILE = DATA_DIR / "dataset.jsonl"
META_FILE = DATA_DIR / "dataset.meta.json"

SIZE = 200
MIN_PER_LABEL = 5
TWO_INTENT = 30
NOT_A_LEAD = 25
GENERATOR_MODEL = "anthropic/claude-opus-5.5"
BATCH = 10

TWO_INTENT_PAIRS = [("buy", "sell"), ("sell", "valuation"), ("buy", "rent"), ("rent", "general question"), ("buy", "valuation")]
CHANNELS = ["web form", "email", "text message", "chat widget", "voicemail transcript"]
LENGTHS = ["one sentence", "two or three sentences", "a short paragraph"]


# --- label specs ----------------------------------------------------------


def build_specs(seed: int = 7) -> list[dict]:
    """200 label combinations that cover every label at least MIN_PER_LABEL times."""
    rng = random.Random(seed)
    lead_intents = ["buy", "sell", "rent", "valuation", "general question"]
    specs = []
    for i in range(SIZE):
        if i < NOT_A_LEAD:
            intent = ["not a lead"]
            timeline, contact, urgency = "unknown", rng.choice(["yes", "no"]), "normal"
        elif i < NOT_A_LEAD + TWO_INTENT:
            intent = list(TWO_INTENT_PAIRS[i % len(TWO_INTENT_PAIRS)])
            timeline = rng.choice(BY_NAME["timeline"].labels)
            contact, urgency = rng.choice(["yes", "no"]), rng.choice(["high", "normal"])
        else:
            intent = [lead_intents[i % len(lead_intents)]]
            timeline = rng.choice(BY_NAME["timeline"].labels)
            contact, urgency = rng.choice(["yes", "no"]), rng.choice(["high", "normal", "normal"])
        specs.append(
            {
                "id": f"m{i + 1:03d}",
                "truth": {"intent": intent, "timeline": [timeline], "wants_contact": [contact], "urgency": [urgency]},
                "style": {"channel": rng.choice(CHANNELS), "length": rng.choice(LENGTHS)},
            }
        )
    rng.shuffle(specs)
    for i, s in enumerate(specs):
        s["id"] = f"m{i + 1:03d}"
    return specs


# --- checks ---------------------------------------------------------------

# Any run of digits shaped like a North American phone number.
PHONE_RE = re.compile(r"(?:\+?1[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}\b")
EMAIL_RE = re.compile(r"[\w.+-]+@([\w-]+(?:\.[\w-]+)+)")


def phone_is_fictional(raw: str) -> bool:
    digits = re.sub(r"\D", "", raw)[-7:]
    return digits[:3] == "555" and 100 <= int(digits[3:]) <= 199


def check_message(text: str) -> list[str]:
    problems = []
    for m in PHONE_RE.finditer(text):
        if not phone_is_fictional(m.group(0)):
            problems.append(f"phone {m.group(0)!r} is outside 555-0100 to 555-0199")
    for m in EMAIL_RE.finditer(text):
        if m.group(1).lower() != "example.com":
            problems.append(f"email {m.group(0)!r} is not at example.com")
    return problems


def check_dataset(rows: list[dict]) -> list[str]:
    """Every problem that blocks freezing. Empty means the dataset may be frozen."""
    problems = []
    if len(rows) != SIZE:
        problems.append(f"{len(rows)} messages, expected {SIZE}")
    ids = [r.get("id") for r in rows]
    if len(set(ids)) != len(ids):
        problems.append("duplicate message ids")
    counts: dict[str, Counter] = {q.name: Counter() for q in QUESTIONS}
    for r in rows:
        text = r.get("text")
        if not isinstance(text, str) or not text.strip():
            problems.append(f"{r.get('id')}: empty text")
            continue
        for p in check_message(text):
            problems.append(f"{r['id']}: {p}")
        for q in QUESTIONS:
            labels = r.get("truth", {}).get(q.name, [])
            if not labels or any(label not in q.labels for label in labels):
                problems.append(f"{r['id']}: bad ground truth for {q.name}: {labels}")
            counts[q.name].update(labels)
    for q in QUESTIONS:
        for label in q.labels:
            if counts[q.name][label] < MIN_PER_LABEL:
                problems.append(f"label {q.name}={label!r} appears {counts[q.name][label]} times, needs {MIN_PER_LABEL}")
    return problems


# --- generation -----------------------------------------------------------

GENERATOR_PROMPT = """Write realistic inbound messages that a real estate agent might receive. Each one must match its spec exactly.

Rules for every message:
- Every personal detail is fictional. Use invented names. Phone numbers only from 555-0100 to 555-0199, written like 206-555-0142. Email addresses only at example.com. Street addresses only on invented streets.
- Do not name real brokerages, agents, or companies.
- Write in the voice of the sender, in the given channel and length. Do not mention these rules or the labels.

What the labels mean:
- intent: what the sender wants (buy, sell, rent, valuation, general question, or not a lead such as spam, a vendor pitch, or a wrong number). When a spec lists two intents, the message must clearly mention both, without making one obviously the main one.
- timeline: when the move or transaction happens, not when an answer or a valuation is needed. "unknown" means the message gives no time for it.
- wants_contact: "yes" only if the sender asks for a reply addressed to them, by call, text, email, or a meeting. A post or reply on a website, portal, web form, or chat widget does not count.
- urgency: "high" only when the message names a deadline or forced move within five weeks; a general wish for speed with no date is normal.

Specs:
{specs}

Return one message per spec, with the same id."""


def generate(specs: list[dict], post=None) -> list[dict]:
    """Write one message per spec with the generator model, through OpenRouter."""
    from .providers import _OpenRouter

    post = post or _OpenRouter().post
    schema = {
        "type": "object",
        "properties": {
            "messages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}, "text": {"type": "string"}},
                    "required": ["id", "text"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["messages"],
        "additionalProperties": False,
    }
    rows, cost = [], 0.0
    for start in range(0, len(specs), BATCH):
        batch = specs[start : start + BATCH]
        brief = [{"id": s["id"], **s["truth"], **s["style"]} for s in batch]
        body = post(
            "/v1/chat/completions",
            {
                "model": GENERATOR_MODEL,
                "max_tokens": 16000,
                "messages": [{"role": "user", "content": GENERATOR_PROMPT.format(specs=json.dumps(brief, indent=1))}],
                "response_format": {"type": "json_schema", "json_schema": {"name": "messages", "strict": True, "schema": schema}},
                "reasoning": {"effort": "low"},
                "provider": {"only": ["anthropic"], "allow_fallbacks": False},
            },
        )
        choice = body["choices"][0]
        if choice.get("finish_reason") not in ("stop", "end_turn"):
            raise RuntimeError(f"generation stopped early ({choice.get('finish_reason')}) at batch starting {start}")
        written = {m["id"]: m["text"] for m in json.loads(choice["message"]["content"])["messages"]}
        for s in batch:
            rows.append({"id": s["id"], "text": written.get(s["id"], ""), "truth": s["truth"], "style": s["style"]})
        cost += float((body.get("usage") or {}).get("cost") or 0.0)
        print(f"  generated {len(rows)}/{len(specs)}, cost so far ${cost:.4f}", flush=True)
    return rows


# --- files ----------------------------------------------------------------


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def version_of(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def freeze(candidate: Path = CANDIDATE_FILE) -> str:
    rows = read_jsonl(candidate)
    problems = check_dataset(rows)
    if problems:
        raise ValueError("not frozen:\n  " + "\n  ".join(problems))
    if DATASET_FILE.exists():
        raise FileExistsError(f"{DATASET_FILE} is already frozen; delete it deliberately to refreeze")
    write_jsonl(DATASET_FILE, rows)
    version = version_of(DATASET_FILE)
    META_FILE.write_text(json.dumps({"version": version, "size": len(rows), "generator": GENERATOR_MODEL}, indent=2) + "\n")
    return version


def load_frozen() -> tuple[list[dict], str]:
    if not DATASET_FILE.exists():
        raise FileNotFoundError("no frozen dataset; run `bakeoff generate`, review it, then `bakeoff freeze`")
    meta = json.loads(META_FILE.read_text())
    version = version_of(DATASET_FILE)
    if version != meta["version"]:
        raise ValueError(f"dataset changed after freezing ({version} != {meta['version']})")
    return read_jsonl(DATASET_FILE), version
