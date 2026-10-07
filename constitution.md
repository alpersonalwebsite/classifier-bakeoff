# Constitution

**Version**: 2.0.0
**Ratified**: 2026-10-07
**Last amended**: 2026-10-07

## Principles

### 1. Same inputs for every provider

Every provider classifies the same dataset against the same questions and the same allowed labels.
No provider gets a prompt, example, or label wording tuned for it alone.
Where an API forces a difference in shape (one request per question versus all questions in one request), the difference is named in the report as its own variant, not hidden inside one provider's adapter.

### 2. Measured as reported, never estimated

Token counts are the numbers the billing service returns in its own response, never estimated, converted between tokenizers, or recomputed locally.
The billing service is whoever charges for the call, a gateway such as OpenRouter or the model's own vendor, and the report names it for every variant.
Where the billing service returns a cost for the call, that cost is used, not a price-list estimate.
Every call is counted, including retries and failed calls.
A call that returns no token counts (a timeout, a 5xx) is counted as a call with tokens reported as unknown, and the number of such calls is shown beside the totals.
Tokens are never reported alone: cost and latency per classified message sit beside them, since tokenizers differ and tokens are not comparable across vendors on their own.
Whenever a provider has any call with unknown tokens, its cost is reported as a lower bound, not as its cost.
A classified message is one input where every question got a completed response, however many requests that took, so variants that split questions across requests stay comparable.
A completed response that refuses or returns a label outside the allowed set still counts: it is scored as wrong, and the rate of such answers is reported per provider.
Only a question with no completed response after its retries leaves a message unclassified.

### 3. Results come from real APIs

Every number in the report is derived from calls to the real provider API: labels and token counts directly, accuracy and cost computed from them.
Mocks and fixtures may test parsing, scoring, and report code, but a mocked run never produces a reported result.
A provider that could not be reached is reported as not run, not dropped silently and not filled in.
A provider that finished only part of the dataset is reported with its coverage shown and kept out of the head-to-head comparison, since Principle 1 requires the same dataset for every provider.

### 4. Synthetic data only

The dataset is synthetic.
No real customer, lead, or company message is sent to any provider, since every run sends the data to every outside vendor in it.

### 5. Secrets stay out of everything the repo produces

API keys never appear in source, logs, results files, or the report, and are never committed.

### 6. Nothing is committed that cannot be published

This repository is meant to be public, so everything committed to it (code, prompts, saved requests and responses, results, reports) must be publishable.
That rules out material a vendor's terms keep confidential, results a vendor's terms forbid publishing, and anything tied to an employer or client.
What cannot be published stays local and out of git, and the report says what was withheld and why.

## Governance

Amending this file bumps the version (major for removing or redefining a principle, minor for adding one, patch for wording) and updates "Last amended".
Supersede a principle in place rather than deleting it silently, a changelog entry at the bottom of this file is enough: `<date>: <what changed, and why>`.

A spec that conflicts with a principle here either changes the spec or amends this file first.
It does not do neither.

## Changelog

- 2026-10-07: 1.1.0. Added Principle 6, because the repository will be public. Principle 4 reworded to stop naming a company, since this is a personal project.
- 2026-10-07: 2.0.0 (major: Principle 2 redefined). Principle 2 now names the billing service, not the model vendor, as the source of token counts, and prefers its reported cost, so all three providers can run through one gateway (OpenRouter) with a single key. Its heading changed from "Vendor-native measurement" to match.
