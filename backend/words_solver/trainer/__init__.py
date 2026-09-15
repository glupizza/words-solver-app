"""Flask-independent Grail Trainer domain foundation."""

from .generation import (
    TrainerBoard,
    TrainerBoardValidationError,
    TrainerCell,
    seeded_rng,
    validate_trainer_board,
)
from .processing import classify_suffix_group, score_word_for_path, validate_physical_path

__all__ = (
    "TrainerBoard",
    "TrainerBoardValidationError",
    "TrainerCell",
    "classify_suffix_group",
    "score_word_for_path",
    "seeded_rng",
    "validate_physical_path",
    "validate_trainer_board",
)
