import pytest

from backend.words_solver.trainer.constants import SUPPORTED_SUFFIXES
from backend.words_solver.trainer.generation import (
    TrainerBoard,
    TrainerBoardValidationError,
    TrainerCell,
    seeded_rng,
    validate_trainer_board,
)
from backend.words_solver.trainer.processing import (
    are_adjacent,
    classify_suffix_group,
    score_word_for_path,
    validate_physical_path,
)
from backend.words_solver.word_search import calculate_word_score


def _board():
    cells = [TrainerCell(("a", "b", "c", "d", "e")) for _ in range(25)]
    for index, multiplier in enumerate(("x2", "x3", "c2", "c3")):
        cells[index] = TrainerCell(("a", "b", "c", "d", "e"), multiplier=multiplier)
    return TrainerBoard(tuple(cells), (SUPPORTED_SUFFIXES[0],), seed=42)


def test_valid_25_by_5_board():
    validate_trainer_board(_board())


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda board: TrainerBoard(board.cells[:-1], board.selected_suffixes, 1), "25 cells"),
        (
            lambda board: TrainerBoard(
                (TrainerCell(("a", "b", "c", "d")),) + board.cells[1:],
                board.selected_suffixes,
                1,
            ),
            "5 letter slots",
        ),
        (
            lambda board: TrainerBoard(
                (TrainerCell(("a", "b", "c", "d", "e"), current_index=5),) + board.cells[1:],
                board.selected_suffixes,
                1,
            ),
            "current_index",
        ),
    ],
)
def test_board_shape_and_current_index_rejected(mutate, message):
    with pytest.raises(TrainerBoardValidationError, match=message):
        validate_trainer_board(mutate(_board()))


def test_missing_or_duplicate_multiplier_types_rejected():
    board = _board()
    missing = TrainerBoard(
        tuple(TrainerCell(cell.letters, cell.current_index) for cell in board.cells),
        board.selected_suffixes,
        1,
    )
    duplicate = TrainerBoard(
        (TrainerCell(board.cells[0].letters, multiplier="x2"),)
        + (TrainerCell(board.cells[1].letters, multiplier="x2"),)
        + board.cells[2:],
        board.selected_suffixes,
        1,
    )
    for invalid in (missing, duplicate):
        with pytest.raises(TrainerBoardValidationError, match="exactly one"):
            validate_trainer_board(invalid)


def test_invalid_suffix_count_and_duplicates_rejected():
    board = _board()
    for suffixes in ((), SUPPORTED_SUFFIXES[:4], (SUPPORTED_SUFFIXES[0], SUPPORTED_SUFFIXES[0])):
        invalid = TrainerBoard(board.cells, suffixes, 1)
        with pytest.raises(TrainerBoardValidationError):
            validate_trainer_board(invalid)


def test_eight_neighbour_geometry_and_path_rules():
    assert are_adjacent(0, 1)
    assert are_adjacent(0, 6)  # diagonal
    assert not are_adjacent(0, 2)
    assert validate_physical_path([0]) == (0,)
    assert validate_physical_path([0, 6, 12]) == (0, 6, 12)
    with pytest.raises(ValueError, match="repeat"):
        validate_physical_path([0, 1, 0])
    with pytest.raises(ValueError, match="8-neighbours"):
        validate_physical_path([0, 2])


def test_seeded_rng_is_deterministic_and_isolated():
    assert [seeded_rng(123).randrange(1000) for _ in range(3)] == [
        seeded_rng(123).randrange(1000) for _ in range(3)
    ]
    first = seeded_rng(123)
    second = seeded_rng(123)
    assert [first.randrange(1000) for _ in range(5)] == [second.randrange(1000) for _ in range(5)]


@pytest.mark.parametrize(
    ("scores", "difficulty"),
    [
        ([100] * 8 + [399, 500], "WEAK"),
        ([400] * 8 + [599, 700], "MEDIUM"),
        ([600] * 8 + [800, 300], "RICH"),
    ],
)
def test_group_classifies_each_difficulty(scores, difficulty):
    stats = classify_suffix_group(
        [{"name": f"word{index}", "score": score} for index, score in enumerate(scores)]
    )
    assert stats["fits"][difficulty]
    assert stats["bands"][difficulty]["ratio"] == 0.9


def test_group_exposes_80_percent_near_boundary_without_rejecting_data():
    stats = classify_suffix_group(
        [{"name": f"word{index}", "score": 400 if index < 8 else 399} for index in range(10)]
    )
    assert stats["bands"]["MEDIUM"] == {"count": 8, "ratio": 0.8}
    assert stats["fits"]["MEDIUM"]


def test_duplicate_word_uses_best_score_and_medians_support_odd_and_even_counts():
    duplicate = classify_suffix_group(
        [
            {"name": "same", "score": 100},
            {"name": "same", "score": 700},
            {"name": "other", "score": 500},
        ]
    )
    assert duplicate["unique_word_count"] == 2
    assert duplicate["scores"] == [500, 700]
    assert duplicate["median_score"] == 600
    assert classify_suffix_group({"a": 100, "b": 300, "c": 900})["median_score"] == 300


def test_scoring_adapter_matches_production_calculator():
    board = _board()
    expected = calculate_word_score(
        "abcd",
        ["x2", "x3", "c2", "c3"],
        ["c2", "c3"],
    )
    assert score_word_for_path("abcd", board, [0, 1, 2, 3]) == expected
