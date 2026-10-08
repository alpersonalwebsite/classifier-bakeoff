# 006: Give intent a definition

**Status**: Implemented
**Created**: 2026-10-07

## Problem

Three of the four questions tell every model how to decide their labels.
Intent does not: it asks only "What does the sender of this message want?" with the list of labels.
So each model guesses what counts as "not a lead" and what to do when a message asks for two things.
The dataset was generated under a rule that settles both, and the frozen labels follow it, but the models are never shown that rule.
Spec 005 showed the cost: Jev reads vendor pitches as sellers, and under definitions that do define intent, its intent accuracy rises from 80.0% to 98.0% and rank 1 changes.
A ranking that rests on an unstated rule measures guessing as much as classifying.

## Scope

**In**:
- An intent definition stating the rule the dataset was generated under.
- A full run of all six variants with it, scored against the frozen labels.
- The report and conclusions for that run, which becomes the published one.

**Out**:
- Changing any label. The definition states the rule the labels were already made under.
- Changing the other three definitions, the question names, or the label words.
- Writing intent from scratch, or adopting the outside definition from spec 005. The owner chose the generator's rule, so the definition matches how the frozen labels were made.

## Behavior

**B1. Intent states its rule.** The intent question tells every model, in the same words, the two parts of the rule the dataset was generated under that a model cannot guess: that "not a lead" means anything that is not a real estate inquiry, with spam, vendor pitches, and wrong numbers as examples rather than a complete list, and that when a message clearly asks for two different things and neither is clearly the main one, either one is correct.
The other intent labels keep their plain meaning, as the generator's rule gives them no further definition.
Its wording is taken from the generator's description of intent, with one phrase added ("anything that is not a real estate inquiry") to make its examples explicit.

**B2. Labels unchanged.** The frozen dataset, its hash, and the label-change log are untouched.

**B3. A new run is the published one.** All six variants run with the new question text, which changes the question-text version.
That run's public report and its conclusions, approved by the owner before commit, become the published report, and the README and the Pages link point to it.
The 2026-10-07 report stays in the repository and is rebuilt from its saved results with a note naming the run that supersedes it; the rebuild also carries the existing warning that its question text differs from the current code, which is accurate.
The superseded note comes from a committed record, not a hand edit, so the rebuilt report stays reproducible (spec 002).

**B4. Earlier checks stay readable.** The spec 004 relabeling and the spec 005 outside run were made under the earlier question text, and the new report says so wherever it shows them, since their raters and variants never saw the intent definition.

**B5. Disclosed.** The report says the intent definition, like the other three, comes from the Claude-assisted drafting, here the generator's rule.

## Acceptance

- **B1.** Given the new intent question text, when it is compared with the generator's description of intent, then it states the same rule: not-a-lead as anything that is not a real estate inquiry, with examples, and the two-intent rule including that neither is clearly the main one.
- **B1.** Given the frozen messages labeled not a lead, including m176 (a newsletter confirmation) and m197 (a school PTA asking for a donation), when read against the new text, then each is covered by it.
- **B1.** Given any two variants' requests in the new run, when their intent text is compared, then it matches word for word.
- **B2.** Given the frozen dataset after this change, when its hash is checked, then it is still `sha256:8c43a059d800a559`.
- **B3.** Given the new run, when its record is read, then its question-text version differs from `sha256:2db74e1065302281`, and the README and the published link name the new run.
- **B3.** Given the 2026-10-07 public report rebuilt from its saved results, when it is read, then it names the run that supersedes it and carries the question-text warning, and rebuilding it again reproduces it byte for byte.
- **B4.** Given the new report, when it shows the spec 004 or spec 005 results, then it states they were made under the earlier question text.
- **B5.** Given the new report, when it renders, then it names where the intent definition came from.

## Success criteria

- Every question the models answer comes with its rule.
- A reader can see, from the published report, how the ranking under a defined intent compares with the earlier run.

## Assumptions

- The new intent text reads: "What does the sender of this message want? Not a lead means anything that is not a real estate inquiry, such as spam, a vendor pitch, or a wrong number. When the message clearly asks for two different things and neither is clearly the main one, either one is correct." It is the generator's rule in the question's voice; "anything that is not a real estate inquiry" makes explicit what its "such as" examples imply, so labels like m176 and m197 stay correct.
- The run costs about $0.90 to $1.00, estimated from the 2026-10-07 run's measured $0.88 and a slightly longer intent text; not measured until the run.
- The comparison with the earlier run sits in the new report, so the move from an undefined to a defined intent is visible in one place.

## Risks and open questions

- **Still Claude-written.** The rule comes from the generator prompt drafted in a Claude session. It is the rule the labels follow, which is why it was chosen, but it is not an outside rule. Spec 005's outside definitions remain the comparison for that.
- **The two-intent sentence tells models that either answer is correct.** That matches how they are scored. It could make a model hedge differently on single-intent messages; the per-question table will show any such change.
- **Earlier checks age.** The relabeling and outside comparison were made under the earlier text. Rerunning them under the new text would cost about $2.40 and is not part of this spec.
