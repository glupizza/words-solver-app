"""Phase-3A bounded economic scoring for already-valid trainer geometry."""

from collections import Counter
from dataclasses import dataclass
from itertools import permutations
from random import Random

from .constants import (
    ECONOMIC_GEOMETRY_ATTEMPTS,
    IN_BAND_TARGET_RATIO,
    MULTIPLIER_PLACEMENT_ATTEMPTS,
    MULTIPLIER_TYPES,
    PHYSICAL_CELL_COUNT,
    ROLE_SEPARATION_TARGET,
    TARGET_DIFFICULTIES,
)
from .generation import (
    TargetGroupPlan,
    TrainerGenerationError,
    TrainerGeometryPlan,
    generate_geometry_plan,
    normalize_selected_suffixes,
    seeded_rng,
)
from .processing import (
    classify_suffix_group,
    score_word_with_multipliers,
    validate_multiplier_assignment,
)


@dataclass(frozen=True)
class ScoredTargetGroup:
    group: TargetGroupPlan
    final_role: str
    word_scores: tuple[tuple[str, int], ...]
    median_score: float | int | None
    in_band_count: int
    in_band_ratio: float
    fits_target: bool


@dataclass(frozen=True)
class EconomicQuality:
    exact_group_count: int
    total_group_count: int
    total_ratio_deficit: float
    total_median_distance: float
    total_separation_deficit: float


@dataclass(frozen=True)
class TrainerEconomicPlan:
    geometry: TrainerGeometryPlan
    multipliers: tuple[str | None, ...]
    groups: tuple[ScoredTargetGroup, ...]
    exact_targets_met: bool
    quality: EconomicQuality

    @property
    def multiplier_cells(self) -> dict[str, int]:
        return {multiplier: self.multipliers.index(multiplier) for multiplier in MULTIPLIER_TYPES}

    @property
    def degraded(self) -> bool:
        return not self.exact_targets_met


def _role_median_distance(role: str, median_score: float | int | None) -> float:
    if median_score is None:
        return float("inf")
    if role == "WEAK":
        return max(0, median_score - 399)
    if role == "MEDIUM":
        if median_score < 400:
            return 400 - median_score
        return max(0, median_score - 599)
    if role == "RICH":
        return max(0, 600 - median_score)
    raise ValueError("unknown target role")


def _role_ratio_deficit(ratio: float) -> float:
    return max(0.0, IN_BAND_TARGET_RATIO - ratio)


def score_target_group(
    group: TargetGroupPlan, multipliers: tuple[str | None, ...], desired_role: str
) -> ScoredTargetGroup:
    """Score one concrete target group with production multiplier semantics."""
    if desired_role not in TARGET_DIFFICULTIES:
        raise ValueError("unknown target role")
    word_scores, statistics = _score_group_statistics(group, multipliers)
    in_band = statistics["bands"][desired_role]
    return ScoredTargetGroup(
        group=group,
        final_role=desired_role,
        word_scores=word_scores,
        median_score=statistics["median_score"],
        in_band_count=in_band["count"],
        in_band_ratio=in_band["ratio"],
        fits_target=statistics["fits"][desired_role],
    )


def _score_group_statistics(group: TargetGroupPlan, multipliers: tuple[str | None, ...]):
    """Score once per physical group; role permutations only reinterpret its stats."""
    assignment = validate_multiplier_assignment(multipliers)
    word_scores = tuple(
        (word.name, score_word_with_multipliers(word.name, word.full_path, assignment))
        for word in group.words
    )
    statistics = classify_suffix_group(
        [{"name": name, "score": score} for name, score in word_scores]
    )
    return word_scores, statistics


def _with_role(group: TargetGroupPlan, word_scores, statistics, role: str) -> ScoredTargetGroup:
    in_band = statistics["bands"][role]
    return ScoredTargetGroup(
        group=group,
        final_role=role,
        word_scores=word_scores,
        median_score=statistics["median_score"],
        in_band_count=in_band["count"],
        in_band_ratio=in_band["ratio"],
        fits_target=statistics["fits"][role],
    )


def _suffix_quality(groups: tuple[ScoredTargetGroup, ...]) -> EconomicQuality:
    by_role = {group.final_role: group for group in groups}
    weak_median = by_role["WEAK"].median_score
    medium_median = by_role["MEDIUM"].median_score
    rich_median = by_role["RICH"].median_score
    separation_deficit = max(0, ROLE_SEPARATION_TARGET - (medium_median - weak_median)) + max(
        0, ROLE_SEPARATION_TARGET - (rich_median - medium_median)
    )
    return EconomicQuality(
        exact_group_count=sum(group.fits_target for group in groups),
        total_group_count=len(groups),
        total_ratio_deficit=sum(_role_ratio_deficit(group.in_band_ratio) for group in groups),
        total_median_distance=sum(
            _role_median_distance(group.final_role, group.median_score) for group in groups
        ),
        total_separation_deficit=separation_deficit,
    )


def _group_tie_signature(
    groups: tuple[ScoredTargetGroup, ...],
) -> tuple[tuple[str, tuple[int, ...]], ...]:
    return tuple(
        (role, next(group.group.suffix_path for group in groups if group.final_role == role))
        for role in TARGET_DIFFICULTIES
    )


def _quality_key(quality: EconomicQuality, tie_signature: tuple[object, ...]) -> tuple[object, ...]:
    """Lexicographic priority: fits, ratio, median, separation, stable ties."""
    return (
        -quality.exact_group_count,
        quality.total_ratio_deficit,
        quality.total_median_distance,
        quality.total_separation_deficit,
        tie_signature,
    )


def assign_roles_for_suffix(
    groups: tuple[TargetGroupPlan, ...], multipliers: tuple[str | None, ...]
) -> tuple[tuple[ScoredTargetGroup, ...], EconomicQuality]:
    """Evaluate every role permutation for one suffix and retain the best one."""
    if len(groups) != len(TARGET_DIFFICULTIES) or len({group.suffix for group in groups}) != 1:
        raise ValueError("role assignment requires exactly three groups of one suffix")
    scored_by_group = {group: _score_group_statistics(group, multipliers) for group in groups}
    best: tuple[tuple[ScoredTargetGroup, ...], EconomicQuality] | None = None
    best_key: tuple[object, ...] | None = None
    for ordered_groups in permutations(groups):
        scored = tuple(
            _with_role(group, *scored_by_group[group], role)
            for group, role in zip(ordered_groups, TARGET_DIFFICULTIES, strict=True)
        )
        quality = _suffix_quality(scored)
        key = _quality_key(quality, _group_tie_signature(scored))
        if best_key is None or key < best_key:
            best = (scored, quality)
            best_key = key
    if best is None:  # pragma: no cover - permutations of three groups is never empty
        raise TrainerGenerationError("could not assign economic roles")
    return best


def _assignment_from_cells(
    cells: tuple[int, ...], types: tuple[str, ...]
) -> tuple[str | None, ...]:
    assignment: list[str | None] = [None] * PHYSICAL_CELL_COUNT
    for cell, multiplier in zip(cells, types, strict=True):
        assignment[cell] = multiplier
    return tuple(assignment)


def _placement_candidates(geometry: TrainerGeometryPlan, rng: Random):
    coverage = Counter(
        cell for group in geometry.groups for word in group.words for cell in word.full_path
    )
    ranked_cells = sorted(range(PHYSICAL_CELL_COUNT), key=lambda cell: (-coverage[cell], cell))
    seen = set()

    def add(cells: tuple[int, ...], types: tuple[str, ...]):
        assignment = _assignment_from_cells(cells, types)
        if assignment not in seen:
            seen.add(assignment)
            return assignment
        return None

    # Coverage-ranked rotations supply understandable high-impact candidates.
    for offset in range(PHYSICAL_CELL_COUNT):
        cells = tuple(ranked_cells[(offset + step * 6) % PHYSICAL_CELL_COUNT] for step in range(4))
        if len(set(cells)) == 4:
            for type_order in permutations(MULTIPLIER_TYPES):
                candidate = add(cells, type_order)
                if candidate is not None:
                    yield candidate
                    if len(seen) >= MULTIPLIER_PLACEMENT_ATTEMPTS:
                        return

    # Seeded samples retain every board cell as a possible low-impact choice.
    while len(seen) < MULTIPLIER_PLACEMENT_ATTEMPTS:
        cells = tuple(rng.sample(range(PHYSICAL_CELL_COUNT), len(MULTIPLIER_TYPES)))
        types = tuple(rng.sample(MULTIPLIER_TYPES, len(MULTIPLIER_TYPES)))
        candidate = add(cells, types)
        if candidate is not None:
            yield candidate


def optimize_multiplier_placement(geometry: TrainerGeometryPlan, seed: int) -> TrainerEconomicPlan:
    """Find the best bounded global placement for one fixed geometry plan."""
    rng = seeded_rng(seed)
    by_suffix = {
        suffix: tuple(group for group in geometry.groups if group.suffix == suffix)
        for suffix in geometry.selected_suffixes
    }
    best_plan: TrainerEconomicPlan | None = None
    best_key: tuple[object, ...] | None = None
    for assignment in _placement_candidates(geometry, rng):
        scored_groups = []
        qualities = []
        for suffix in geometry.selected_suffixes:
            scored, quality = assign_roles_for_suffix(by_suffix[suffix], assignment)
            scored_groups.extend(scored)
            qualities.append(quality)
        combined = EconomicQuality(
            exact_group_count=sum(quality.exact_group_count for quality in qualities),
            total_group_count=sum(quality.total_group_count for quality in qualities),
            total_ratio_deficit=sum(quality.total_ratio_deficit for quality in qualities),
            total_median_distance=sum(quality.total_median_distance for quality in qualities),
            total_separation_deficit=sum(quality.total_separation_deficit for quality in qualities),
        )
        plan = TrainerEconomicPlan(
            geometry=geometry,
            multipliers=assignment,
            groups=tuple(scored_groups),
            exact_targets_met=combined.exact_group_count == combined.total_group_count,
            quality=combined,
        )
        tie_signature = (
            tuple(
                _group_tie_signature(
                    tuple(group for group in plan.groups if group.group.suffix == suffix)
                )
                for suffix in geometry.selected_suffixes
            ),
            tuple(plan.multiplier_cells[multiplier] for multiplier in MULTIPLIER_TYPES),
        )
        key = _quality_key(combined, tie_signature)
        if best_key is None or key < best_key:
            best_plan = plan
            best_key = key
        if plan.exact_targets_met:
            return plan
    if best_plan is None:  # pragma: no cover - bounded candidate stream always yields candidates
        raise TrainerGenerationError("could not evaluate multiplier placements")
    return best_plan


def generate_economic_plan(selected_suffixes, dictionary_words, seed: int) -> TrainerEconomicPlan:
    """Evaluate a bounded set of geometries and return the best exact or degraded plan."""
    suffixes = normalize_selected_suffixes(selected_suffixes)
    words = tuple(dictionary_words)
    rng = seeded_rng(seed)
    best_plan: TrainerEconomicPlan | None = None
    best_key: tuple[object, ...] | None = None
    failures = []
    for _attempt in range(ECONOMIC_GEOMETRY_ATTEMPTS):
        geometry_seed = rng.randrange(1 << 63)
        multiplier_seed = rng.randrange(1 << 63)
        try:
            geometry = generate_geometry_plan(suffixes, words, geometry_seed)
        except TrainerGenerationError as exc:
            failures.append(str(exc))
            continue
        plan = optimize_multiplier_placement(geometry, multiplier_seed)
        key = _quality_key(
            plan.quality,
            (
                tuple(plan.multiplier_cells[multiplier] for multiplier in MULTIPLIER_TYPES),
                geometry.seed,
            ),
        )
        if best_key is None or key < best_key:
            best_plan = plan
            best_key = key
        if plan.exact_targets_met:
            return plan
    if best_plan is not None:
        return best_plan
    detail = failures[-1] if failures else "no geometry candidates"
    raise TrainerGenerationError(f"economic generation failed: {detail}")
