# 003: A vendor-neutral ranking, and the report's own bias checks

**Status**: Implemented
**Amends**: spec 001 B10 (section order and the paired reference) and its third success criterion, which the ranking replaces
**Created**: 2026-10-07

## Problem

The report does not say which variant is best, and its structure leans toward Claude even where its numbers do not.
The head-to-head table is ordered by intent accuracy, so Sonnet sits on top; the paired comparison measures every variant against the top intent score, which is Sonnet's; and nothing in the report ranks the variants on the whole triage task, the four questions together.
A reader skimming the report can come away with a winner the report's own recommendation does not name.
The report also says nothing about how much its results depend on the labels revised in review, which were revised with Claude's help.

## Scope

**In**:
- A single ranking of the complete variants under one stated rule, with the winner named at the top of the report.
- Confidence intervals for the share of messages with all four answers right, which the ranking needs to decide ties.
- Report sections that order and compare by the ranking rather than by intent accuracy.
- A table, shown in every report, of how much each variant's results depend on the pre-freeze label edits.
- Rewriting the 2026-10-07 conclusions to lead with the ranking.

**Out**:
- A second dataset written by a non-Claude model. It is the only real test of generator bias and is its own spec.
- An independent relabeling of the 46 edited labels (on 42 messages), by the owner or by a non-Claude model. It is the only real test of whether the review was biased, and is its own change.
- Changing what the variants are sent. Prompt shape is fixed by the APIs and spec 001.
- Weighting the four questions differently. Every question counts the same.

## Behavior

**B1. One ranking rule.** Complete variants are ranked by the share of messages with all four answers right.
Two variants are tied on accuracy when the 95% paired interval of their difference on that share includes zero.
Ranking works in tiers: the highest-scoring remaining variant leads a tier, every remaining variant tied with it joins that tier, and the next tier starts from what is left.
Within a tier, variants are ordered by cost per message, cheapest first, then by p50 latency.
Variants that gave identical answers to every question share one rank, shown as one result with each of their costs and latencies, so two request shapes of one model never read as two models ahead of a third.
Ranks are numbered from 1 without gaps, so the variant after a shared rank 1 is rank 2.

**B2. Costs that decide an order.** A variant with no known cost ranks after the priced variants in its tier.
When a variant whose cost is a lower bound is ranked above another on cost, the report says that order is unconfirmed, because its true cost could be higher; a lower-bound variant ranked below an exact one is settled, since a lower bound can only rise. This matches spec 001 B7.

**B3. The winner, first.** The report names the rank 1 variant near the top, with the ranking rule in one sentence, before any table.

**B4. Everything ordered by rank.** The head-to-head table is ordered by rank and shows each variant's rank and tier, with the all-four share and its 95% interval.
The paired comparison measures every complete variant against the rank 1 variant, on all four right and on intent.
No section is ordered by a single question's accuracy.

**B5. Vendor-blind.** The ranking and every generated sentence come from the measured figures alone.
Renaming variants, or swapping which vendor each belongs to, changes no rank, no tier, and no generated text other than the names themselves.
Generated text never characterizes a vendor or model ("ceiling", "leader", "flagship"); it states ranks and figures.

**B6. Dependence on the label edits.** Every report shows, for each complete variant, its all-four share under the labels as generated and under the labels as frozen, and the change between them, described as how much that variant's result depends on the review's edits.
The report says plainly that this does not test whether the review was biased: every variant was given the revised definitions, so the change mostly measures how well each model follows that wording on the edited messages, and only an independent relabeling of those messages can test the review itself.
The pre-review labels come from the committed record of label changes, not from a separate copy.
Beside the table, the report states who proposed the edits and who approved them, naming any model that assisted, taken from the dataset's own record; any later independent relabeling is disclosed the same way, naming its model.

**B7. Conclusions follow the ranking.** The 2026-10-07 conclusions are rewritten to lead with the ranking and name rank 1 as the recommendation, and describe each variant by its rank and measured figures only.

## Acceptance

- **B1.** Given three variants at 84.5% all-four whose pairwise intervals include zero, and costs $0.000062, $0.000081, and $0.001998, when ranked, then they share tier 1 and rank 1, 2, 3 in that cost order.
- **B1.** Given two variants with identical answers on every question, when ranked, then they share one rank, shown as one result with both costs, and the next variant takes the next rank number.
- **B1.** Given a variant at 72.5% whose interval against a 73.0% variant includes zero and that costs less, when ranked, then it ranks above the 73.0% variant within their tier.
- **B1.** Given a variant whose interval against the tier leader excludes zero, when ranked, then it starts a later tier.
- **B2.** Given two tied variants where the one ranked higher has a lower-bound cost, when ranked, then the report marks that order as unconfirmed.
- **B2.** Given an exact-cost variant ranked above a lower-bound one, when ranked, then the order is not marked unconfirmed.
- **B3.** Given any complete run, when the report renders, then the rank 1 variant's name and the one-sentence rule appear before the first table.
- **B4.** Given any complete run, when the report renders, then the head-to-head rows appear in rank order and the paired comparison names the rank 1 variant as its reference.
- **B5.** Given a run, when every variant name and vendor is permuted and the report is rendered again, then ranks and tiers map to the same underlying results and the text differs only in names.
- **B5.** Given the generated report, when it is searched for "ceiling", "leader", or "flagship", then none appears.
- **B6.** Given the frozen dataset and its committed label-change record, when the report renders, then each complete variant shows its all-four share under both label sets and the change, the report states that this is not a test of reviewer bias, and it names who proposed and who approved the edits.
- **B7.** Given the rewritten conclusions, when the report builds, then every quoted figure passes spec 002's check and the first sentence names the rank 1 variant.

## Success criteria

- On the 2026-10-07 run, a reader can name the best variant from the report's first screen, and it is the variant the ranking rule puts first.
- Swapping vendors in a test run changes no rank.

## Assumptions

- All four right is the primary measure because it is the whole triage job; intent alone is shown but never decides a rank.
- Ties are decided by the data (overlapping paired intervals), not by a fixed threshold, so the rule needs no tuned number.
- Cost before latency within a tier, because the latency gaps here (sub-second to a few seconds) matter less for lead triage than a 30x cost gap. Latency still breaks exact cost ties.
- The rule was chosen after seeing the first full 2026-10-07 run, made before intent had a definition and whose report was later removed (spec 006 B3), so it is checked against alternatives rather than trusted. On that run, rank 1 is decisions-batched under B1, under intent alone with cost as the tie-break, under intent alone with latency, and under B1 with the pre-review labels (computed during drafting). The rule is fixed from here on and is not retuned to future runs.
- Applying B1 to that first run gives: 1 decisions (batched and per question, identical answers on 800 of 800 questions), 2 sonnet-batched (tier 1, all 84.5%); 3 jev, 4 haiku-per-q (tier 2); 5 haiku-batched (tier 3). Computed during drafting, to be confirmed by the implementation.
- Rescoring that run against the pre-review labels moved the two Anthropic variants 16.5 points apart (Sonnet +15.5, haiku-batched -1.0), so the edits do not move one vendor uniformly; this is a statement about dependence on the edits, not evidence for or against reviewer bias, for the reason B6 gives.

## Risks and open questions

- **Tiers are not transitive.** A can tie B and B tie C while A beats C. The tier rule assigns each variant to the first tier whose leader it ties, so the result depends on that order, which is fixed by score, then cost, then latency. Stated so it is not mistaken for a bug.
- **Disclosing AI help with the labels.** Decided by the owner on 2026-10-07: the report names the model that assisted the label review (B6), and will name the model used for any independent relabeling. This is report content about how the dataset was made; commit messages and PR descriptions keep to the repository's rule against AI attribution.
- **Small sample.** With intervals near ±5.5 points, most of today's ranks inside a tier are decided by cost, not accuracy. That is the honest reading of 200 messages, and the fix is a larger dataset, not a different rule.
