# classifier-bakeoff

A bakeoff of classifiers on synthetic real estate lead triage: Jev (TypeSafe), OpenAI's Decisions API, and Claude.
Every call goes through OpenRouter with one key, pinned to the model's own vendor with no fallback.
The repository is public.

## Rules that come first

- `constitution.md` (v2.0.0) holds six principles every change must follow; read it before changing behavior.
- Work is spec driven: `specs/001-lead-triage-bakeoff.md` defines behavior and acceptance checks. A change to scope or behavior updates the spec in the same change, and new work starts with a new spec (`specs/002-…`).
- Nothing tied to an employer or client goes in the repo, and the data stays fictional (555-0100 to 555-0199 phone numbers, `example.com` emails).
- Never commit `results/`, `reports/full/`, `data/candidate*.jsonl`, `prices.local.json`, or `.env`; `.gitignore` covers them.
- Result numbers appear only in the public report edition (`reports/public/`) and the written conclusions that feed it (`reports/conclusions/`), never in commit messages, PR descriptions, or comments.

## Layout

- `bakeoff/questions.py`: the four questions and labels every variant receives; `questions_version()` hashes the full request bodies.
- `bakeoff/providers.py`: OpenRouter adapters (Decisions endpoint for Jev and Decisions, chat completions for Claude).
- `bakeoff/variants.py`: the six variants, the $2 default cap, and three attempts per call.
- `bakeoff/runner.py`, `scoring.py`, `report.py`: running, scoring, and the full and public report editions.
- `bakeoff/conclusions.py` and `reports/conclusions/<run_id>.md`: written conclusions for one run (spec 002). Every figure they quote must appear exactly as printed in that run's public edition, or no report is written; the owner approves the text before it is committed.
- `bakeoff/dataset.py`: generating, checking, and freezing the dataset.
- `data/dataset.jsonl`: the frozen 200-message dataset; never edit it, since a run refuses a dataset whose hash changed. `data/label-changes.md` logs the review edits made before freezing.
- `withheld.json`: figures the public edition removes (only `cost` is supported); currently empty.
- `prices.json`: fallback rates only; cost comes from OpenRouter's `usage.cost`.

## Commands

```sh
uv sync
uv run pytest                                   # 50 offline tests, no keys needed
uv run python -m bakeoff run --variant haiku-batched --limit 5   # smoke test, costs cents
uv run python -m bakeoff run                    # full run, under $1; ask before running
uv run python -m bakeoff report                 # rebuild reports from the latest saved run, no API calls
```

A full run, generation, or any call that spends money needs the owner's go-ahead first.
`OPENROUTER_API_KEY` is read from `.env` (copy `.env.example`).

## Changing the question text

Any change to question text, labels, the Claude prompt template, or the Decisions request layout changes `questions_version()`.
Earlier runs then no longer match the code, and their reports show a warning, so a fresh run is needed before publishing.
The question text and the spec's B1 definitions must say the same thing.

## Tests

Tests use hand-written OpenRouter responses, so they prove the code reads the documented shapes, not that vendors send them.
Only a real run shows real behavior (constitution Principle 3).

## Pull requests

Work on a branch and open a PR; never commit to `main`.
Add the `review` label to get a CodeRabbit review; it triggers once, so later commits need `@coderabbitai review`.
