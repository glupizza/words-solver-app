import random

import pytest

from backend.words_solver.trainer import economics
from backend.words_solver.trainer.constants import MULTIPLIER_TYPES, SUPPORTED_SUFFIXES
from backend.words_solver.trainer.economics import (
    ScoredTargetGroup,
    _role_median_distance,
    assign_roles_for_suffix,
    generate_economic_plan,
    optimize_multiplier_placement,
    score_target_group,
)
from backend.words_solver.trainer.generation import (
    TargetGroupPlan,
    TargetWordPlan,
    generate_geometry_plan,
)
from backend.words_solver.trainer.processing import (
    score_word_with_multipliers,
    validate_multiplier_assignment,
)
from backend.words_solver.word_search import calculate_word_score


def _assignment():
    values = [None] * 25
    for cell, multiplier in zip((10, 11, 12, 13), MULTIPLIER_TYPES, strict=True):
        values[cell] = multiplier
    return tuple(values)


def _group(provisional_role, marker):
    suffix = "z"
    words = tuple(
        TargetWordPlan(f"{marker}{index}{suffix}", f"{marker}{index}", (0, 1, 2))
        for index in range(8)
    )
    return TargetGroupPlan(suffix, provisional_role, (2,), words)


def _words_for(suffixes):
    return [
        f"{first}{second}{suffix}" for suffix in suffixes for first in "abcd" for second in "abc"
    ]


def test_multiplier_assignment_requires_one_of_each_on_distinct_cells():
    assignment = validate_multiplier_assignment(_assignment())
    assert {multiplier: assignment.index(multiplier) for multiplier in MULTIPLIER_TYPES} == {
        "x2": 10,
        "x3": 11,
        "c2": 12,
        "c3": 13,
    }
    with pytest.raises(ValueError, match="exactly one"):
        validate_multiplier_assignment((None,) * 25)
    invalid = list(_assignment())
    invalid[11] = "x2"
    with pytest.raises(ValueError, match="exactly one"):
        validate_multiplier_assignment(invalid)


def test_path_scoring_adapter_delegates_all_multiplier_semantics_to_production_scorer():
    assignment = [None] * 25
    assignment[0:4] = ["x2", "x3", "c2", "c3"]
    expected = calculate_word_score("abcd", ["x2", "x3", "c2", "c3"], ["c2", "c3"])
    assert score_word_with_multipliers("abcd", [0, 1, 2, 3], assignment) == expected


def test_group_scoring_uses_real_scores_and_classification_statistics():
    scored = score_target_group(_group("WEAK", "a"), _assignment(), "WEAK")
    assert scored.median_score == 6
    assert scored.in_band_count == 8
    assert scored.in_band_ratio == 1.0
    assert scored.fits_target


def test_provisional_roles_are_reassigned_and_exact_fits_beat_separation(monkeypatch):
    groups = (_group("RICH", "a"), _group("WEAK", "b"), _group("MEDIUM", "c"))
    desired = {"a": (350, "WEAK"), "b": (400, "MEDIUM"), "c": (600, "RICH")}

    def fake_statistics(group, _multipliers):
        median, exact_role = desired[group.words[0].name[0]]
        return (), {
            "median_score": median,
            "bands": {
                role: {
                    "count": 8 if role == exact_role else 0,
                    "ratio": 1.0 if role == exact_role else 0.0,
                }
                for role in ("WEAK", "MEDIUM", "RICH")
            },
            "fits": {role: role == exact_role for role in ("WEAK", "MEDIUM", "RICH")},
        }

    monkeypatch.setattr(economics, "_score_group_statistics", fake_statistics)
    scored, quality = assign_roles_for_suffix(groups, _assignment())
    assert quality.exact_group_count == 3
    assert {group.final_role: group.group.words[0].name[0] for group in scored} == {
        "WEAK": "a",
        "MEDIUM": "b",
        "RICH": "c",
    }
    # The exact assignment has only 50 points of WEAK->MEDIUM separation;
    # exact fit count still wins over the soft 100-point preference.
    assert quality.total_separation_deficit == 50


@pytest.mark.parametrize(
    ("role", "median", "distance"),
    [("WEAK", 400, 1), ("MEDIUM", 399, 1), ("MEDIUM", 600, 1), ("RICH", 599, 1)],
)
def test_median_band_distance(role, median, distance):
    assert _role_median_distance(role, median) == distance


def test_economic_optimizer_is_deterministic_and_preserves_global_random_state():
    suffix = SUPPORTED_SUFFIXES[0]
    geometry = generate_geometry_plan([suffix], _words_for([suffix]), seed=7)
    random.seed(1234)
    before = random.getstate()
    first = optimize_multiplier_placement(geometry, seed=99)
    assert random.getstate() == before
    assert optimize_multiplier_placement(geometry, seed=99) == first
    assert len({first.multiplier_cells[item] for item in MULTIPLIER_TYPES}) == 4


def test_economic_generation_preserves_selected_order_and_returns_degraded_plan():
    suffixes = (SUPPORTED_SUFFIXES[1], SUPPORTED_SUFFIXES[0])
    plan = generate_economic_plan(suffixes, _words_for(suffixes), seed=33)
    assert plan.geometry.selected_suffixes == suffixes
    assert plan.quality.total_group_count == 6
    assert not plan.exact_targets_met
    assert plan.degraded


def test_scored_group_model_can_represent_any_valid_eight_word_group():
    group = _group("WEAK", "a")
    scored = ScoredTargetGroup(group, "WEAK", (), 10, 8, 1.0, True)
    assert scored.group.words[0].name.endswith(group.suffix)
