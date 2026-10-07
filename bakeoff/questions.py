"""The four lead-triage questions (spec 001 B1).

Every provider receives exactly this text and these labels. Nothing else about
a question may differ between variants (constitution Principle 1).
"""

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
            "A post on a website or portal does not count."
        ),
        labels=("yes", "no"),
    ),
    Question(
        name="urgency",
        text=(
            "How urgent is the sender's request? "
            "Answer high only when the message names a deadline or forced move within about four weeks; "
            "otherwise answer normal."
        ),
        labels=("high", "normal"),
    ),
)

BY_NAME: dict[str, Question] = {q.name: q for q in QUESTIONS}
