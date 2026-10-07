# Classifier bakeoff

Compares three classifiers on the same synthetic lead-triage task: Jev (TypeSafe), OpenAI's Decisions API, and Claude.
All three run through [OpenRouter](https://openrouter.ai) with one key, each pinned to its own vendor with no fallback.
It measures accuracy, invalid answers, vendor-reported tokens, cost, and latency per message.

The rules every run follows are in [`constitution.md`](constitution.md), and the behavior is specified in [`specs/001-lead-triage-bakeoff.md`](specs/001-lead-triage-bakeoff.md).

## Results

The latest public report is [`reports/public/20261007T194642Z-ba611a.html`](reports/public/20261007T194642Z-ba611a.html), from a run on 2026-10-07 over the frozen dataset with question text `sha256:2db74e1065302281`.
Its conclusions, written for that run, are in [`reports/conclusions/20261007T194642Z-ba611a.md`](reports/conclusions/20261007T194642Z-ba611a.md) and appear at the top of the report.
GitHub shows HTML as source, so download it and open it in a browser.

## Setup

```sh
uv sync
cp .env.example .env   # then set OPENROUTER_API_KEY; .env is gitignored
```

Cost comes from the `usage.cost` OpenRouter returns with every call.
`prices.json` is only a fallback and the spend cap's first projection; Jev's rate is not committed.

## Use

```sh
uv run python -m bakeoff generate      # write data/candidate.jsonl (one-time, Claude Opus 5.5)
uv run python -m bakeoff check         # rerun the fictional-details and label-coverage checks
uv run python -m bakeoff freeze        # freeze it as data/dataset.jsonl after you have reviewed it
uv run python -m bakeoff run           # all six variants, then both reports
uv run python -m bakeoff run --variant haiku-batched --limit 5   # smoke test
uv run python -m bakeoff report        # rebuild reports from the latest saved run, no API calls
uv run pytest
```

## What stays local

| Path | Committed | Why |
|---|---|---|
| `data/dataset.jsonl` | yes | the frozen, fictional dataset anyone can rerun |
| `reports/public/` | yes | figures that can be published; withheld ones are listed in each report |
| `results/` | no | raw vendor responses |
| `reports/full/` | no | every figure, including withheld ones |
| `prices.local.json` | no | optional local rates, such as Jev's |

Figures withheld from the public edition are listed in [`withheld.json`](withheld.json), fixed before a run.
