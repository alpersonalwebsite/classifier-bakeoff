"""The six variants (spec 001 B3), their prices, and their spend caps (B8)."""

import json
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRICES_FILE = ROOT / "prices.json"
# Jev's rate stays out of committed files while its disclosure question is
# open (spec 001 Risks, constitution Principle 6).
LOCAL_PRICES_FILE = ROOT / "prices.local.json"

DEFAULT_CAP_USD = 2.0
MAX_ATTEMPTS = 3  # first attempt plus up to 2 retries


@dataclass(frozen=True)
class Variant:
    name: str
    kind: str  # "decisions" (OpenRouter Decisions endpoint) | "chat" (OpenRouter chat completions)
    model: str  # OpenRouter model id
    vendor: str  # OpenRouter provider slug the request is pinned to
    batched: bool


VARIANTS: tuple[Variant, ...] = (
    Variant("jev", "decisions", "typesafe/jev-1.13", "typesafe", True),
    Variant("decisions-batched", "decisions", "openai/gpt-6-luna-decisions", "openai", True),
    Variant("decisions-per-q", "decisions", "openai/gpt-6-luna-decisions", "openai", False),
    Variant("sonnet-batched", "chat", "anthropic/claude-sonnet-5.5", "anthropic", True),
    Variant("haiku-per-q", "chat", "anthropic/claude-haiku-4.5", "anthropic", False),
    Variant("haiku-batched", "chat", "anthropic/claude-haiku-4.5", "anthropic", True),
)
BY_NAME = {v.name: v for v in VARIANTS}


def load_prices() -> dict[str, dict]:
    prices = json.loads(PRICES_FILE.read_text())
    if LOCAL_PRICES_FILE.exists():
        prices.update(json.loads(LOCAL_PRICES_FILE.read_text()))
    return {k: v for k, v in prices.items() if not k.startswith("_")}


def make_provider(variant: Variant):
    from . import providers

    if variant.kind == "chat":
        return providers.ClaudeProvider(variant.model)
    if variant.kind == "decisions":
        return providers.DecisionsRouterProvider(variant.model, variant.vendor)
    raise ValueError(variant.kind)
