"""Reusable production processing for five-image Grail boards."""

import time
from collections import Counter

import cv2

from .grail_search import GRID_SIZE, find_grail_words
from .image_processing import TRANSLIT_TO_RUS, crop_board_image, recognize_board_cells

IMAGE_COUNT = 5
MAX_WORDS = 500
MAX_SERIES = 50
MAX_SERIES_WORDS = 10
MIN_SERIES_SUFFIX_LENGTH = 6
MIN_WORD_SCORE = 400
MIN_GOOD_WORDS = 3
NESTED_TOP5_PRESERVE_RATIO = 0.95
PRIORITY_SERIES_SUFFIXES = (
    "\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435",
    "\u0438\u0440\u043e\u0432\u0430\u0442\u044c\u0441\u044f",
    "\u0438\u0440\u043e\u0432\u0430\u0442\u044c",
    "\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0439",
    "\u0438\u0440\u043e\u0432\u043a\u0430",
    "\u0441\u0442\u0440\u043e\u0435\u043d\u0438\u0435",
    "\u0432\u0430\u0440\u0438\u0432\u0430\u043d\u0438\u0435",
    "\u043e\u0431\u0440\u0430\u0437\u043e\u0432\u0430\u043d\u0438\u0435",
)


class GrailMultiplierConflict(ValueError):
    """OCR observations disagree about a fixed Grail multiplier."""


def _require_five_boards(boards, name):
    if len(boards) != IMAGE_COUNT:
        raise ValueError(f"{name} must contain exactly five 5x5 boards")
    if any(
        len(board) != GRID_SIZE or any(len(row) != GRID_SIZE for row in board) for board in boards
    ):
        raise ValueError(f"each {name} board must be 5x5")


def merge_cell_letters(boards):
    _require_five_boards(boards, "letter")
    return [
        [{board[row][col] for board in boards} for col in range(GRID_SIZE)]
        for row in range(GRID_SIZE)
    ]


def merge_multipliers(grids):
    _require_five_boards(grids, "multiplier")
    merged = [[None for _col in range(GRID_SIZE)] for _row in range(GRID_SIZE)]
    sightings = [[{} for _col in range(GRID_SIZE)] for _row in range(GRID_SIZE)]
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            counts = dict(
                sorted(Counter(grid[row][col] for grid in grids if grid[row][col]).items())
            )
            sightings[row][col] = counts
            if len(counts) > 1:
                raise GrailMultiplierConflict(
                    f"multiplier inconsistency at R{row + 1}C{col + 1}: {counts}"
                )
            merged[row][col] = next(iter(counts), None)
    return merged, sightings


def unique_letter_statistics(cell_letters):
    counts = [len(cell) for row in cell_letters for cell in row]
    return {
        "avg_unique_letters_per_cell": sum(counts) / len(counts),
        "min_unique_letters_per_cell": min(counts),
        "max_unique_letters_per_cell": max(counts),
        "distribution": dict(sorted(Counter(counts).items())),
    }


def serialize_word(result):
    return {
        "name": result["name"],
        "score": result["score"],
        "path": [row * GRID_SIZE + col for row, col, _letter in result["path"]],
    }


def top_words(results, limit=MAX_WORDS):
    return [
        serialize_word(result)
        for result in sorted(results.values(), key=lambda item: (-item["score"], item["name"]))[
            :limit
        ]
    ]


def _series_metrics(suffix, suffix_path, members):
    members = sorted(members, key=lambda item: (-item["score"], item["name"]))
    scores = [member["score"] for member in members]
    return {
        "suffix": suffix,
        "suffix_length": len(suffix),
        "suffix_path": list(suffix_path),
        "good_members": members,
        "good_count": len(members),
        "best_score": scores[0],
        "top3_sum": sum(scores[:3]),
        "top5_sum": sum(scores[:5]),
    }


def build_series(results, min_suffix_length=MIN_SERIES_SUFFIX_LENGTH):
    min_suffix_length = max(min_suffix_length, MIN_SERIES_SUFFIX_LENGTH)
    candidates = {}
    for result in results.values():
        word = result["name"]
        path = tuple(row * GRID_SIZE + col for row, col, _letter in result["path"])
        for length in range(min_suffix_length, len(word) + 1):
            candidates.setdefault((word[-length:], path[-length:]), []).append(result)
    groups = [item for item in candidates.items() if len(item[1]) >= 2]
    specific = {}
    priority_candidates = {}
    for (suffix, path), members in groups:
        if suffix in PRIORITY_SERIES_SUFFIXES:
            priority_candidates[(suffix, path)] = (suffix, path, members)
        key = frozenset(member["name"] for member in members)
        existing = specific.get(key)
        if existing is None or (len(suffix), suffix, path) > (
            len(existing[0]),
            existing[0],
            existing[1],
        ):
            specific[key] = (suffix, path, members)
    selected_candidates = list(specific.values())
    selected_keys = {(suffix, path) for suffix, path, _members in selected_candidates}
    selected_candidates.extend(
        candidate for key, candidate in priority_candidates.items() if key not in selected_keys
    )
    return [
        _series_metrics(suffix, path, [m for m in members if m["score"] >= MIN_WORD_SCORE])
        for suffix, path, members in selected_candidates
        if sum(m["score"] >= MIN_WORD_SCORE for m in members) >= MIN_GOOD_WORDS
    ]


def _ranking_key(series):
    return (
        -series["top3_sum"],
        -series["top5_sum"],
        -series["good_count"],
        -series["suffix_length"],
        series["suffix"],
        series["suffix_path"],
    )


def _suppresses(longer, shorter):
    return (
        longer["suffix_length"] > shorter["suffix_length"]
        and longer["suffix"].endswith(shorter["suffix"])
        and longer["suffix_path"][-shorter["suffix_length"] :] == shorter["suffix_path"]
        and [member["name"] for member in longer["good_members"][:3]]
        == [member["name"] for member in shorter["good_members"][:3]]
        and longer["top5_sum"] >= shorter["top5_sum"] * NESTED_TOP5_PRESERVE_RATIO
    )


def select_series(results, min_suffix_length=MIN_SERIES_SUFFIX_LENGTH):
    candidates = build_series(results, min_suffix_length)

    ordered = sorted(
        candidates,
        key=lambda series: (-series["suffix_length"],) + _ranking_key(series),
    )

    selected = []
    for candidate in ordered:
        if candidate["suffix"] not in PRIORITY_SERIES_SUFFIXES and any(
            _suppresses(longer, candidate) for longer in selected
        ):
            continue
        selected.append(candidate)

    priority = [
        candidate
        for suffix in PRIORITY_SERIES_SUFFIXES
        for candidate in selected
        if candidate["suffix"] == suffix
    ]
    normal = sorted(
        (
            candidate
            for candidate in selected
            if candidate["suffix"] not in PRIORITY_SERIES_SUFFIXES
        ),
        key=_ranking_key,
    )
    return (priority + normal)[:MAX_SERIES]


def serialize_series(series):
    score_ranked_members = series["good_members"]
    members = (
        score_ranked_members
        if series["suffix"] in PRIORITY_SERIES_SUFFIXES
        else score_ranked_members[:MAX_SERIES_WORDS]
    )
    members = sorted(
        members, key=lambda member: (len(member["name"]), member["score"], member["name"])
    )
    return {
        "suffix": series["suffix"],
        "suffix_path": series["suffix_path"],
        "good_count": series["good_count"],
        "best_score": series["best_score"],
        "top3_sum": series["top3_sum"],
        "top5_sum": series["top5_sum"],
        "words": [serialize_word(member) for member in members],
    }


def _recognize_path(path, model):
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"could not read image: {path}")
    board, _details = crop_board_image(image)
    if board.size == 0:
        raise ValueError(f"production crop is empty: {path}")
    recognition = recognize_board_cells(board, model)
    letters = [
        [TRANSLIT_TO_RUS.get(letter, letter) for letter, _multiplier in row]
        for row in recognition["board"]
    ]
    multipliers = [[None for _col in range(GRID_SIZE)] for _row in range(GRID_SIZE)]
    for (row, col), multiplier in recognition["multipliers"].items():
        multipliers[row][col] = multiplier
    return letters, multipliers


def process_grail_images(paths, model, trie):
    if len(paths) != IMAGE_COUNT:
        raise ValueError("exactly five images are required")
    started = time.perf_counter()
    ocr_started = time.perf_counter()
    recognized = [_recognize_path(path, model) for path in paths]
    ocr_seconds = time.perf_counter() - ocr_started
    merge_started = time.perf_counter()
    letters = merge_cell_letters([item[0] for item in recognized])
    multipliers, _sightings = merge_multipliers([item[1] for item in recognized])
    merge_seconds = time.perf_counter() - merge_started
    search_started = time.perf_counter()
    results = find_grail_words(letters, multipliers, trie)
    search_seconds = time.perf_counter() - search_started
    series_started = time.perf_counter()
    series = select_series(results)
    series_seconds = time.perf_counter() - series_started
    return {
        "words": top_words(results),
        "series": [serialize_series(item) for item in series],
        "meta": {
            "total_found": len(results),
            "returned_words": min(len(results), MAX_WORDS),
            "returned_series": len(series),
        },
        "timings": {
            "ocr_all_5_seconds": ocr_seconds,
            "merge_seconds": merge_seconds,
            "grail_search_seconds": search_seconds,
            "series_processing_seconds": series_seconds,
            "request_core_seconds": time.perf_counter() - started,
        },
        "debug": {
            "cell_letters": letters,
            "multipliers": multipliers,
            "unique_letter_statistics": unique_letter_statistics(letters),
        },
    }
