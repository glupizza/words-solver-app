"""Pure board representation and deterministic generation primitives."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from random import Random
from typing import Any

from .constants import (
    GENERATOR_VERSION,
    GEOMETRY_PLAN_ATTEMPTS,
    LETTER_SLOTS_PER_CELL,
    MAX_SELECTED_SUFFIXES,
    MULTIPLIER_TYPES,
    PHYSICAL_CELL_COUNT,
    PREFIX_PATH_ATTEMPTS,
    PREFIX_PATH_NODE_BUDGET,
    SUFFIX_PATH_ATTEMPTS,
    SUFFIX_PATH_NODE_BUDGET,
    SUPPORTED_SUFFIXES,
    TARGET_DIFFICULTIES,
    TARGET_GROUP_ATTEMPTS,
    TARGET_WORDS_MAX,
    TARGET_WORDS_MIN,
)


class TrainerBoardValidationError(ValueError):
    """A trainer board does not meet its fixed game invariants."""


class TrainerGenerationError(ValueError):
    """Bounded trainer geometry construction could not meet its constraints."""


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


@dataclass(frozen=True)
class TargetWordPlan:
    name: str
    prefix: str
    full_path: tuple[int, ...]


@dataclass(frozen=True)
class TargetGroupPlan:
    suffix: str
    role: str
    suffix_path: tuple[int, ...]
    words: tuple[TargetWordPlan, ...]

    @property
    def link_bundles(self) -> frozenset[tuple[int, str]]:
        return frozenset(
            (word.full_path[len(word.prefix) - 1], word.prefix[-1]) for word in self.words
        )

    @property
    def link_bundle_count(self) -> int:
        return len(self.link_bundles)


@dataclass(frozen=True)
class TrainerGeometryPlan:
    seed: int
    selected_suffixes: tuple[str, ...]
    groups: tuple[TargetGroupPlan, ...]
    required_letters_by_cell: tuple[tuple[str, ...], ...]


class LetterRequirements:
    """Mutable, transactional per-cell letter requirements used during search."""

    def __init__(self, buckets: Iterable[Iterable[str]] | None = None):
        if buckets is None:
            self.buckets = [set() for _ in range(PHYSICAL_CELL_COUNT)]
        else:
            self.buckets = [set(bucket) for bucket in buckets]
            if len(self.buckets) != PHYSICAL_CELL_COUNT:
                raise ValueError("requirements must contain exactly 25 cell buckets")
            if any(len(bucket) > LETTER_SLOTS_PER_CELL for bucket in self.buckets):
                raise ValueError("a cell cannot require more than five letters")

    def add_path(self, path: Iterable[int], letters: str) -> bool:
        """Atomically merge a letter path, returning False without mutation on overflow."""
        from .processing import validate_physical_path

        normalized_path = validate_physical_path(path)
        if len(normalized_path) != len(letters):
            raise ValueError("path and letters must have equal lengths")
        additions: dict[int, set[str]] = {}
        for cell, letter in zip(normalized_path, letters, strict=True):
            if not isinstance(letter, str) or len(letter) != 1:
                raise ValueError("path letters must be one-character strings")
            additions.setdefault(cell, set()).add(letter)
        if any(
            len(self.buckets[cell] | added) > LETTER_SLOTS_PER_CELL
            for cell, added in additions.items()
        ):
            return False
        for cell, added in additions.items():
            self.buckets[cell].update(added)
        return True

    def snapshot(self) -> tuple[tuple[str, ...], ...]:
        return tuple(tuple(sorted(bucket)) for bucket in self.buckets)

    def clone(self) -> "LetterRequirements":
        """Return an independent copy suitable for a tentative target group."""
        return LetterRequirements(self.snapshot())


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


def normalize_selected_suffixes(selected_suffixes: Iterable[str]) -> tuple[str, ...]:
    """Normalize and validate trainer suffix selection without requiring a board."""
    if isinstance(selected_suffixes, str):
        raise ValueError("selected suffixes must be an iterable of strings")
    try:
        normalized = tuple(suffix.strip().lower() for suffix in selected_suffixes)
    except (AttributeError, TypeError) as exc:
        raise ValueError("selected suffixes must be an iterable of strings") from exc
    if not normalized or len(normalized) > MAX_SELECTED_SUFFIXES:
        raise ValueError("select between one and three supported suffixes")
    if len(set(normalized)) != len(normalized):
        raise ValueError("selected suffixes must be unique")
    if any(suffix not in SUPPORTED_SUFFIXES for suffix in normalized):
        raise ValueError("selected suffixes must be supported")
    return normalized


def normalize_trainer_word(word: str) -> str:
    """Use the lowercase, trimmed form used by the existing Grail word handling."""
    if not isinstance(word, str):
        raise ValueError("dictionary words must be strings")
    return word.strip().lower()


def build_candidate_word_index(
    dictionary_words: Iterable[str], selected_suffixes: Iterable[str]
) -> dict[str, tuple[str, ...]]:
    """Index normalized, board-possible prefix words for requested suffixes."""
    suffixes = normalize_selected_suffixes(selected_suffixes)
    if isinstance(dictionary_words, str):
        raise ValueError("dictionary words must be an iterable of strings")
    try:
        normalized_words = {normalize_trainer_word(word) for word in dictionary_words}
    except TypeError as exc:
        raise ValueError("dictionary words must be an iterable of strings") from exc
    normalized_words.discard("")
    return {
        suffix: tuple(
            sorted(
                word
                for word in normalized_words
                if word.endswith(suffix)
                and len(word) > len(suffix)
                and len(word) <= PHYSICAL_CELL_COUNT
            )
        )
        for suffix in suffixes
    }


def _can_require_letter(requirements: LetterRequirements, cell: int, letter: str) -> bool:
    bucket = requirements.buckets[cell]
    return letter in bucket or len(bucket) < LETTER_SLOTS_PER_CELL


def _find_suffix_path(
    suffix: str,
    requirements: LetterRequirements,
    existing_paths: set[tuple[int, ...]],
    rng: Random,
) -> tuple[int, ...] | None:
    """Find and commit one suffix path, bounded by ``SUFFIX_PATH_ATTEMPTS``."""
    from .processing import neighbour_cells

    for _attempt in range(SUFFIX_PATH_ATTEMPTS):
        nodes_seen = 0
        starts = list(range(PHYSICAL_CELL_COUNT))
        rng.shuffle(starts)
        for start in starts:
            if not _can_require_letter(requirements, start, suffix[0]):
                continue
            path = [start]
            used = {start}

            def extend(position: int) -> tuple[int, ...] | None:
                nonlocal nodes_seen
                if nodes_seen >= SUFFIX_PATH_NODE_BUDGET:
                    return None
                if position == len(suffix):
                    candidate = tuple(path)
                    if candidate in existing_paths:
                        return None
                    return candidate if requirements.add_path(candidate, suffix) else None
                choices = list(neighbour_cells(path[-1]))
                rng.shuffle(choices)
                for cell in choices:
                    nodes_seen += 1
                    if cell in used or not _can_require_letter(
                        requirements, cell, suffix[position]
                    ):
                        continue
                    path.append(cell)
                    used.add(cell)
                    found = extend(position + 1)
                    if found is not None:
                        return found
                    used.remove(cell)
                    path.pop()
                return None

            found = extend(1)
            if found is not None:
                return found
    return None


def _find_prefix_path(
    prefix: str,
    suffix_path: tuple[int, ...],
    requirements: LetterRequirements,
    rng: Random,
) -> tuple[int, ...] | None:
    """Search backwards from a suffix attachment and commit a compatible prefix."""
    from .processing import neighbour_cells

    reversed_prefix = prefix[::-1]
    for _attempt in range(PREFIX_PATH_ATTEMPTS):
        nodes_seen = 0
        used = set(suffix_path)
        backwards_path: list[int] = []

        def extend(position: int, previous: int) -> tuple[int, ...] | None:
            nonlocal nodes_seen
            if nodes_seen >= PREFIX_PATH_NODE_BUDGET:
                return None
            if position == len(reversed_prefix):
                prefix_path = tuple(reversed(backwards_path))
                return prefix_path if requirements.add_path(prefix_path, prefix) else None
            choices = list(neighbour_cells(previous))
            rng.shuffle(choices)
            letter = reversed_prefix[position]
            for cell in choices:
                nodes_seen += 1
                if cell in used or not _can_require_letter(requirements, cell, letter):
                    continue
                backwards_path.append(cell)
                used.add(cell)
                found = extend(position + 1, cell)
                if found is not None:
                    return found
                used.remove(cell)
                backwards_path.pop()
            return None

        found = extend(0, suffix_path[0])
        if found is not None:
            return found
    return None


def _ordered_candidates(words: tuple[str, ...], suffix: str, rng: Random) -> list[str]:
    """Prefer shorter prefixes while giving deterministic seeded tie variation."""
    decorated = [(len(word) - len(suffix), rng.random(), word) for word in words]
    return [word for _length, _tie, word in sorted(decorated)]


def _build_group_words(
    suffix: str,
    suffix_path: tuple[int, ...],
    candidates: tuple[str, ...],
    requirements: LetterRequirements,
    rng: Random,
) -> tuple[TargetWordPlan, ...] | None:
    selected = []
    for word in _ordered_candidates(candidates, suffix, rng):
        prefix = word[: -len(suffix)]
        prefix_path = _find_prefix_path(prefix, suffix_path, requirements, rng)
        if prefix_path is None:
            continue
        selected.append(TargetWordPlan(word, prefix, prefix_path + suffix_path))
        if len(selected) == TARGET_WORDS_MIN:
            # Eight is the product requirement. Extra words are deliberately
            # left for a later optimization phase rather than consuming scarce
            # capacity needed by downstream target groups.
            return tuple(selected)
    return None


def _try_build_target_group(
    suffix: str,
    role: str,
    candidates: tuple[str, ...],
    committed_requirements: LetterRequirements,
    committed_suffix_paths: set[tuple[int, ...]],
    rng: Random,
) -> tuple[TargetGroupPlan, LetterRequirements] | None:
    """Build one whole group on a copy; return it only when all eight words fit."""
    for _attempt in range(TARGET_GROUP_ATTEMPTS):
        tentative_requirements = committed_requirements.clone()
        suffix_path = _find_suffix_path(suffix, tentative_requirements, committed_suffix_paths, rng)
        if suffix_path is None:
            continue
        words = _build_group_words(suffix, suffix_path, candidates, tentative_requirements, rng)
        if words is not None:
            return TargetGroupPlan(suffix, role, suffix_path, words), tentative_requirements
    return None


def generate_geometry_plan(
    selected_suffixes: Iterable[str], dictionary_words: Iterable[str], seed: int
) -> TrainerGeometryPlan:
    """Construct Phase-2 suffix and word geometry without scoring or board filling."""
    suffixes = normalize_selected_suffixes(selected_suffixes)
    candidates_by_suffix = build_candidate_word_index(dictionary_words, suffixes)
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("trainer seed must be an integer")
    for suffix, candidates in candidates_by_suffix.items():
        if len(candidates) < TARGET_WORDS_MIN:
            raise TrainerGenerationError(f"suffix {suffix!r} has fewer than 8 candidate words")

    generation_suffixes = tuple(
        sorted(
            suffixes,
            key=lambda suffix: (
                len(candidates_by_suffix[suffix]),
                -len(suffix),
                suffix,
            ),
        )
    )

    rng = seeded_rng(seed)
    last_failure = "unknown geometry failure"
    for _plan_attempt in range(GEOMETRY_PLAN_ATTEMPTS):
        requirements = LetterRequirements()
        groups_by_suffix: dict[str, list[TargetGroupPlan]] = {suffix: [] for suffix in suffixes}
        suffix_paths: dict[str, set[tuple[int, ...]]] = {suffix: set() for suffix in suffixes}
        for suffix in generation_suffixes:
            for role in TARGET_DIFFICULTIES:
                built_group = _try_build_target_group(
                    suffix,
                    role,
                    candidates_by_suffix[suffix],
                    requirements,
                    suffix_paths[suffix],
                    rng,
                )
                if built_group is None:
                    last_failure = f"could not place 8 words for suffix {suffix!r} role {role}"
                    break
                group, requirements = built_group
                suffix_paths[suffix].add(group.suffix_path)
                groups_by_suffix[suffix].append(group)
            else:
                continue
            break
        else:
            groups = tuple(group for suffix in suffixes for group in groups_by_suffix[suffix])
            plan = TrainerGeometryPlan(seed, suffixes, groups, requirements.snapshot())
            validate_geometry_plan(plan)
            return plan
    raise TrainerGenerationError(
        f"geometry generation failed after {GEOMETRY_PLAN_ATTEMPTS} attempts: {last_failure}"
    )


def validate_geometry_plan(plan: TrainerGeometryPlan) -> None:
    """Verify Phase-2 plan invariants independently of HTTP or Flask."""
    from .processing import validate_physical_path

    if not isinstance(plan, TrainerGeometryPlan):
        raise ValueError("plan must be a TrainerGeometryPlan")
    suffixes = normalize_selected_suffixes(plan.selected_suffixes)
    if len(plan.required_letters_by_cell) != PHYSICAL_CELL_COUNT:
        raise ValueError("plan must contain exactly 25 requirement buckets")
    requirements = tuple(set(bucket) for bucket in plan.required_letters_by_cell)
    if any(
        len(original) != len(bucket)
        or len(bucket) > LETTER_SLOTS_PER_CELL
        or any(not isinstance(letter, str) or len(letter) != 1 for letter in bucket)
        for original, bucket in zip(plan.required_letters_by_cell, requirements, strict=True)
    ):
        raise ValueError("requirement buckets must contain at most five one-character letters")

    by_suffix: dict[str, list[TargetGroupPlan]] = {suffix: [] for suffix in suffixes}
    for group in plan.groups:
        if group.suffix not in by_suffix or group.role not in TARGET_DIFFICULTIES:
            raise ValueError("group has an unsupported suffix or role")
        by_suffix[group.suffix].append(group)
        suffix_path = validate_physical_path(group.suffix_path)
        if len(suffix_path) != len(group.suffix):
            raise ValueError("suffix path length must match suffix")
        if any(
            letter not in requirements[cell]
            for cell, letter in zip(suffix_path, group.suffix, strict=True)
        ):
            raise ValueError("suffix path letters must be required by their cells")
        if not TARGET_WORDS_MIN <= len(group.words) <= TARGET_WORDS_MAX:
            raise ValueError("each target group must contain 8 to 10 words")
        if len({word.name for word in group.words}) != len(group.words):
            raise ValueError("target word names must be unique within a group")
        for word in group.words:
            if not word.prefix:
                raise ValueError("target word prefix must not be empty")
            if not word.name.endswith(group.suffix) or word.prefix + group.suffix != word.name:
                raise ValueError("target word must equal prefix plus its group suffix")
            full_path = validate_physical_path(word.full_path)
            if len(full_path) != len(word.name) or full_path[-len(group.suffix) :] != suffix_path:
                raise ValueError("word path must end with its exact suffix path")
            if any(
                letter not in requirements[cell]
                for cell, letter in zip(full_path, word.name, strict=True)
            ):
                raise ValueError("word path letters must be required by their cells")
    for suffix, groups in by_suffix.items():
        if len(groups) != len(TARGET_DIFFICULTIES) or {group.role for group in groups} != set(
            TARGET_DIFFICULTIES
        ):
            raise ValueError(f"suffix {suffix!r} must have exactly one group per role")
        if len({group.suffix_path for group in groups}) != len(TARGET_DIFFICULTIES):
            raise ValueError(f"suffix {suffix!r} must have three distinct suffix paths")
