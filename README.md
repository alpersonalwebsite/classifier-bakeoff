# Classifier bakeoff

Compares three classifiers on the same synthetic lead-triage task: Jev (TypeSafe), OpenAI's Decisions API, and Claude.
All three run through [OpenRouter](https://openrouter.ai) with one key, each pinned to its own vendor with no fallback.
It measures accuracy, invalid answers, vendor-reported tokens, cost, and latency per message.

The rules every run follows are in [`constitution.md`](constitution.md), and the behavior is specified in [`specs/001-lead-triage-bakeoff.md`](specs/001-lead-triage-bakeoff.md).

## Results

The latest public report is at https://alpersonalwebsite.github.io/classifier-bakeoff/reports/public/20261007T235443Z-da1571.html, from a run on 2026-10-07 over the frozen dataset with question text `sha256:6cbd46e11dc7a47c`.
Its source is [`reports/public/20261007T235443Z-da1571.html`](reports/public/20261007T235443Z-da1571.html), and its conclusions are in [`reports/conclusions/20261007T235443Z-da1571.md`](reports/conclusions/20261007T235443Z-da1571.md).

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

## Check the labels yourself

You can test the labels with your own reading, blind, in about 40 minutes, with no API key and no cost.
**Label first, before reading the published report, the specs, the code, or anything under `data/`**: they all contain the labels or the definitions the models were given, and seeing them first defeats the check.

```sh
uv sync
uv run python -m bakeoff label-page --set edits     # or --set unseen if you have followed the project's review
# open the printed file in a browser, answer every message, then save your answers to a file
uv run python -m bakeoff label-import ~/Downloads/labels-edits.json --name your-handle
uv run python -m bakeoff label-second-look --name your-handle
# open the printed file, mark each disagreement, save it
uv run python -m bakeoff label-import-second ~/Downloads/second-look.json --name your-handle
uv run python -m bakeoff report                     # your labeling appears in the full report
```

The page shows only the messages and plain questions, with no definitions and no labels, and asks once what you had already read; that answer is kept with your labels.
The `edits` set has the 72 messages whose labels were edited in review (plus controls), so a fresh reader can test those edits directly.
To have your labeling in the published report, open a pull request with your two files under `data/human/`; the handle you choose is published.

## What stays local

| Path | Committed | Why |
|---|---|---|
| `data/dataset.jsonl` | yes | the frozen, fictional dataset anyone can rerun |
| `reports/public/` | yes | figures that can be published; withheld ones are listed in each report |
| `results/` | no | raw vendor responses |
| `reports/full/` | no | every figure, including withheld ones |
| `prices.local.json` | no | optional local rates, such as Jev's |

Figures withheld from the public edition are listed in [`withheld.json`](withheld.json), fixed before a run.
