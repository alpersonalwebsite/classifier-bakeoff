# 007: Blind human labeling, for anyone who clones the repository

**Status**: Agreed (amended 2026-10-08, see the end)
**Created**: 2026-10-08

## Problem

Every definition the variants are given, and every edit to the frozen labels, came from Claude sessions.
Spec 004 showed an outside model applies those definitions consistently, and spec 005 showed definitions written by an outside model give no consistent shift toward or away from the Claude variants.
Neither tests whether a person reading these messages without the definitions agrees with the labels, or with the edits.
The owner is not the right person to do it: the owner approved every edit and saw many messages judged during review.
A reader who clones the repository and has not followed the review is the best one, so the check has to be something anyone can run.

## Scope

**In**:
- A local labeling page and commands anyone can run from a clone, with no API key and no cost.
- Two message sets: the edits set, for readers who have not seen the review, and the unseen set, for readers who have.
- Comparing each labeler's answers with the frozen labels, and on the edits set with the labels as generated and with the outside rater.
- A second look at each labeler's disagreements, with the definitions shown, in which they mark each as keep mine, keep frozen, or unsure.
- The ranking recomputed with each labeler's answers.
- Every labeling on record shown in the report, side by side, and instructions in the README.

**Out**:
- Changing the frozen labels. Human labels sit beside them.
- Keeping labelers from seeing the labels or definitions elsewhere. The page never shows them, but they are in the repository's data, specs, and code and in the published report. The README asks labelers to label before reading any of those, and B4 records what each labeler had read, so results can be read in that light.
- Any model call.

## Behavior

**B1. Two message sets.** The **edits set** is the 72 messages of spec 004's blind set: every message carrying an edited label and the same 30 controls, so a fresh reader can test the edits directly and be compared with the outside rater message for message.
The **unseen set** is 60 messages drawn with a fixed seed from those the owner had not seen judged: every frozen message except the 42 carrying an edited label and the 51 others shown with labels during review (listed in a committed file), which leaves 107.
A labeler picks a set; either way the messages appear one at a time, shuffled into an order of the set's own, under identifiers that reveal nothing.

**B2. No labels, no definitions.** For each message the page shows the text and four plain questions, each with its allowed answers: what the sender wants, when they plan to act, whether they ask to be contacted, and how urgent the request is.
It shows no definition, no label of any kind, and no variant's or rater's answer, and nothing the page loads contains any of those.
Intent accepts one or two answers, as the frozen labels do; every other question takes one.

**B3. Easy to finish.** The labeler can stop and resume without losing answers, see how many messages remain, go back to change an answer, and save the finished answers to a file.
The page works offline and makes no network request.

**B4. Per labeler, kept apart.** Each labeling is saved under a name the labeler chooses, with its set, seed, and date, so several people's results sit side by side and none overwrites another.
Before the first message, the page asks what the labeler had already read, as one choice ordered from least to most: nothing about the project, the published report, the specs or code, or the review itself. A labeler to whom several apply picks the furthest they have gone. The answer is saved with the labeling, self-declared.
A labeler who wants theirs in the published report commits it through a pull request.

**B5. The comparison.** For each labeling on record and each question, the report shows how often the labeler's first-pass answer matches the frozen label.
On the edits set it also shows, over the edited labels, how often the labeler chose the frozen label, the label as generated, or neither, beside the labeler's agreement on that question across the controls and beside the outside rater's figures, as spec 004 does.

**B6. The second look.** After the first pass, the labeler reviews every answer that differs from the frozen label, now with that question's current definition and the frozen label shown, and marks it keep mine, keep frozen, or unsure.
The report shows those counts per question: disagreements kept after reading the definition are where it draws a line the labeler would not; ones given up are where the plain question was ambiguous.
The first-pass answers are never changed by this step.

**B7. Does the ranking hold?** For each labeling, the ranking is recomputed under spec 003's rule with the labeler's answers in place of the frozen labels: on the edits set, in place of the edited labels only, as spec 004 does; on the unseen set, on its 60 messages.
The report states plainly whether rank 1 and the tiers are the same.

**B8. Disclosed.** The report names each labeling's set, labeler name, and what the labeler declared having read, calls it one person's single blind pass made without the definitions on the page, and groups labelings by that declaration, so ones made after reading the report or definitions are not mixed with ones made fresh.
With no labeling on record, the report says so and points to the README section that explains how to run one.

## Acceptance

- **B1.** Given the edits set, when it is built, then it holds the same 72 messages as spec 004's blind set, in a different order; given the unseen set, then it holds 60 messages, none of them excluded, the same 60 every time.
- **B2.** Given every file the page loads, when it is searched for any definition text, any message id, and any label given as an answer, then none is found; the label words appear only as the allowed choices.
- **B2.** Given a message, when the labeler answers intent with two labels, then both are kept; any other question accepts exactly one.
- **B3.** Given answers to 20 messages, when the page is closed and reopened, then those 20 answers are still there and the page resumes at message 21, shows how many remain, and lets the labeler go back and change an earlier answer.
- **B3.** Given the page open, when its network activity is observed, then it makes no request.
- **B4.** Given two labelers with different names, when both import their answers, then both records exist and neither changed the other.
- **B4.** Given the page, when a labeler starts, then it asks what they had already read before showing the first message, and the saved file carries the answer.
- **B8.** Given two labelings with different declarations, when the report renders, then they appear in separate groups, each labeled with its declaration.
- **B5.** Given a labeling on the edits set, when the report renders, then it shows per question the frozen, generated, and neither counts with the control baseline beside the outside rater's; given one on the unseen set, then it shows per question the matches with the frozen labels.
- **B6.** Given a second look on record, when the report renders, then it shows per question how many disagreements were kept, given up, or marked unsure, and the first-pass answers are unchanged.
- **B7.** Given a labeling on the edits set, when the ranking is recomputed, then only the edited labels change; on the unseen set, only its 60 messages change.
- **B8.** Given no labeling on record, when the report renders, then it says none is on record and points to the README.

## Success criteria

- Someone who clones the repository can run a labeling from the README alone, with no key, in one sitting of under 45 minutes, and a second look in under 15.
- Each labeling on record shows, per question, where its labeler and the labels agree, where the labeler keeps a different reading after seeing the definition, and whether the ranking survives.

## Assumptions

- The plain questions are short rewrites of each question's opening, with the definitions removed: "What does the sender want?" (intent's first sentence, cut), "When does the sender plan to act?" (rewritten from "When does the sender plan to buy, sell, rent, or move?"), "Does the sender ask to be contacted?" (rewritten from a first sentence that already defines what counts), and "How urgent is the request?" (urgency's first sentence, cut). The allowed answers are the label words, unchanged.
- The 51 shown messages for the unseen set are a best-effort list: 45 from a reviewer's count of non-edited messages its reviews showed with a label, plus 6 more quoted in replies during this work, counted as a union with no edited message counted twice. It is committed so a reader can check it.
- A labeler name is any handle the labeler chooses; it is published if they commit their labeling, so a real name is optional.
- The page is a local HTML file opened in a browser, not a published page, and saves progress in that browser.

## Risks and open questions

- **One person is one opinion.** Each labeling is a single pass; several labelers side by side are what make the check strong, which is why B4 keeps them apart.
- **Blindness rests on trust.** The labels and definitions are in the repository and in the published report, which most people will read before deciding to clone. The README asks labelers to label first; the self-declared field in B4 is what keeps a labeling made after reading them from passing as a fresh one.
- **Plain questions invite different conventions.** Without definitions, some disagreement is about where to draw a line rather than bias. B6 separates the two.

## Amendment

2026-10-08: the first agreed version had the owner label the unseen set. The owner chose not to label, and asked that anyone cloning the repository be able to run and verify it instead. The scope became a tool for any labeler, with two message sets, per-labeler records, and README instructions; the unseen set and its exclusion list are kept for readers who have followed the review.
