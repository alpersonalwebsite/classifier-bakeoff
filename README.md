# Classifier bakeoff

Compares three classifiers on the same synthetic lead-triage task: Jev (TypeSafe), OpenAI's Decisions API, and Claude.
All three run through [OpenRouter](https://openrouter.ai) with one key, each pinned to its own vendor with no fallback.
It measures accuracy, invalid answers, tokens as OpenRouter reports them, cost, and latency per message.

The rules every run follows are in [`constitution.md`](constitution.md), and the behavior is specified in [`specs/`](specs/), starting with [`specs/001-lead-triage-bakeoff.md`](specs/001-lead-triage-bakeoff.md) and amended or extended by 002 to 007.

## Results

If you might [check the labels yourself](#check-the-labels-yourself), do that before opening the report: it shows the labels.

The latest public report is at https://alpersonalwebsite.github.io/classifier-bakeoff/reports/public/20261007T235443Z-da1571.html, from a run on 2026-10-07 over the frozen dataset with question text `sha256:6cbd46e11dc7a47c`.
Its source is [`reports/public/20261007T235443Z-da1571.html`](reports/public/20261007T235443Z-da1571.html), and its conclusions are in [`reports/conclusions/20261007T235443Z-da1571.md`](reports/conclusions/20261007T235443Z-da1571.md).

## Setup

Requires Python 3.13 or newer and [uv](https://docs.astral.sh/uv/getting-started/installation/).

```sh
uv sync
cp .env.example .env   # then set OPENROUTER_API_KEY; .env is gitignored
```

Cost comes from the `usage.cost` OpenRouter returns with every call.
`prices.json` is only a fallback and the spend cap's first projection. Jev has no fallback rate there; its cost comes from `usage.cost` like every other variant's.

## Use

```sh
uv run pytest                          # offline tests, no key needed
uv run python -m bakeoff run --variant haiku-batched --limit 5   # smoke test, costs cents
uv run python -m bakeoff run           # all six variants, then both reports
uv run python -m bakeoff report        # rebuild reports from the newest run under the current definitions, no API calls
uv run python -m bakeoff report results/<run_id>   # or from a named one
```

`run` and `report` write into `results/` and `reports/`; `report` needs a run of your own, since `results/` is not committed.

The dataset is already frozen in `data/dataset.jsonl`, so you do not need these. They are how it was made, once:

```sh
uv run python -m bakeoff generate      # write data/candidate.jsonl (Claude Opus 5.5, costs money)
uv run python -m bakeoff check         # the fictional-details and label-coverage checks on the candidate
uv run python -m bakeoff freeze        # freeze the reviewed candidate; refuses if data/dataset.jsonl exists
```

## Check the labels yourself

You can test the labels with your own reading, blind, in about 40 minutes, with no API key and no cost.
**Label first, before reading the published report, the specs, the code, or anything under `data/`**: they all contain the labels or the definitions the models were given, and seeing them first defeats the check.

You need only the [Setup](#setup) prerequisites (Python 3.13+ and uv); skip the `.env` step.

```sh
uv sync
uv run python -m bakeoff label-page --set edits     # or --set unseen if you have followed the project's review
# open the printed file in a browser, answer every message, then save your answers
uv run python -m bakeoff label-import ~/Downloads/labels-edits.json --name your-handle
uv run python -m bakeoff label-second-look --name your-handle
# open the printed file, mark each disagreement, save it
uv run python -m bakeoff label-import-second ~/Downloads/second-look.json --name your-handle
uv run python -m bakeoff label-summary --name your-handle   # your results
```

- **The page** shows only the messages and plain questions, with no definitions and no labels, and asks once what you had already read; that answer is kept with your labels.
- **Progress** is kept in the browser, so you can close the page and resume. Use a normal window, not a private one, which discards it on close, and one browser profile per labeler.
- **Saving** downloads `labels-edits.json` (or `labels-unseen.json`) and later `second-look.json` to your browser's download folder, usually `~/Downloads`; adjust the path if yours differs.
- **The sets.** `edits` has the 42 messages whose labels were edited in review plus 30 controls, 72 in all, so a fresh reader can test those edits directly. `unseen` has 60 messages the owner did not see judged.
- **Your results.** `label-summary` shows, per question, how often you matched the frozen labels; on the `edits` set, how often you chose the edited label, the original, or neither, beside the outside rater; and your second-look counts.
- **The ranking check** (does the ranking hold under your labels) needs a run's raw responses, which are not committed. Open a pull request with your two files under `data/human/` (`your-handle.json` and `your-handle-second-look.json`), and once it is merged and the published report is rebuilt, your labeling and its ranking appear there. The handle you choose is published.

## What stays local

| Path | Committed | Why |
|---|---|---|
| `data/dataset.jsonl` | yes | the frozen, fictional dataset anyone can rerun |
| `reports/public/` | yes | figures that can be published; withheld ones are listed in each report |
| `results/` | no | raw vendor responses |
| `reports/full/` | no | every figure, including withheld ones |
| `prices.local.json` | no | optional local fallback rates |

Figures withheld from the public edition are listed in [`withheld.json`](withheld.json), fixed before a run.
