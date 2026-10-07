"""Turn a vendor's raw usage object into token counts and dollars.

Token counts are copied from the response body as the vendor sent them
(constitution Principle 2). Nothing here estimates a token count.
"""


def flatten_usage(usage: object, prefix: str = "") -> dict[str, int]:
    """Every numeric leaf of a usage object, keyed by its dotted path."""
    out: dict[str, int] = {}
    if isinstance(usage, dict):
        for key, value in usage.items():
            path = f"{prefix}{key}"
            if isinstance(value, bool):
                continue
            if isinstance(value, (int, float)):
                out[path] = value
            elif isinstance(value, dict):
                out.update(flatten_usage(value, f"{path}."))
    return out


def usage_from_response(body: object) -> dict | None:
    """The `usage` object in a raw response body, or None when the vendor sent none."""
    if isinstance(body, dict) and isinstance(body.get("usage"), dict):
        usage = body["usage"]
        # A usage object whose token fields are all null reports nothing.
        if any(isinstance(v, (int, float)) for v in flatten_usage(usage).values()):
            return usage
    return None


def call_cost(usage: dict | None, price: dict | None) -> float | None:
    """Dollars for one call: the billing service's own figure when it sent one
    (constitution Principle 2), else tokens times the price list, else None."""
    if usage is None:
        return None
    reported = usage.get("cost")
    if isinstance(reported, (int, float)) and not isinstance(reported, bool):
        return float(reported)
    if price is None:
        return None
    tokens = flatten_usage(usage)
    per_m = 1_000_000

    def get(key: str) -> float:
        return float(tokens.get(key) or 0)

    if "cache_read_input_tokens" in tokens or "cache_creation_input_tokens" in tokens:
        # Anthropic: input_tokens excludes cache reads and writes, each priced separately.
        return (
            get("input_tokens") * price["input"]
            + get("cache_read_input_tokens") * price.get("cache_read_input", price["input"])
            + get("cache_creation_input_tokens") * price.get("cache_creation_input", price["input"])
            + get("output_tokens") * price["output"]
        ) / per_m
    # OpenRouter chat completions name them prompt/completion; Decisions name them input/output.
    inp = get("input_tokens") or get("prompt_tokens")
    out = get("output_tokens") or get("completion_tokens")
    return (inp * price["input"] + out * price["output"]) / per_m
