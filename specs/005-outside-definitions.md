# 005: Definitions written outside Anthropic

**Status**: Implemented
**Created**: 2026-10-07

## Problem

Every model in the bakeoff is told how to read the four questions through definitions written in a Claude session, and the frozen labels were edited to fit those definitions.
If that wording matches how Claude models interpret language, the Claude variants are helped twice: in the prompt they answer and in the labels they are scored against.
Spec 004's outside rater could not detect this, because it was given the same definitions.
Nothing so far tests whether the ranking depends on who wrote the definitions.

## Scope

**In**:
- Definitions for the four questions written by a model whose vendor has no variant, from the task alone, without seeing the current definitions or the dataset.
- A second, complete label set for all 200 messages, made blind by that same outside model under its own definitions.
- A full run of all six variants with the outside definitions as their question text.
- The ranking under the outside definitions and labels, shown in the published report beside the current ranking, with a plain statement of what changed.

**Out**:
- Replacing the current definitions, labels, or published ranking. The outside version is a sensitivity check beside them.
- Definitions written by the owner. That remains the stronger test and can follow.
- Changing the questions themselves, their names, or their allowed labels. Only the definitions that explain them change. Those names and label words came from the same Claude-assisted drafting, so that shared starting point stays untested here; keeping it is what lets the two conditions be compared.

## Behavior

**B1. Outside definitions.** A model from a vendor with no variant writes one definition per question.
It is given the task (triaging inbound real estate leads for an agent), each question's name and allowed labels, and an instruction to state when each label applies, including borderline cases, without favoring any reading.
It is never given the current definitions, the label-change log, or any message from the dataset.
The owner approves the definitions as written or rejects them; any edit the owner makes is recorded word for word beside the original.

**B2. Outside labels.** The same outside model labels all 200 messages blind under its own definitions, in the same way as spec 004: message text and questions only, no label of any kind, one pass, recorded with model, endpoint, settings, and date.
Intent may take two labels when a message clearly asks for two things, as the frozen labels allow, so both conditions give the same "either intent" credit; every other question takes one.
The result is a second label set kept beside the frozen dataset, which does not change.

**B3. A run under the outside definitions.** All six variants run over the frozen messages with the outside definitions as their question text, through the same harness and under the same rules as every run.
That run records its own question-text version, different from the current one, and is scored against the outside labels.

**B4. Does the ranking depend on the definitions?** Two things change between the current setup and the outside one, the definitions the variants answer under and the labels they are scored against, so the report separates them with three rankings:
the current run scored against the current labels (today's report); the current run scored against the outside labels, which needs no new calls and shows the effect of the labels alone; and the outside run scored against the outside labels, which, compared with the middle one, shows the effect of the definitions alone.
For each complete variant the report shows its all-four share, rank, and tier under all three, and states plainly whether rank 1 and each tier are the same between each adjacent pair.
It also shows each vendor's variants' change in rank and all-four share, so a shift toward or away from one vendor is visible without a reader computing it.
It shows each variant's accuracy per question under the current and the outside setup, so a reader can see which question drives a change.
It applies no threshold; it shows what changed.

**B5. Disclosed.** The report names the model that wrote the definitions and labels, says it is one model's single pass and not ground truth, and shows both sets of definitions in full so a reader can compare them.

## Acceptance

- **B1.** Given the request that asks for definitions, when it is inspected, then it contains the task, the four question names, and their allowed labels, and contains no current definition text, no label-log content, and no dataset message.
- **B1.** Given owner edits to the outside definitions, when they are recorded, then both the original and the edited text are kept.
- **B2.** Given the outside label set, when it is checked, then it covers all 200 frozen messages and the frozen dataset's hash is unchanged.
- **B3.** Given the outside run, when its record is read, then its question-text version differs from the current one and all six variants were run with the outside definitions.
- **B4.** Given the three rankings, when the report renders, then each complete variant shows rank, tier, and all-four share under all three, with a plain statement for each adjacent pair (labels alone, then definitions alone) of whether rank 1 and the tiers match, and a per-vendor change for each.
- **B4.** Given the current run and the outside labels, when the middle ranking is computed, then no provider is called.
- **B2.** Given a message the outside model labels with two intents, when a variant answers either one, then it is scored correct, as under the frozen labels.
- **B5.** Given the report, when it renders, then it shows both definition sets in full and names the outside model.

## Success criteria

- A reader can see whether the ranking, and in particular the Claude variants' position, changes when the definitions come from outside Anthropic.
- The whole check costs under $5 at the rates recorded at run time.

## Assumptions

- The outside model is `google/gemini-3.1-pro-preview` on `google-vertex/global`, as in spec 004, under the same Google terms the owner accepted.
- The outside labeler may give two intents, so the "either intent" credit exists in both conditions. Without that, variants would lose it unequally: on the 11 two-intent messages Gemini labeled in spec 004, scoring against its single pick cost the variants between 1 and 4 messages each, which would look like a definitions effect.
- Expected cost, estimated, not measured: drafting definitions about $0.05; labeling 200 messages about $0.80 at spec 004's measured $0.30 for 72; one full run about $0.90 at the 2026-10-07 run's measured $0.88. Each step keeps its own spend cap.
- The current run, definitions, labels, ranking, and conclusions stay as published; the outside comparison is added beside them. (Spec 006 later replaced the published run and its conclusions with a run that defines intent.)

## Risks and open questions

- **One outside model swaps in its own leanings.** Gemini's wording may suit Gemini-like readers, and none of the variants is a Gemini model, so this tests "Claude-written versus not Claude-written", not "biased versus neutral". The owner writing definitions is the stronger test.
- **The same model writes definitions and labels.** That keeps the outside condition consistent, as the current one is, but it means the outside labels inherit the outside definitions' quirks. That mirrors the current setup and is the point of the comparison.
- **Different label granularity.** The outside labeler decides for itself which messages have two intents, so its two-intent set will not match the frozen one. The labels-alone comparison in B4 isolates that, but absolute shares are still not comparable across label sets; ranks are.
- **Owner approval could pull the definitions back toward the current ones.** B1 records any edit word for word, so the extent of that pull is visible.
