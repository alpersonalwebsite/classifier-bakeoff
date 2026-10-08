# 006: Give intent a definition

**Status**: Implemented
**Amended**: 2026-10-07, B3: the earlier report is removed rather than kept, at the owner's request; 2026-10-08, B4, success criteria, and risks to match
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
The earlier report and its conclusions are removed from the repository, so only the run with intent defined is published. They remain in git history, and its Pages URL stops resolving. (Amended: the first version kept it with a superseded note.)

**B4. Earlier checks stay readable.** The spec 004 relabeling was made under the earlier question text, so the new report says so where it shows it, naming the questions whose text differs and how many of its checked labels they touch.
The spec 005 outside run and labels used the outside definitions, which this change does not touch, so they stay current; the report says what "current definitions" means there. (Amended 2026-10-08: the first version said both checks used the earlier text.)

**B5. Disclosed.** The report says the intent definition, like the other three, comes from the Claude-assisted drafting, here the generator's rule.

## Acceptance

- **B1.** Given the new intent question text, when it is compared with the generator's description of intent, then it states the same rule: not-a-lead as anything that is not a real estate inquiry, with examples, and the two-intent rule including that neither is clearly the main one.
- **B1.** Given the frozen messages labeled not a lead, including m176 (a newsletter confirmation) and m197 (a school PTA asking for a donation), when read against the new text, then each is covered by it.
- **B1.** Given any two variants' requests in the new run, when their intent text is compared, then it matches word for word.
- **B2.** Given the frozen dataset after this change, when its hash is checked, then it is still `sha256:8c43a059d800a559`.
- **B3.** Given the new run, when its record is read, then its question-text version differs from `sha256:2db74e1065302281`, and the README and the published link name the new run.
- **B3.** Given the repository after this change, when `reports/public/` and `reports/conclusions/` are listed, then only the run with intent defined is there.
- **B4.** Given the new report, when it shows the spec 004 relabeling, then it names intent as the only question whose text differs and says it affects 1 of the 46 edited labels; and the spec 005 section does not call the outside run outdated.
- **B5.** Given the new report, when it renders, then it names where the intent definition came from.

## Success criteria

- Every question the models answer comes with its rule.
- The published ranking comes from a run in which all four questions state their rule. (Amended: the first version also had the report compare it with the earlier run, which B3's removal took out.)

## Assumptions

- The new intent text reads: "What does the sender of this message want? Not a lead means anything that is not a real estate inquiry, such as spam, a vendor pitch, or a wrong number. When the message clearly asks for two different things and neither is clearly the main one, either one is correct." It is the generator's rule in the question's voice; "anything that is not a real estate inquiry" makes explicit what its "such as" examples imply, so labels like m176 and m197 stay correct.
- The run costs about $0.90 to $1.00, estimated from the 2026-10-07 run's measured $0.88 and a slightly longer intent text; not measured until the run.

## Risks and open questions

- **Still Claude-written.** The rule comes from the generator prompt drafted in a Claude session. It is the rule the labels follow, which is why it was chosen, but it is not an outside rule. Spec 005's outside definitions remain the comparison for that.
- **The two-intent sentence tells models that either answer is correct.** That matches how they are scored. It could make a model hedge differently on single-intent messages; the per-question table will show any such change.
- **The relabeling ages.** The spec 004 relabeling was made under the earlier intent text; B4 shows how many of its labels that touches. Rerunning it with the outside labeling was estimated at about $2.40 and is not part of this spec. The spec 005 outside run is unaffected (B4).
