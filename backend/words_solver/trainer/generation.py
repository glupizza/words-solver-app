"""Pure board representation and deterministic generation primitives."""

from dataclasses import dataclass, field
from random import Random
from typing import Any

from .constants import (
    GENERATOR_VERSION,
    LETTER_SLOTS_PER_CELL,
    MAX_SELECTED_SUFFIXES,
    MULTIPLIER_TYPES,
    PHYSICAL_CELL_COUNT,
    SUPPORTED_SUFFIXES,
)


class TrainerBoardValidationError(ValueError):
    """A trainer board does not meet its fixed game invariants."""


@dataclass(frozen=True)
class TrainerCell:
    """One physical cell and its five cyclic letter choices."""

    letters: tuple[str, ...]
    current_index: int = 0
    multiplier: str | None = None


@dataclass(frozen=True)
class TrainerBoard:
    """Serializable trainer-board domain data; target metadata remains private."""

    cells: tuple[TrainerCell, ...]
    selected_suffixes: tuple[str, ...]
    seed: int
    generator_version: int = GENERATOR_VERSION
    hidden_targets: Any | None = field(default=None, repr=False)


def seeded_rng(seed: int) -> Random:
    """Return an isolated deterministic RNG for trainer generation decisions."""
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("trainer seed must be an integer")
    return Random(seed)


def _board_parts(board: TrainerBoard | dict[str, Any]):
    if isinstance(board, TrainerBoard):
        return board.cells, board.selected_suffixes
    if isinstance(board, dict):
        return board.get("cells"), board.get("selected_suffixes")
    raise TrainerBoardValidationError("board must be a TrainerBoard or mapping")


def _cell_parts(cell: TrainerCell | dict[str, Any]):
    if isinstance(cell, TrainerCell):
        return cell.letters, cell.current_index, cell.multiplier
    if isinstance(cell, dict):
        return cell.get("letters"), cell.get("current_index"), cell.get("multiplier")
    raise TrainerBoardValidationError("each cell must be a TrainerCell or mapping")


def validate_trainer_board(board: TrainerBoard | dict[str, Any]) -> None:
    """Raise ``TrainerBoardValidationError`` when fixed board rules are broken."""
    cells, selected_suffixes = _board_parts(board)
    if not isinstance(cells, (list, tuple)) or len(cells) != PHYSICAL_CELL_COUNT:
        raise TrainerBoardValidationError(f"board must contain exactly {PHYSICAL_CELL_COUNT} cells")

    multipliers = []
    for cell in cells:
        letters, current_index, multiplier = _cell_parts(cell)
        if not isinstance(letters, (list, tuple)) or len(letters) != LETTER_SLOTS_PER_CELL:
            raise TrainerBoardValidationError(
                f"each cell must contain exactly {LETTER_SLOTS_PER_CELL} letter slots"
            )
        if any(not isinstance(letter, str) or len(letter) != 1 for letter in letters):
            raise TrainerBoardValidationError(
                "each letter must be a non-empty one-character string"
            )
        if (
            not isinstance(current_index, int)
            or isinstance(current_index, bool)
            or not 0 <= current_index < LETTER_SLOTS_PER_CELL
        ):
            raise TrainerBoardValidationError("cell current_index must be between 0 and 4")
        if multiplier is not None:
            multipliers.append(multiplier)

    if len(multipliers) != len(MULTIPLIER_TYPES) or set(multipliers) != set(MULTIPLIER_TYPES):
        raise TrainerBoardValidationError("board must contain exactly one x2, x3, c2, and c3")

    if not isinstance(selected_suffixes, (list, tuple)) or not selected_suffixes:
        raise TrainerBoardValidationError("select between one and three supported suffixes")
    if len(selected_suffixes) > MAX_SELECTED_SUFFIXES:
        raise TrainerBoardValidationError("select at most three suffixes")
    if any(not isinstance(suffix, str) for suffix in selected_suffixes):
        raise TrainerBoardValidationError("selected suffixes must be strings")
    if len(set(selected_suffixes)) != len(selected_suffixes):
        raise TrainerBoardValidationError("selected suffixes must be unique")
    if any(suffix not in SUPPORTED_SUFFIXES for suffix in selected_suffixes):
        raise TrainerBoardValidationError("selected suffixes must be supported")
