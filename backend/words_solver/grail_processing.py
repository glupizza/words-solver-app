"""Reusable production processing for five-image Grail boards."""

import time
from collections import Counter

import cv2

from .grail_constants import (
    GRAIL_SERIES_SUFFIXES,
    MIN_GRAIL_SERIES_WORD_SCORE,
    PRIORITY_SERIES_SUFFIXES,
)
from .grail_search import GRID_SIZE, find_grail_words
from .image_processing import TRANSLIT_TO_RUS, crop_board_image, recognize_board_cells

IMAGE_COUNT = 5
MAX_WORDS = 500
MIN_GOOD_WORDS = 8


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


def priority_dictionary_words(words):
    """Return dictionary entries eligible for the startup priority Trie."""
    return [
        word
        for word in words
        if isinstance(word, str) and word.lower().endswith(PRIORITY_SERIES_SUFFIXES)
    ]


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
    unique = {}
    for member in members:
        existing = unique.get(member["name"])
        if existing is None or member["score"] > existing["score"]:
            unique[member["name"]] = member
    members = sorted(unique.values(), key=lambda item: (-item["score"], item["name"]))
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
        "average_score": sum(scores) / len(scores),
    }


def build_series(results):
    candidates = {}
    for result in results.values():
        if result["score"] <= MIN_GRAIL_SERIES_WORD_SCORE:
            continue
        word = result["name"]
        path = tuple(row * GRID_SIZE + col for row, col, _letter in result["path"])
        for suffix in GRAIL_SERIES_SUFFIXES:
            if word.endswith(suffix) and len(path) >= len(suffix):
                candidates.setdefault((suffix, path[-len(suffix) :]), []).append(result)
    return [
        _series_metrics(suffix, path, members)
        for (suffix, path), members in candidates.items()
        if len({member["name"] for member in members}) >= MIN_GOOD_WORDS
    ]


def _ranking_key(series):
    return (
        -series["good_count"],
        -sum(member["score"] for member in series["good_members"][:8]),
        -series["average_score"],
        tuple(series["suffix_path"]),
    )


def _display_members(series):
    def key(member):
        prefix_length = len(member["name"]) - series["suffix_length"]
        prefix = member["path"][:prefix_length]
        reverse_route = tuple(
            (row * GRID_SIZE + col, letter) for row, col, letter in reversed(prefix)
        )
        return reverse_route, -member["score"], member["name"]

    return sorted(series["good_members"], key=key)


def select_series(results):
    candidates = build_series(results)
    chosen = {}
    assigned = set()
    # Specific endings claim words only after an eligible route survives deduplication.
    for suffix in sorted(
        GRAIL_SERIES_SUFFIXES, key=lambda item: (-len(item), GRAIL_SERIES_SUFFIXES.index(item))
    ):
        paths = [item for item in candidates if item["suffix"] == suffix]
        routes = []
        for _ in range(2):
            remaining = []
            for item in paths:
                members = [
                    member for member in item["good_members"] if member["name"] not in assigned
                ]
                if len(members) >= MIN_GOOD_WORDS:
                    remaining.append(_series_metrics(suffix, item["suffix_path"], members))
            if not remaining:
                break
            best = min(remaining, key=_ranking_key)
            best["display_members"] = _display_members(best)
            routes.append(best)
            assigned.update(member["name"] for member in best["good_members"])
            paths = [item for item in paths if item["suffix_path"] != best["suffix_path"]]
        if routes:
            chosen[suffix] = {"suffix": suffix, "routes": routes}
    return [chosen[suffix] for suffix in GRAIL_SERIES_SUFFIXES if suffix in chosen]


def serialize_series(series):
    routes = []
    for route in series["routes"]:
        routes.append(
            {
                "suffix_path": route["suffix_path"],
                "good_count": route["good_count"],
                "best_score": route["best_score"],
                "top3_sum": route["top3_sum"],
                "top5_sum": route["top5_sum"],
                "average_score": route["average_score"],
                "words": [serialize_word(member) for member in route["display_members"]],
            }
        )
    words = [word for route in routes for word in route["words"]]
    return {
        "suffix": series["suffix"],
        "routes": routes,
        "good_count": len(words),
        "average_score": sum(word["score"] for word in words) / len(words),
        "best_score": max(word["score"] for word in words),
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


def prepare_grail_board(paths, model):
    """Recognize and merge a five-image Grail board exactly once."""
    if len(paths) != IMAGE_COUNT:
        raise ValueError("exactly five images are required")
    ocr_started = time.perf_counter()
    recognized = [_recognize_path(path, model) for path in paths]
    ocr_seconds = time.perf_counter() - ocr_started
    merge_started = time.perf_counter()
    letters = merge_cell_letters([item[0] for item in recognized])
    multipliers, _sightings = merge_multipliers([item[1] for item in recognized])
    merge_seconds = time.perf_counter() - merge_started
    return {
        "cell_letters": letters,
        "multipliers": multipliers,
        "timings": {
            "ocr_all_5_seconds": ocr_seconds,
            "merge_seconds": merge_seconds,
        },
        "debug": {
            "cell_letters": letters,
            "multipliers": multipliers,
            "unique_letter_statistics": unique_letter_statistics(letters),
        },
    }


def search_grail_board(cell_letters, multipliers, trie):
    """Run the existing Grail DFS and series selection on a prepared board."""
    search_started = time.perf_counter()
    series_results = {}
    results = find_grail_words(cell_letters, multipliers, trie, series_results=series_results)
    search_seconds = time.perf_counter() - search_started
    series_started = time.perf_counter()
    series = select_series(series_results)
    series_seconds = time.perf_counter() - series_started
    return (
        results,
        series,
        {
            "grail_search_seconds": search_seconds,
            "series_processing_seconds": series_seconds,
        },
    )


def search_grail_best_words(cell_letters, multipliers, trie):
    """Find the best-scoring path per word without collecting series variants."""
    started = time.perf_counter()
    results = find_grail_words(cell_letters, multipliers, trie)
    return results, time.perf_counter() - started


def grail_result_from_search(prepared, results, series, search_timings):
    """Build the established Grail response shape from prepared/search data."""
    timings = {**prepared["timings"], **search_timings}
    return {
        "words": top_words(results),
        "series": [serialize_series(item) for item in series],
        "meta": {
            "total_found": len(results),
            "returned_words": min(len(results), MAX_WORDS),
            "returned_series": len(series),
        },
        "timings": {
            **timings,
        },
        "debug": prepared["debug"],
    }


def process_grail_images(paths, model, trie):
    started = time.perf_counter()
    prepared = prepare_grail_board(paths, model)
    results, series, search_timings = search_grail_board(
        prepared["cell_letters"], prepared["multipliers"], trie
    )
    result = grail_result_from_search(prepared, results, series, search_timings)
    result["timings"]["request_core_seconds"] = time.perf_counter() - started
    return result
