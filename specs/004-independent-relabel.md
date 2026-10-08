# 004: An independent relabeling of the reviewed messages

**Status**: Implemented
**Created**: 2026-10-07

## Problem

Before the dataset was frozen, 46 labels on 42 messages were edited, and Claude Opus 5.5 both proposed the edits and critiqued the definitions behind them.
Three of the six variants are Claude models, so if those edits leaned toward how Claude reads a message, the Claude variants would score higher for it.
Nothing so far can tell.
Spec 003's table shows how much each result depends on the edits, but every variant was given the revised definitions, so it measures how well each model follows that wording, not whether the edits were fair.
No reviewer outside Anthropic's models has checked these labels.

## Scope

**In**:
- One blind labeling of the 42 messages with an edited label and a control set of unedited ones, by a model from a vendor with no variant under test.
- Measuring how often that rater agrees with the frozen labels versus the labels as generated, against its agreement on the controls.
- Recomputing the ranking with the rater's labels in place of the frozen ones on the messages it labeled, and reporting whether rank 1 and the tiers hold.
- Showing the result in every report, and naming the rater in the disclosure.

**Out**:
- Changing the frozen dataset. The rater's labels are a second opinion beside it, not a replacement.
- A human relabeling. It would be a stronger test and can follow; this spec is the model check the owner chose first.
- Relabeling all 200 messages. The question is about the review's edits, and the controls give the baseline.
- Whether the definitions themselves lean toward Claude. The rater gets the same Claude-written definitions, and the frozen labels were edited to fit them, so agreement with the frozen labels shows the edits apply those definitions consistently, not that the definitions are neutral. Testing that needs definitions written independently.

## Behavior

**B1. A blind set.** The rater sees the 42 messages carrying the 46 edited labels and 30 messages with no edited label, chosen reproducibly and shuffled together, under identifiers that do not reveal which are which.
For each it gets the message text and the four questions exactly as every variant gets them, including their definitions.
It never sees a label: not the frozen one, not the generated one, and not any variant's answer.

**B2. An outside rater.** The rater is a model from a vendor with no variant in the run.
For this spec it is `google/gemini-3.1-pro-preview` through OpenRouter, pinned to Google's standard global Vertex endpoint (`google-vertex/global`, not its flex or priority tiers) with no fallback, so one known set of Google terms and one price apply, and the endpoint that actually served each call is recorded.
It answers every question with exactly one allowed label in a single pass, with reasoning effort set low and a spend cap of $3 for the pass, and its labels, the model and endpoint it reported, those settings, and the date are committed beside the dataset.
Its raw responses stay local with the other call records.
If it fails to answer a message after retries, that message is left out of every measure below and the count of such messages is shown.

**B3. Did the edits hold up?** For each edited label, the rater counts as agreeing with the frozen label when its answer is one of the frozen labels, and with the generated label when its answer is one of those.
The report shows these shares per question (urgency, wants_contact, timeline, intent), each as a count and a share: agreeing with the frozen labels, agreeing with the generated labels, and agreeing with neither.
Beside each question it shows the rater's agreement with the frozen labels on that same question across the controls, so each question's edits are compared with that question's baseline. The 46 edits are mostly urgency (28) and wants_contact (14), and a pooled baseline would be pulled up by easier questions.

**B4. Does the ranking hold?** The ranking is recomputed under spec 003's rule with the rater's answer in place of each of the 46 edited labels only, and every other label as frozen, including the controls and both intents of every two-intent message.
That isolates the question this spec asks, whether the edits moved the ranking, from the rater's disagreements with labels nobody edited.
The report shows, for each complete variant, its all-four share and rank under the frozen labels and under the rater's labels, and states plainly whether rank 1 and each variant's tier are the same.
It does not apply any threshold to call the review biased or not; it shows what changed.

**B5. Disclosed in every report.** Every report built after the relabeling shows B3 and B4 in their own section, names the rater model and its vendor, and says it is one model's single pass, not a ground truth.
The label-review disclosure from spec 003 adds that this independent check was made and by which model.
Until a relabeling exists, the report says none has been made.

**B6. Replicable, as Google's terms require.** Everything needed to repeat the relabeling is published with its results: the rater model and endpoint, the exact request sent, its settings, how the blind set was chosen, and the dataset.

## Acceptance

- **B1.** Given the frozen dataset and the label-change log, when the blind set is built, then it has the 42 messages with an edited label and 30 without, the same set on every build, and no field of what the rater is sent contains a label or reveals which messages were edited.
- **B1.** Given the request sent for any message, when it is compared with a variant's request for that message, then the question text and label wording match word for word.
- **B2.** Given the rater's vendor, when it is compared with the vendors of the variants in the run, then it is none of them.
- **B2.** Given a message the rater never answered, when the measures are computed, then that message is excluded and counted.
- **B3.** Given an edited label where the rater picks the frozen label, one where it picks the generated label, and one where it picks neither, when agreement is computed, then each counts toward its own share.
- **B3.** Given a two-intent message where the rater picks either intent, when agreement is computed, then it agrees with that label set.
- **B3.** Given rater answers on the controls, when the baseline is computed, then it is computed per question and each edited question is shown beside its own baseline.
- **B4.** Given rater labels that differ from the frozen labels on edited and on control labels, when the ranking is recomputed, then only the edited labels change, control labels and two-intent sets stay as frozen, and the report shows both rankings with a plain statement of whether rank 1 and the tiers match.
- **B5.** Given a report built with a relabeling on record, when it renders, then it names the rater model and its vendor and calls it a single pass rather than ground truth.
- **B5.** Given no relabeling on record, when a report renders, then it says no independent check has been made.
- **B6.** Given the published relabeling, when someone has the repository and an OpenRouter key, then they can rerun it with the recorded model, endpoint, request, and blind-set seed.

## Success criteria

- A reader of the report can see, for the 46 edited labels, whether an outside model sided with the edits or with the original labels, and how that compares with its agreement on untouched messages.
- A reader can see whether the ranking survives an outside model's labels.
- The relabeling costs under $3 at the rates recorded at run time, and the spend cap stops it before then.

## Assumptions

- 30 controls: enough to estimate a baseline agreement rate, small enough that the set stays mostly about the edits. Chosen with a fixed seed from messages with no edited label.
- The rater gets the same question text as the variants, definitions included, so it judges the messages by the rules the labels claim to follow. Giving it different wording would test the wording, not the edits.
- The rater's single answer counts against a two-intent ground truth the same way a variant's does: matching either label agrees.
- Its settings are the provider defaults apart from structured output and reasoning effort, which is set low to bound cost. That is a cost setting, not one tuned to the answers, and it is recorded and published (B6).
- Expected cost is about $1 to $3: 72 short messages, one pass, at the rates OpenRouter lists for this endpoint on 2026-10-07 ($2.00 per million input tokens, $12.00 per million output and reasoning). A review projection for 72 messages puts it at $1.05 with 1,000 reasoning tokens per message and $2.77 with 3,000, so how much Gemini reasons decides it, which is why reasoning is set low and capped. Not measured until the run.

## Risks and open questions

- **One model is one opinion.** Gemini can be wrong in its own direction, and agreement with it is not correctness. The report says so (B5), and a human relabeling remains the stronger test.
- **Gemini is a preview model.** Its behavior may change, so the rater's reported model identifier and the date are recorded with its labels.
- **Small numbers.** 46 edited labels and 30 control messages give wide uncertainty on the agreement shares. The report shows counts, not only percentages, so a reader can judge the size.
- **Google's benchmarking terms.** Google Cloud's Service Terms (section 7, last modified 2026-09-30) allow publishing benchmark results of its services only if the disclosure includes everything needed to replicate them and the customer lets Google benchmark the customer's public products. OpenRouter's terms bind users to each provider's terms, so this applies through OpenRouter. Whether a labeling pass is a benchmark of Gemini is arguable; publishing its agreement rates looks like one, so B6 meets the replication condition, and the second condition is the owner's to accept. This is a reading of the terms, not legal advice. Google AI Studio's endpoint has separate terms that were not read, which is why B2 pins Vertex.
- **Mixed vendors in the comparison.** Decisions is an OpenAI model and Jev a TypeSafe one; Gemini is from neither, nor from Anthropic. It is the only vendor considered that is independent of all three.
