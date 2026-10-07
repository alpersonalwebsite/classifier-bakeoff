"""The four lead-triage questions (spec 001 B1).

Every provider receives exactly this text and these labels. Nothing else about
a question may differ between variants (constitution Principle 1).
"""

import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Question:
    name: str
    text: str
    labels: tuple[str, ...]


QUESTIONS: tuple[Question, ...] = (
    Question(
        name="intent",
        text="What does the sender of this message want?",
        labels=("buy", "sell", "rent", "valuation", "general question", "not a lead"),
    ),
    Question(
        name="timeline",
        text=(
            "When does the sender plan to buy, sell, rent, or move? "
            "Count when the move or transaction happens, not when an answer or a valuation is needed. "
            "Answer unknown if the message gives no time for it."
        ),
        labels=("under 3 months", "3 to 12 months", "over 12 months", "unknown"),
    ),
    Question(
        name="wants_contact",
        text=(
            "Does the sender ask for a reply addressed to them, by call, text, email, or a meeting? "
            "A post or reply on a website, portal, web form, or chat widget does not count."
        ),
        labels=("yes", "no"),
    ),
    Question(
        name="urgency",
        text=(
            "How urgent is the sender's request? "
            "Answer high only when the message names a deadline or forced move within five weeks. "
            "A general wish for speed with no date is normal."
        ),
        labels=("high", "normal"),
    ),
)

BY_NAME: dict[str, Question] = {q.name: q for q in QUESTIONS}


def questions_version() -> str:
    """A hash of the request bodies both adapters build, in both shapes (all questions at
    once, and one at a time), with a placeholder message and without model, reasoning or
    routing fields. That covers the question text, the labels, the Claude prompt template
    and the Decisions request layout, so a change to any of them changes the version and a
    report built from an older run says so (spec 001 B10)."""
    from .providers import claude_request, decisions_request

    shapes = [list(QUESTIONS)] + [[q] for q in QUESTIONS]
    payload = json.dumps(
        {
            "claude": [claude_request("<message>", shape) for shape in shapes],
            "decisions": [decisions_request("<message>", shape) for shape in shapes],
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
