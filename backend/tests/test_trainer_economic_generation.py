from random import Random

from backend.words_solver.trainer.constants import SUPPORTED_SUFFIXES
from backend.words_solver.trainer.economic_generation import (
    base_word_score,
    find_prefix_path_candidates,
    role_aware_candidates,
    word_role_key,
)
from backend.words_solver.trainer.generation import LetterRequirements
from backend.words_solver.word_search import calculate_word_score


def test_base_score_delegates_to_production_scorer():
    assert base_word_score("abcdef") == calculate_word_score("abcdef", [None] * 6, [])


def test_role_aware_ordering_prefers_longer_richer_candidates():
    suffix = SUPPORTED_SUFFIXES[0]
    words = (f"a{suffix}", f"abcdef{suffix}", f"abc{suffix}")
    assert role_aware_candidates(words, suffix, "WEAK")[0] == f"a{suffix}"
    assert role_aware_candidates(words, suffix, "RICH")[0] == f"abcdef{suffix}"


def test_prefix_candidates_are_multiple_and_do_not_mutate_requirements():
    requirements = LetterRequirements()
    before = requirements.snapshot()
    paths = find_prefix_path_candidates("abc", (12,), requirements, Random(5), limit=3)
    assert len(paths) >= 2
    assert requirements.snapshot() == before
    assert all(path[-1] in {6, 7, 8, 11, 13, 16, 17, 18} for path in paths)


def test_word_role_quality_uses_real_band_boundaries():
    path = (0, 1)
    assert word_role_key(650, "RICH", path)[0] is False
    assert word_role_key(599, "RICH", path)[0] is True
    assert word_role_key(399, "WEAK", path)[0] is False
    assert word_role_key(400, "WEAK", path)[0] is True
