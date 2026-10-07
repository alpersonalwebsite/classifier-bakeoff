"""Spec 003: the vendor-neutral ranking and the report built around it."""

import random
import re

from bakeoff.report import render
from bakeoff.scoring import VariantScore, rank_variants

N = 200


def variant(name, correct, cost, p50=1.0, lower_bound=False, signature=None, seed=0):
    """A complete variant with `correct` of N messages all-four right, at given positions."""
    rng = random.Random(seed)
    ids = [f"m{i:03d}" for i in range(N)]
    right = set(rng.sample(ids, correct)) if isinstance(correct, int) else set(correct)
    s = VariantScore(name=name, status="complete", reason="", total_messages=N, classified=N)
    s.all_four = len(right)
    s.all_four_vector = {i: int(i in right) for i in ids}
    s.intent_vector = dict(s.all_four_vector)
    s.correct = {"intent": s.all_four, "timeline": N, "wants_contact": N, "urgency": N}
    s.invalid = {"intent": 0, "timeline": 0, "wants_contact": 0, "urgency": 0}
    s.cost_per_message, s.cost_is_lower_bound, s.price_known = cost, lower_bound, True
    s.latency_p50, s.latency_p95 = p50, p50 * 2
    s.signature = signature if signature is not None else (name, seed)
    return s


def shared_right(k, seed=1):
    return set(random.Random(seed).sample([f"m{i:03d}" for i in range(N)], k))


def test_b1_three_tied_variants_rank_by_cost():
    right = shared_right(169)
    vs = [variant("a", right, 0.001998, signature="A"), variant("b", right, 0.000062, signature="B"), variant("c", right, 0.000081, signature="C")]
    ranked = rank_variants(vs)
    assert [s.name for s in ranked] == ["b", "c", "a"]
    assert [s.rank for s in ranked] == [1, 2, 3] and {s.tier for s in ranked} == {1}


def test_b1_identical_answers_share_a_rank_and_ranks_have_no_gaps():
    right = shared_right(169)
    vs = [variant("x", right, 0.000062, signature="same"), variant("y", right, 0.000081, signature="same"), variant("z", right, 0.002, signature="other")]
    ranked = rank_variants(vs)
    assert [(s.name, s.rank) for s in ranked] == [("x", 1), ("y", 1), ("z", 2)]


def test_b1_a_cheaper_tied_variant_ranks_above_a_slightly_higher_one():
    base = sorted(shared_right(146, seed=3))
    hi = set(base) | {next(f"m{i:03d}" for i in range(N) if f"m{i:03d}" not in base)}  # 147 right
    ranked = rank_variants([variant("high", hi, 0.0015), variant("cheap", set(base), 0.000025)])
    assert [s.name for s in ranked] == ["cheap", "high"] and ranked[0].tier == ranked[1].tier == 1


def test_b1_a_clearly_worse_variant_starts_a_later_tier():
    top = shared_right(169)
    worse = set(sorted(top)[:120])  # a subset, so every difference points one way
    ranked = rank_variants([variant("top", top, 0.002), variant("worse", worse, 0.00001)])
    assert [(s.name, s.tier) for s in ranked] == [("top", 1), ("worse", 2)]


def test_b2_a_lower_bound_ranked_above_another_is_unconfirmed():
    right = shared_right(169)
    ranked = rank_variants([variant("lb", right, 0.0001, lower_bound=True, signature="L"), variant("exact", right, 0.0005, signature="E")])
    assert ranked[0].name == "lb" and ranked[0].order_unconfirmed


def test_b2_an_exact_cost_above_a_lower_bound_is_settled():
    right = shared_right(169)
    ranked = rank_variants([variant("exact", right, 0.0001, signature="E"), variant("lb", right, 0.0005, lower_bound=True, signature="L")])
    assert ranked[0].name == "exact" and not any(s.order_unconfirmed for s in ranked)


META = {"run_id": "r", "started_at": "2026-10-07T00:00:00Z", "dataset_version": "d", "cap_usd": 2.0, "prices": {}, "models": {}}


def _ranked_six():
    tied = shared_right(169)
    return rank_variants(
        [
            variant("v-cheap", tied, 0.000062, p50=0.2, signature="same"),
            variant("v-cheap-twin", tied, 0.000081, p50=0.8, signature="same"),
            variant("v-dear", tied, 0.002, p50=1.4, signature="D"),
            variant("v-mid", set(sorted(tied)[:145]), 0.000025, p50=0.2, signature="M"),
            variant("v-low", set(sorted(tied)[:129]), 0.0008, p50=0.8, signature="W"),
        ]
    )


def test_b3_rank_1_and_the_rule_come_before_the_first_table():
    page = render(META, _ranked_six(), public=True, withheld=[])
    first_table = page.index("<table")
    assert page.index("Rank 1: <b>v-cheap</b> and <b>v-cheap-twin</b>") < first_table
    assert page.index("Rule: complete variants are ranked") < first_table


def test_b4_head_to_head_in_rank_order_against_the_rank_1_reference():
    page = render(META, _ranked_six(), public=True, withheld=[])
    h2h = page[page.index("<h2>Head-to-head</h2>") : page.index("<h2>Against rank 1</h2>")]
    order = [n for n in re.findall(r"<td>(v-[a-z-]+)</td>", h2h)]
    assert order == ["v-cheap", "v-cheap-twin", "v-dear", "v-mid", "v-low"]
    assert "the rank 1 variant <b>v-cheap</b>" in page


def test_b5_permuting_names_changes_only_the_names():
    first = render(META, _ranked_six(), public=True, withheld=[])
    swap = {"v-cheap": "q1", "v-cheap-twin": "q2", "v-dear": "q3", "v-mid": "q4", "v-low": "q5"}
    renamed = _ranked_six()
    for s in renamed:
        s.name = swap[s.name]
    second = render(META, rank_variants(renamed), public=True, withheld=[])
    for old in sorted(swap, key=len, reverse=True):  # longest first, so "v-cheap" never eats "v-cheap-twin"
        first = first.replace(old, swap[old])
    assert first == second


def test_b5_no_characterizing_words():
    page = render(META, _ranked_six(), public=True, withheld=[]).lower()
    for word in ("ceiling", "leader", "flagship", "best"):
        assert word not in page, word


def test_b6_label_dependence_is_shown_with_its_limits_and_who_reviewed():
    meta_ds = {"generator": "x/y", "size": N, "label_review": {"summary": "Edits proposed with help from Model Z, approved by the owner."}}
    deps = {s.name: (0.6, 0.8) for s in _ranked_six()}
    page = render(META, _ranked_six(), public=True, withheld=[], dataset_meta=meta_ds, label_dependence=deps)
    section = page[page.index("<h2>Dependence on the label edits</h2>") :]
    assert "Edits proposed with help from Model Z, approved by the owner." in section
    assert "does not test whether the review was biased" in section
    assert "<td>60.0%</td><td>80.0%</td><td>+20.0</td>" in section


def test_withheld_cost_hides_the_position_inside_a_tier():
    page = render(META, _ranked_six(), public=True, withheld=[{"variant": "v-dear", "figure": "cost", "reason": "r"}])
    assert "tier 1, position withheld" in page
