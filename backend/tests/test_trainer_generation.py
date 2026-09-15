import random

import pytest

from backend.words_solver.trainer import generation
from backend.words_solver.trainer.constants import SUPPORTED_SUFFIXES
from backend.words_solver.trainer.generation import (
    LetterRequirements,
    TrainerGenerationError,
    build_candidate_word_index,
    generate_geometry_plan,
    validate_geometry_plan,
)
from backend.words_solver.trainer.processing import validate_physical_path


def _words_for(suffixes):
    # Twelve deterministic names use only four prefix letters, leaving room for
    # suffix overlap in the five-slot physical-cell constraint.
    return [
        f"{first}{second}{suffix}" for suffix in suffixes for first in "abcd" for second in "abc"
    ]


def _assert_plan_geometry(plan):
    validate_geometry_plan(plan)
    assert len(plan.required_letters_by_cell) == 25
    assert all(len(letters) <= 5 for letters in plan.required_letters_by_cell)
    for suffix in plan.selected_suffixes:
        groups = [group for group in plan.groups if group.suffix == suffix]
        assert {group.role for group in groups} == {"WEAK", "MEDIUM", "RICH"}
        assert len({group.suffix_path for group in groups}) == 3
        for group in groups:
            assert 8 <= len(group.words) <= 10
            assert len({word.name for word in group.words}) == len(group.words)
            assert len(group.suffix_path) == len(suffix)
            validate_physical_path(group.suffix_path)
            for word in group.words:
                assert word.name.endswith(suffix)
                assert len(word.full_path) == len(word.name)
                assert word.full_path[-len(suffix) :] == group.suffix_path
                validate_physical_path(word.full_path)


def test_candidate_index_normalizes_deduplicates_and_filters_invalid_candidates():
    suffix = SUPPORTED_SUFFIXES[0]
    long_word = "a" * 26 + suffix
    indexed = build_candidate_word_index(
        [f"  A{suffix.upper()}  ", f"a{suffix}", suffix, long_word], [suffix]
    )
    assert indexed == {suffix: (f"a{suffix}",)}


def test_generation_is_deterministic_and_does_not_touch_global_random_state():
    suffix = SUPPORTED_SUFFIXES[0]
    words = _words_for([suffix])
    random.seed(9876)
    before = random.getstate()
    first = generate_geometry_plan([suffix], words, seed=12345)
    assert random.getstate() == before
    assert generate_geometry_plan([suffix], words, seed=12345) == first
    _assert_plan_geometry(first)


def test_failed_whole_group_keeps_parent_requirements_and_paths_unreserved(monkeypatch):
    suffix = SUPPORTED_SUFFIXES[0]
    committed = LetterRequirements()
    committed_paths = set()
    before = committed.snapshot()

    def place_then_fail(_suffix, requirements, _paths, _rng):
        assert requirements.add_path([0], "a")
        return (0,)

    monkeypatch.setattr(generation, "_find_suffix_path", place_then_fail)
    monkeypatch.setattr(generation, "_build_group_words", lambda *_args: None)

    assert (
        generation._try_build_target_group(
            suffix,
            "WEAK",
            (f"a{suffix}",) * 8,
            committed,
            committed_paths,
            generation.seeded_rng(1),
        )
        is None
    )
    assert committed.snapshot() == before
    assert committed_paths == set()


def test_requirements_merge_same_letter_free_and_reject_sixth_letter_transactionally():
    requirements = LetterRequirements()
    assert requirements.add_path([0], "a")
    before = requirements.snapshot()
    assert requirements.add_path([0], "a")
    assert requirements.snapshot() == before
    assert requirements.add_path([0], "b")
    assert requirements.add_path([0], "c")
    assert requirements.add_path([0], "d")
    assert requirements.add_path([0], "e")
    before_failure = requirements.snapshot()
    assert not requirements.add_path([0], "f")
    assert requirements.snapshot() == before_failure


@pytest.mark.parametrize("suffix_count", [1, 2, 3])
def test_generation_constructs_one_two_or_three_suffixes(suffix_count):
    suffixes = SUPPORTED_SUFFIXES[:suffix_count]
    plan = generate_geometry_plan(suffixes, _words_for(suffixes), seed=314159)
    assert len(plan.groups) == suffix_count * 3
    _assert_plan_geometry(plan)


def test_exactly_eight_words_is_valid_without_optional_ninth_or_tenth():
    suffix = SUPPORTED_SUFFIXES[0]
    words = [f"{first}{second}{suffix}" for first in "abcd" for second in "ab"]
    plan = generate_geometry_plan([suffix], words, seed=123)
    assert {len(group.words) for group in plan.groups} == {8}
    validate_geometry_plan(plan)


def test_generation_failure_is_explicit_and_deterministic_for_small_pool():
    suffix = SUPPORTED_SUFFIXES[0]
    words = [f"a{suffix}"] * 7
    with pytest.raises(TrainerGenerationError, match="fewer than 8 candidate words") as first:
        generate_geometry_plan([suffix], words, seed=1)
    with pytest.raises(TrainerGenerationError, match="fewer than 8 candidate words") as second:
        generate_geometry_plan([suffix], words, seed=1)
    assert str(first.value) == str(second.value)
