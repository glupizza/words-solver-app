"""Flask-independent Grail Trainer domain foundation."""

from .generation import (
    LetterRequirements,
    TargetGroupPlan,
    TargetWordPlan,
    TrainerBoard,
    TrainerBoardValidationError,
    TrainerCell,
    TrainerGenerationError,
    TrainerGeometryPlan,
    build_candidate_word_index,
    generate_geometry_plan,
    normalize_selected_suffixes,
    seeded_rng,
    validate_geometry_plan,
    validate_trainer_board,
)
from .processing import classify_suffix_group, score_word_for_path, validate_physical_path

__all__ = (
    "LetterRequirements",
    "TargetGroupPlan",
    "TargetWordPlan",
    "TrainerBoard",
    "TrainerBoardValidationError",
    "TrainerGenerationError",
    "TrainerGeometryPlan",
    "TrainerCell",
    "build_candidate_word_index",
    "classify_suffix_group",
    "generate_geometry_plan",
    "normalize_selected_suffixes",
    "score_word_for_path",
    "seeded_rng",
    "validate_physical_path",
    "validate_geometry_plan",
    "validate_trainer_board",
)
