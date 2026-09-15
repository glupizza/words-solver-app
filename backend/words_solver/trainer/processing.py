"""Pure geometry, score, and target-group helpers for Grail Trainer."""

from collections.abc import Iterable, Mapping
from statistics import median
from typing import Any

from ..word_search import calculate_word_score
from .constants import (
    BOARD_SIZE,
    IN_BAND_TARGET_RATIO,
    MEDIUM_MAX_SCORE,
    MEDIUM_MIN_SCORE,
    MULTIPLIER_TYPES,
    PHYSICAL_CELL_COUNT,
    RICH_MIN_SCORE,
    TARGET_WORDS_MAX,
    TARGET_WORDS_MIN,
    WEAK_MAX_SCORE,
)
from .generation import TrainerBoard, validate_trainer_board


def is_cell_index(cell: int) -> bool:
    return isinstance(cell, int) and not isinstance(cell, bool) and 0 <= cell < PHYSICAL_CELL_COUNT


def are_adjacent(first: int, second: int) -> bool:
    """Whether two distinct physical cells share an edge or corner."""
    if not is_cell_index(first) or not is_cell_index(second) or first == second:
        return False
    first_row, first_col = divmod(first, BOARD_SIZE)
    second_row, second_col = divmod(second, BOARD_SIZE)
    return max(abs(first_row - second_row), abs(first_col - second_col)) == 1


def neighbour_cells(cell: int) -> tuple[int, ...]:
    if not is_cell_index(cell):
        raise ValueError("cell index must be between 0 and 24")
    return tuple(other for other in range(PHYSICAL_CELL_COUNT) if are_adjacent(cell, other))


def validate_physical_path(path: Iterable[int]) -> tuple[int, ...]:
    """Validate a non-repeating, 8-neighbour path and return it as a tuple."""
    try:
        normalized = tuple(path)
    except TypeError as exc:
        raise ValueError("path must be an iterable of cell indices") from exc
    if not normalized:
        raise ValueError("path must contain at least one cell")
    if any(not is_cell_index(cell) for cell in normalized):
        raise ValueError("path cells must be between 0 and 24")
    if len(set(normalized)) != len(normalized):
        raise ValueError("path cannot repeat a physical cell")
    if any(not are_adjacent(first, second) for first, second in zip(normalized, normalized[1:])):
        raise ValueError("consecutive path cells must be 8-neighbours")
    return normalized


def validate_submitted_path(path: Iterable[int]) -> tuple[int, ...]:
    """Game-mechanics name for structural submitted-path validation."""
    return validate_physical_path(path)


def current_path_letters(board: TrainerBoard | dict[str, Any], path: Iterable[int]) -> str:
    """Read the presently selected cyclic letters along a valid path."""
    validate_trainer_board(board)
    normalized = validate_physical_path(path)
    cells = board.cells if isinstance(board, TrainerBoard) else board["cells"]
    return "".join(
        (
            cell.letters[cell.current_index]
            if hasattr(cell, "letters")
            else cell["letters"][cell["current_index"]]
        )
        for cell in (cells[index] for index in normalized)
    )


def score_word_for_path(
    word: str, board: TrainerBoard | dict[str, Any], path: Iterable[int]
) -> int:
    """Score a path with the production formula and its multiplier semantics."""
    validate_trainer_board(board)
    normalized = validate_submitted_path(path)
    if not isinstance(word, str) or len(word) != len(normalized):
        raise ValueError("word must be a string with one letter per path cell")
    cells = board.cells if isinstance(board, TrainerBoard) else board["cells"]
    multipliers = [
        cell.multiplier if hasattr(cell, "multiplier") else cell.get("multiplier")
        for cell in (cells[index] for index in normalized)
    ]
    return calculate_word_score(
        word,
        multipliers,
        [multiplier for multiplier in multipliers if multiplier in ("c2", "c3")],
    )


def validate_multiplier_assignment(multipliers: Iterable[str | None]) -> tuple[str | None, ...]:
    """Validate the one-global-set-of-four economic multiplier assignment."""
    try:
        assignment = tuple(multipliers)
    except TypeError as exc:
        raise ValueError("multiplier assignment must be iterable") from exc
    if len(assignment) != PHYSICAL_CELL_COUNT:
        raise ValueError("multiplier assignment must contain 25 cells")
    if any(
        multiplier is not None and multiplier not in MULTIPLIER_TYPES for multiplier in assignment
    ):
        raise ValueError("multiplier assignment contains an unknown multiplier")
    present = tuple(multiplier for multiplier in assignment if multiplier is not None)
    if len(present) != len(MULTIPLIER_TYPES) or set(present) != set(MULTIPLIER_TYPES):
        raise ValueError("assignment must contain exactly one x2, x3, c2, and c3")
    return assignment


def score_word_with_multipliers(
    word: str, full_path: Iterable[int], multipliers: Iterable[str | None]
) -> int:
    """Score a concrete path through the production word-score implementation."""
    path = validate_physical_path(full_path)
    assignment = validate_multiplier_assignment(multipliers)
    if not isinstance(word, str) or len(word) != len(path):
        raise ValueError("word must be a string with one letter per path cell")
    path_multipliers = [assignment[cell] for cell in path]
    return calculate_word_score(
        word,
        path_multipliers,
        [multiplier for multiplier in path_multipliers if multiplier in ("c2", "c3")],
    )


def _best_word_scores(words: Mapping[str, int] | Iterable[Mapping[str, Any]]) -> dict[str, int]:
    if isinstance(words, Mapping):
        source = (
            {"name": name, "score": value["score"]}
            if isinstance(value, Mapping)
            else {"name": name, "score": value}
            for name, value in words.items()
        )
    else:
        source = words
    best = {}
    for item in source:
        try:
            name, score = item["name"], item["score"]
        except (TypeError, KeyError) as exc:
            raise ValueError("words must provide name and score values") from exc
        if not isinstance(name, str) or not name or not isinstance(score, (int, float)):
            raise ValueError("word names must be non-empty strings and scores numeric")
        best[name] = max(score, best.get(name, score))
    return best


def classify_suffix_group(words: Mapping[str, int] | Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Measure unique words for one exact concrete suffix path.

    Repeated word names retain their best score, letting future generation rank
    near misses without treating the target ratio as a hard rejection.
    """
    scores_by_word = _best_word_scores(words)
    scores = sorted(scores_by_word.values())
    count = len(scores)
    if not count:
        return {
            "unique_word_count": 0,
            "scores": [],
            "median_score": None,
            "target_word_count_ok": False,
            "bands": {},
            "fits": {},
        }

    bands = {
        "WEAK": sum(score < WEAK_MAX_SCORE for score in scores),
        "MEDIUM": sum(MEDIUM_MIN_SCORE <= score <= MEDIUM_MAX_SCORE for score in scores),
        "RICH": sum(score >= RICH_MIN_SCORE for score in scores),
    }
    return {
        "unique_word_count": count,
        "scores": scores,
        "median_score": median(scores),
        "target_word_count_ok": TARGET_WORDS_MIN <= count <= TARGET_WORDS_MAX,
        "bands": {
            difficulty: {"count": in_band, "ratio": in_band / count}
            for difficulty, in_band in bands.items()
        },
        "fits": {
            "WEAK": median(scores) < WEAK_MAX_SCORE
            and bands["WEAK"] / count >= IN_BAND_TARGET_RATIO,
            "MEDIUM": MEDIUM_MIN_SCORE <= median(scores) <= MEDIUM_MAX_SCORE
            and bands["MEDIUM"] / count >= IN_BAND_TARGET_RATIO,
            "RICH": median(scores) >= RICH_MIN_SCORE
            and bands["RICH"] / count >= IN_BAND_TARGET_RATIO,
        },
    }
