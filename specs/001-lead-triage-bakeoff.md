# 001: Lead triage classifier bakeoff

**Status**: Implemented
**Created**: 2026-10-07

## Problem

Three classifier options now exist for routing inbound real estate leads: Jev, OpenAI's Decisions API, and Claude.
Each one counts tokens with its own tokenizer, charges differently, and takes questions in a different shape, so their published numbers cannot be compared directly.
Without a head-to-head on the same messages, choosing one for production lead triage comes down to vendor claims.

## Scope

**In**:
- A frozen synthetic dataset of lead messages with ground-truth answers.
- One command that runs every variant over that dataset and writes one comparison report, in a full local edition and a publishable edition (B11).
- Accuracy, invalid-answer rate, coverage, vendor-native tokens, cost, and latency per variant.
- A spend cap per variant.

**Out**:
- Prompt tuning for any provider, since Principle 1 forbids per-vendor tuning and tuning for all of them is its own exercise.
- Calibration analysis of Jev's probabilities. Only the top label is scored.
- Production integration, routing, or any live traffic.
- Real customer or company messages (Principle 4).
- Throughput or concurrency benchmarking. Latency is measured per call, not under load.

## Behavior

**B1. Questions.** Every message is classified on four questions, each with a fixed label set:

| Question | Labels |
|---|---|
| intent | buy, sell, rent, valuation, general question, not a lead |
| timeline | under 3 months, 3 to 12 months, over 12 months, unknown |
| wants contact | yes, no |
| urgency | high, normal |

Each question's text defines its terms, so a model never has to guess a reading only the dataset author knows:
- timeline counts when the move or transaction (buy, sell, rent, move) happens, not when an answer or a valuation is needed, and is unknown when the message gives no time for it;
- wants_contact is yes for a request for a reply addressed to the sender, by call, text, email, or a meeting, and a post on a website or portal does not count;
- urgency is high only when the message names a deadline or forced move within about four weeks, and normal otherwise, including for a general wish for speed with no date.

The question text and label wording are identical for every variant.
A message that mentions two intents has both as acceptable answers in its ground truth, and either one scores as correct.
Every other question has exactly one correct label.

**B2. Dataset.** 200 synthetic messages, each with a ground-truth label for all four questions.
It covers every label of every question at least 5 times and includes hard cases: messages that mention two intents, messages with no stated timeline, and messages that are not leads at all.
The dataset is frozen before the first scored run and is identical for every variant.
The person running the bakeoff can review it before it is frozen.
Every personal detail in it is unmistakably fictional: invented names, phone numbers only in the 555-0100 to 555-0199 range reserved for fiction, email addresses only at `example.com`, and street addresses on invented streets.
A check run before freezing rejects any message with a phone number outside that range or an email at any other domain.

**B3. Variants.** One run covers six variants:

| Variant | Model (OpenRouter id) | Request shape |
|---|---|---|
| jev | Jev, `typesafe/jev-1.13` | all four questions in one request |
| decisions-batched | OpenAI Decisions, `openai/gpt-6-luna-decisions` | all four questions in one request |
| decisions-per-q | OpenAI Decisions, `openai/gpt-6-luna-decisions` | one question per request |
| sonnet-batched | Claude Sonnet 5.5, `anthropic/claude-sonnet-5.5` | all four questions in one request |
| haiku-per-q | Claude Haiku 4.5, `anthropic/claude-haiku-4.5` | one question per request |
| haiku-batched | Claude Haiku 4.5, `anthropic/claude-haiku-4.5` | all four questions in one request |

Every variant runs through OpenRouter with one API key, served only by the model's own vendor, with no fallback to another provider or model.
Jev and Decisions receive the same request shape through the same endpoint.

**B4. One command.** A single command runs every variant over the full dataset and produces the report, with no input needed during the run.
A variant can also be run on its own, and the report can be rebuilt from saved results without calling any provider again.

**B5. Call record.** Every call, including retries and failures, is saved with: variant, message, the full request as sent (minus auth), attempt number, outcome (answered, invalid, refused, failed), returned labels, latency, the provider that served it, and the token counts and cost exactly as the billing service returned them, or unknown if it returned none.
No API key or auth header appears in any record.
Call records stay on the machine that ran the bakeoff and are never committed, since they hold full vendor responses; the committed dataset and code are enough for anyone to rerun it with their own keys.

**B6. Scoring.** Per variant and per question: accuracy against ground truth, and the rate of invalid or refused answers.
An invalid or refused answer is scored as wrong.
A message is unclassified only when some question has no completed response after its retries.

**B7. Cost and latency.** Per variant, per classified message: input tokens, output tokens, reasoning tokens shown separately where the vendor bills them, and any other token category the vendor reports, all in that vendor's own units; cost in US dollars, summed from the cost the billing service reported per call, or from published prices only where it reported none; latency at p50 and p95.
A message's latency is the total time a caller would wait for all its answers: every attempt counts, failed ones included, and per-question latencies are summed.
The report states next to the token table that tokens are not comparable across vendors.
A variant with any unknown-token call shows its cost as a lower bound, with the count of such calls.
In any cost ranking a lower-bound variant is marked as such, and if one ranks cheapest, the report says the cheapest variant is unconfirmed.
A variant with no known price shows cost as unknown and is excluded from any cost ranking, with the reason stated.

**B8. Spend cap.** Each variant stops once its estimated spend would pass its cap, $2 by default and settable per run.
A variant with no known price stops after a fixed number of calls instead, set before the run and never below what the full dataset needs with every retry used (three times its first-attempt calls), so the cap alone cannot make it partial.
A stopped variant is reported as partial.

**B9. Coverage.** A variant that never reached its provider is reported as not run.
A variant that classified fewer than all 200 messages is reported with its coverage and left out of the head-to-head ranking.

**B10. Report.** A local HTML report with: the head-to-head table (accuracy with a 95% confidence interval, invalid rate, cost per message, p50 and p95 latency) for complete variants; for each complete variant, a 95% paired confidence interval on its intent accuracy difference from the best variant, computed over the same messages; per-question accuracy; vendor-native tokens per message; partial and not-run variants listed separately with the reason; and the run date, dataset version, billing service, and the model identifiers and serving providers each response reported.

**B11. Two editions.** Every report is produced in two editions from the same results.
The full edition contains everything and is never committed.
The public edition omits each figure that Principle 6 rules out, and has a Withheld section listing, per omitted figure, which variant it belongs to and the reason.
The current list of withheld figures is set before the run, not decided after seeing results.
A variant whose cost is withheld is left out of every cost ranking in the public edition, and each such ranking states which variants it excludes, so the public edition never implies a winner it cannot show.

## Acceptance

- **B1.** Given any two variants' saved requests for the same message, when their question and label text are compared, then they match word for word.
- **B2.** Given the frozen dataset, when its labels are counted, then there are 200 messages and every label of every question appears at least 5 times.
- **B4.** Given a `.env` with an OpenRouter key, when the single command runs, then six variants' results and both report editions exist without any prompt during the run.
- **B11.** Given a run where Jev cost is on the withheld list, when both editions render, then the full edition shows Jev cost, the public edition does not, and its Withheld section names Jev cost and the reason.
- **B11.** Given Jev cost is withheld, when the public edition renders, then Jev appears in no cost ranking, not even as a position with its number blanked, and each cost ranking names Jev as excluded.
- **B11.** Given a fresh clone of the repository after a run is committed, when it is searched, then no full-edition report or raw results file is present.
- **B2.** Given a candidate dataset containing one message with the phone number 206-555-0247 (outside the reserved 0100 to 0199 block) or the email jane@gmail.com, when the pre-freeze check runs, then that message is rejected and the dataset is not frozen.
- **B4.** Given saved results and no network access, when the report is rebuilt, then it is produced with the same numbers and no provider is called.
- **B5.** Given a run where one call timed out and its retry succeeded, when the records are read, then both attempts are present, the first with tokens unknown.
- **B5.** Given any finished run, when every record and the report are searched for each key in `.env`, then none is found.
- **B6.** Given a variant that returned a label outside the allowed set for one question, when it is scored, then that answer is wrong, the message still counts as classified, and the invalid rate is above zero.
- **B7.** Given a variant with one unknown-token call, when the report renders, then its cost is labeled as a lower bound and shows a count of 1.
- **B8.** Given a cap set below the default, low enough to trigger on a test dataset, when that variant runs, then it stops before the estimated spend passes the cap and is reported as partial.
- **B9.** Given an invalid key, when the run finishes, then each variant is listed as not run with the error, and none of them blocks or crashes another.
- **B9.** Given a variant that classified 150 of 200 messages, when the report renders, then it shows 75% coverage and does not appear in the head-to-head ranking.

## Success criteria

- A full run of all six variants over 200 messages finishes in under 45 minutes, and the three Claude variants together cost under $2, at the prices known at run time.
- Every number in the head-to-head table can be traced to saved call records.
- From the report alone, a reader can answer: which complete, priced variant is cheapest per message among those whose paired interval against the best intent accuracy includes zero, and how its p95 latency compares.

## Assumptions

- Decisions runs in both shapes, like Claude, since OpenRouter's Decisions endpoint takes several questions in one request.
- Jev and Decisions go through OpenRouter's alpha Decisions endpoint, which takes a state and a set of typed questions. OpenRouter documents it with a Jev example only; a smoke call on 2026-10-07 confirmed it accepts `openai/gpt-6-luna-decisions` and returns choices, token counts and cost.
- Claude variants go through OpenRouter's chat completions with a strict JSON schema restricted to the allowed labels, and the lowest reasoning effort OpenRouter accepts per model: none for Haiku 4.5, minimal for Sonnet 5.5, which rejects none as mandatory reasoning (smoke call, 2026-10-07; minimal returned 0 reasoning tokens).
- Jev runs only in its batched shape, since sending all of a message's questions in one request is how it is designed to be used. A per-question Jev variant is easy to add if wanted.
- Claude variants send the B1 question and labels inside one shared instruction, identical across all three Claude variants, and limited to that text plus the required output format: no examples, tie-break rules, or guidance the other providers do not get. Jev and Decisions take question and labels as structured fields, so they need no instruction. Principle 1 is met by the shared question and label text, not by identical prompts, which the APIs do not allow.
- Each variant gets the same retry rule: up to 2 retries on timeouts, 5xx errors and rate limits, with no retry after a completed answer, invalid or not.
- Sonnet 5.5 and Haiku 4.5 are the Claude models, as agreed. Sonnet runs batched only, as the accuracy ceiling Haiku is judged against; a per-question Sonnet variant was dropped on 2026-10-07 because it was about $1 of each run's roughly $1.30 Sonnet spend (smoke-call costs) and Haiku per-question already measures the effect of splitting questions. Jev and Decisions use whatever model the vendor serves.
- Claude variants run with the least reasoning each model allows, since reasoning is billed as output and a four-way label choice should not need it. The setting is recorded in the report. Reasoning tokens are reported per variant, so any Sonnet reasoning at minimal effort shows up in the report.
- Expected Claude spend per full run is about $1.15 (Sonnet 5.5 at $2 / $10 and Haiku 4.5 at $1 / $5 per million input / output tokens, list prices as of 2026-09-25; tokens per call estimated, not measured). The $2 cap is a guard against runaway retries, not a budget.
- Cost comes from the `usage.cost` OpenRouter returns with each call, which its usage-accounting docs say every response carries. The price list below is the fallback for calls that carry no cost, and for the spend cap's projection before the first call.
- Prices come from each vendor's published rates on the run date, recorded in the report. Decisions API is $0.10 per million input tokens with no output charge (OpenAI's Decisions guide, read 2026-10-07), so it gets a dollar cap like the rest. The same guide says regional processing premiums and long-context multipliers apply on top. The run uses no regional processing and inputs of a few hundred tokens (the long-context threshold itself was not checked), so the base rate should hold, but the rate actually billed is confirmed at run time and recorded, not assumed. The call-count cap in B8 remains for any variant whose price is not known at run time.
- The dataset is generated with Claude Opus 5.5 through OpenRouter, which is not a variant under test. Labels are chosen first and a message is then written to match them, and the person running the bakeoff spot-checks it before freezing.
- Calls run one at a time within a variant, so latency is not distorted by self-inflicted rate limiting, and the six variants run at the same time as each other. The 45-minute target rests on this: the slowest variant makes 800 first-attempt calls, about 2.25 s each at 30 minutes, which leaves no room for timeouts.

## Risks and open questions

- **Two moving targets.** OpenRouter's Decisions endpoint is alpha, and OpenAI's Decisions API is in public beta. Either may change shape before a rerun.
- **Decisions API is in public beta.** It went public on 2026-10-06 with a guide and an API reference (`POST /v1/decisions`, a `usage` object with input and output tokens). OpenAI says GA is coming in weeks, so the shape may change before then.
- **Generator bias.** If Claude generates the dataset, its wording may favor Claude variants. Mitigations: label-first generation and the spot-check. A stronger option, using a non-Claude model to generate or splitting generation across vendors, is open.
- **Small sample.** At 200 messages and about 85% accuracy, one variant's 95% interval is about ±5 points, so small accuracy gaps are noise. B10's paired intervals make that visible rather than hiding it, but may still be too wide to separate variants; the fix then is a larger dataset, not a looser reading.
- **Token counts come from OpenRouter.** Its usage-accounting docs say counts use each model's native tokenizer, and its Decisions schema makes input and output tokens required. Whether its counts for Claude equal Anthropic's own is unverified.
- **Latency includes a gateway hop.** Every variant pays it, so comparisons between variants are fair, but absolute latencies are higher than calling each vendor directly.
- **The repository will be public, and Jev's contract restricts disclosure.** TypeSafe's Master Customer Agreement (last updated 2026-09-23) has no benchmark-publication ban in its current text, but its confidentiality section (14.1) classes TypeSafe's documentation, pricing, and the agreement's own terms as confidential even where they are publicly available. Publishing Jev's cost per message, or quoting its docs or contract, may conflict with that, which is why this spec paraphrases rather than quotes them. OpenAI's beta terms could not be read (openai.com returned 403). Calling Jev through OpenRouter makes this an OpenRouter account, not a direct TypeSafe one, which may change whether that agreement applies at all; OpenRouter's own terms have not been read either. Neither reading is legal advice. Under Principle 6, until this is settled, Jev cost figures stay out of the committed report.
- **Prices drift.** All three vendors change prices. Recording the rates used per run makes old reports interpretable but not comparable to new ones.
