"""Bounded Phase-3B role-aware construction and targeted family validation."""

from dataclasses import dataclass
from random import Random

from ..grail_search import find_grail_words
from ..trie import Trie
from ..word_search import calculate_word_score
from .constants import (
    IN_BAND_TARGET_RATIO,
    MULTIPLIER_TYPES,
    PHYSICAL_CELL_COUNT,
    PREFIX_PATH_CANDIDATE_LIMIT,
    PREFIX_PATH_CANDIDATE_NODE_BUDGET,
    ROLE_AWARE_GROUP_ATTEMPTS,
    ROLE_AWARE_MULTIPLIER_LAYOUT_ATTEMPTS,
    ROLE_AWARE_SUFFIX_PATH_CANDIDATE_LIMIT,
    ROLE_AWARE_SUFFIX_PATH_NODE_BUDGET,
    TARGET_DIFFICULTIES,
    TARGET_WORDS_MIN,
    TARGETED_VALIDATION_CANDIDATES,
)
from .economics import ScoredTargetGroup, _role_median_distance, score_target_group
from .generation import (
    LetterRequirements,
    TargetGroupPlan,
    TargetWordPlan,
    _can_require_letter,
    build_candidate_word_index,
    normalize_selected_suffixes,
    seeded_rng,
)
from .processing import classify_suffix_group, neighbour_cells, score_word_with_multipliers


@dataclass(frozen=True)
class ValidatedTargetGroup:
    constructed: ScoredTargetGroup
    actual_word_scores: tuple[tuple[str, int], ...]
    actual_unique_word_count: int
    median_score: float | int | None
    in_band_count: int
    in_band_ratio: float
    fits_target: bool


@dataclass(frozen=True)
class RoleAwareCandidatePlan:
    selected_suffixes: tuple[str, ...]
    seed: int
    multipliers: tuple[str | None, ...]
    requirements: tuple[tuple[str, ...], ...]
    groups: tuple[ScoredTargetGroup, ...]
    exact_group_count: int


def base_word_score(word: str) -> int:
    """Production-compatible no-multiplier baseline used only for ordering."""
    return calculate_word_score(word, [None] * len(word), [])


def role_aware_candidates(words: tuple[str, ...], suffix: str, role: str) -> tuple[str, ...]:
    """Deterministically rank candidates by production baseline, not prefix length alone."""
    if role not in TARGET_DIFFICULTIES:
        raise ValueError("unknown target role")
    scored = [(word, base_word_score(word)) for word in words]
    if role == "WEAK":
        return tuple(
            word
            for word, _score in sorted(scored, key=lambda item: (item[1], len(item[0]), item[0]))
        )
    elif role == "MEDIUM":
        return tuple(
            word
            for word, _score in sorted(
                scored, key=lambda item: (abs(item[1] - 500), -item[1], item[0])
            )
        )
    return tuple(
        word for word, _score in sorted(scored, key=lambda item: (-item[1], -len(item[0]), item[0]))
    )


def find_prefix_path_candidates(
    prefix: str,
    suffix_path: tuple[int, ...],
    requirements: LetterRequirements,
    rng: Random,
    limit: int = PREFIX_PATH_CANDIDATE_LIMIT,
) -> tuple[tuple[int, ...], ...]:
    """Return bounded uncommitted, self-avoiding prefix alternatives."""
    results = []
    nodes_seen = 0
    used = set(suffix_path)
    backwards = []
    reversed_prefix = prefix[::-1]

    def visit(position: int, previous: int):
        nonlocal nodes_seen
        if nodes_seen >= PREFIX_PATH_CANDIDATE_NODE_BUDGET:
            return
        if len(results) >= limit:
            return
        if position == len(reversed_prefix):
            results.append(tuple(reversed(backwards)))
            return
        cells = list(neighbour_cells(previous))
        rng.shuffle(cells)
        for cell in cells:
            nodes_seen += 1
            letter = reversed_prefix[position]
            if cell in used or not _can_require_letter(requirements, cell, letter):
                continue
            used.add(cell)
            backwards.append(cell)
            visit(position + 1, cell)
            backwards.pop()
            used.remove(cell)
            if len(results) >= limit:
                return

    visit(0, suffix_path[0])
    return tuple(results)


def word_role_key(score: int, role: str, path: tuple[int, ...]) -> tuple[object, ...]:
    if role not in TARGET_DIFFICULTIES:
        raise ValueError("unknown target role")
    if role == "WEAK":
        return (score >= 400, max(0, score - 399), path)
    if role == "MEDIUM":
        return (not 400 <= score <= 599, min(abs(score - 400), abs(score - 599)), path)
    return (score < 600, max(0, 600 - score), path)


def multiplier_layout_candidates(seed: int):
    """Yield a small deterministic mix of central heuristics and random legal layouts."""
    rng = seeded_rng(seed)
    seen = set()
    central = (12, 7, 11, 13, 17, 6, 8, 16, 18)
    choices = [central[index : index + 4] for index in range(len(central) - 3)]
    while len(choices) < ROLE_AWARE_MULTIPLIER_LAYOUT_ATTEMPTS:
        choices.append(tuple(rng.sample(range(PHYSICAL_CELL_COUNT), 4)))
    for cells in choices:
        if len(set(cells)) != 4:
            continue
        assignment = [None] * PHYSICAL_CELL_COUNT
        for cell, multiplier in zip(cells, MULTIPLIER_TYPES, strict=True):
            assignment[cell] = multiplier
        result = tuple(assignment)
        if result not in seen:
            seen.add(result)
            yield result
        if len(seen) == ROLE_AWARE_MULTIPLIER_LAYOUT_ATTEMPTS:
            return


def suffix_path_candidates(suffix, role, requirements, existing_paths, multipliers, rng):
    """Return bounded uncommitted suffix paths ordered by soft multiplier exposure."""
    if role not in TARGET_DIFFICULTIES:
        raise ValueError("unknown target role")
    paths = []
    nodes = 0
    for start in rng.sample(range(PHYSICAL_CELL_COUNT), PHYSICAL_CELL_COUNT):
        path, used = [start], {start}

        def visit(position):
            nonlocal nodes
            if (
                nodes >= ROLE_AWARE_SUFFIX_PATH_NODE_BUDGET
                or len(paths) >= ROLE_AWARE_SUFFIX_PATH_CANDIDATE_LIMIT
            ):
                return
            if position == len(suffix):
                candidate = tuple(path)
                if candidate not in existing_paths:
                    paths.append(candidate)
                return
            cells = list(neighbour_cells(path[-1]))
            rng.shuffle(cells)
            for cell in cells:
                nodes += 1
                if cell in used or not _can_require_letter(requirements, cell, suffix[position]):
                    continue
                path.append(cell)
                used.add(cell)
                visit(position + 1)
                used.remove(cell)
                path.pop()

        if _can_require_letter(requirements, start, suffix[0]):
            visit(1)
        if len(paths) >= ROLE_AWARE_SUFFIX_PATH_CANDIDATE_LIMIT:
            break

    def exposure(path):
        value = sum({"x2": 1, "x3": 2, "c2": 3, "c3": 4}.get(multipliers[cell], 0) for cell in path)
        return value if role == "RICH" else -value if role == "WEAK" else -abs(value - 3)

    return tuple(sorted(set(paths), key=lambda path: (-exposure(path), path)))


def generate_role_aware_candidates(selected_suffixes, dictionary_words, seed):
    """Construct up to the validation-finalist budget; does not run targeted validation."""
    suffixes = normalize_selected_suffixes(selected_suffixes)
    pools = build_candidate_word_index(dictionary_words, suffixes)
    rng = seeded_rng(seed)
    finalists = []
    order = sorted(suffixes, key=lambda suffix: (len(pools[suffix]), -len(suffix), suffix))
    for multipliers in multiplier_layout_candidates(rng.randrange(1 << 63)):
        requirements = LetterRequirements()
        paths = {suffix: set() for suffix in suffixes}
        built = []
        for suffix in order:
            for role in ("RICH", "MEDIUM", "WEAK"):
                winner = None
                for suffix_path in suffix_path_candidates(
                    suffix, role, requirements, paths[suffix], multipliers, rng
                ):
                    result = build_role_aware_group(
                        suffix, role, suffix_path, pools[suffix], requirements, multipliers, rng
                    )
                    if result is None:
                        continue
                    group, updated = result
                    scored = score_target_group(group, multipliers, role)
                    key = (
                        scored.fits_target,
                        scored.in_band_ratio,
                        -_role_median_distance(role, scored.median_score),
                    )
                    if winner is None or key > winner[0]:
                        winner = (key, group, updated, scored)
                if winner is None:
                    break
                _key, group, requirements, scored = winner
                paths[suffix].add(group.suffix_path)
                built.append(scored)
            else:
                continue
            break
        else:
            by_suffix = {
                suffix: {item.final_role: item for item in built if item.group.suffix == suffix}
                for suffix in suffixes
            }
            groups = tuple(
                by_suffix[suffix][role] for suffix in suffixes for role in TARGET_DIFFICULTIES
            )
            finalists.append(
                RoleAwareCandidatePlan(
                    suffixes,
                    seed,
                    multipliers,
                    requirements.snapshot(),
                    groups,
                    sum(item.fits_target for item in groups),
                )
            )
    finalists.sort(
        key=lambda plan: (
            -plan.exact_group_count,
            tuple(plan.multipliers.index(multiplier) for multiplier in MULTIPLIER_TYPES),
        )
    )
    return tuple(finalists[:TARGETED_VALIDATION_CANDIDATES])


def build_role_aware_group(
    suffix: str,
    role: str,
    suffix_path: tuple[int, ...],
    candidates: tuple[str, ...],
    requirements: LetterRequirements,
    multipliers: tuple[str | None, ...],
    rng: Random,
) -> tuple[TargetGroupPlan, LetterRequirements] | None:
    """Greedily build eight scored words on a clone; failed work never leaks."""
    best = None
    for _attempt in range(ROLE_AWARE_GROUP_ATTEMPTS):
        tentative = requirements.clone()
        if not tentative.add_path(suffix_path, suffix):
            return None
        words = []
        for word in role_aware_candidates(candidates, suffix, role):
            prefix = word[: -len(suffix)]
            alternatives = find_prefix_path_candidates(prefix, suffix_path, tentative, rng)
            ranked = sorted(
                (
                    (
                        word_role_key(
                            score_word_with_multipliers(word, path + suffix_path, multipliers),
                            role,
                            path,
                        ),
                        path,
                    )
                    for path in alternatives
                ),
                key=lambda item: item[0],
            )
            for _key, prefix_path in ranked:
                if tentative.add_path(prefix_path, prefix):
                    words.append(TargetWordPlan(word, prefix, prefix_path + suffix_path))
                    break
            if len(words) == TARGET_WORDS_MIN:
                group = TargetGroupPlan(suffix, role, suffix_path, tuple(words))
                scored = score_target_group(group, multipliers, role)
                candidate = (
                    scored.fits_target,
                    -(max(0.0, IN_BAND_TARGET_RATIO - scored.in_band_ratio)),
                    -_role_median_distance(role, scored.median_score),
                    group.link_bundle_count,
                    -sum(len(bucket) for bucket in tentative.buckets),
                    tuple(word.full_path for word in group.words),
                    group,
                    tentative,
                )
                if best is None or candidate[:6] > best[:6]:
                    best = candidate
                break
    return None if best is None else (best[6], best[7])


def build_family_trie(dictionary_words, suffixes: tuple[str, ...]) -> Trie:
    """Build one small selected-family Trie for final validation reuse."""
    trie = Trie()
    for word in sorted(
        {word.strip().lower() for word in dictionary_words if isinstance(word, str)}
    ):
        if len(word) <= PHYSICAL_CELL_COUNT and any(
            word.endswith(suffix) and len(word) > len(suffix) for suffix in suffixes
        ):
            trie.insert(word)
    return trie


def targeted_validate_group(
    group: ScoredTargetGroup,
    requirements: LetterRequirements,
    multipliers: tuple[str | None, ...],
    trie: Trie,
) -> ValidatedTargetGroup:
    """Validate reachable selected-family words whose best path has this exact suffix path."""
    # Empty cells stay empty and therefore cannot invent playable letters.
    flat_letters = [set(bucket) for bucket in requirements.buckets]
    grid = [flat_letters[row * 5 : row * 5 + 5] for row in range(5)]
    multiplier_grid = [list(multipliers[row * 5 : row * 5 + 5]) for row in range(5)]
    found = find_grail_words(
        grid,
        multiplier_grid,
        trie,
        suffix_paths=(group.group.suffix_path,),
        allow_empty_cells=True,
    )
    suffix_path = group.group.suffix_path
    scores = []
    for (word, path_key), result in found.items():
        if word.endswith(group.group.suffix) and path_key == suffix_path:
            scores.append((word, result["score"]))
    stats = classify_suffix_group([{"name": word, "score": score} for word, score in scores])
    band = stats["bands"].get(group.final_role, {"count": 0, "ratio": 0.0})
    return ValidatedTargetGroup(
        group,
        tuple(sorted(scores)),
        stats["unique_word_count"],
        stats["median_score"],
        band["count"],
        band["ratio"],
        stats["fits"].get(group.final_role, False),
    )
