"""Reusable production processing for five-image Grail boards."""

import json
import time
from collections import Counter
from pathlib import Path
from statistics import median

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
MAIN_EVALUATION_WINDOW = 25
VALUE_EVALUATION_WINDOW = 15
VALUE_LENGTH_PENALTY = 20
NESTED_TOP5_PRESERVE_RATIO = 0.95
PRIORITY_SERIES_SUFFIXES = (
    "\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435",
    "\u0438\u0440\u043e\u0432\u0430\u0442\u044c\u0441\u044f",
    "\u0438\u0440\u043e\u0432\u0430\u0442\u044c",
    "\u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0439",
    "\u0438\u0440\u043e\u0432\u043a\u0430",
    "\u0441\u0442\u0440\u043e\u0435\u043d\u0438\u0435",
    "\u0432\u0430\u0440\u0438\u0432\u0430\u043d\u0438\u0435",
)
TABLE_AWARE_SUFFIXES = PRIORITY_SERIES_SUFFIXES[:5]


def _load_known_bases():
    path = Path(__file__).resolve().parents[1] / "assets" / "grail_known_bases.json"
    with path.open(encoding="utf-8") as source:
        data = json.load(source)
    bases = {
        link.strip().lower(): {base.strip().lower() for base in values}
        for link, values in data["link_bases"].items()
    }
    if (
        data.get("suffix") != "\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435"
        or len(bases) != 18
        or sum(len(values) for values in bases.values()) != 428
    ):
        raise ValueError("invalid grail known-bases asset")
    return bases


KNOWN_BASES = _load_known_bases()


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
        "average_score": sum(scores) / len(scores),
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


def _merge_series_by_suffix(series):
    merged = {}
    for item in series:
        current = merged.get(item["suffix"])
        if current is None:
            current = {
                "suffix_path": item["suffix_path"],
                "members": {},
            }
            merged[item["suffix"]] = current
        for member in item["good_members"]:
            existing = current["members"].get(member["name"])
            if existing is None or member["score"] > existing["score"]:
                current["members"][member["name"]] = member
    return [
        _series_metrics(suffix, item["suffix_path"], item["members"].values())
        for suffix, item in merged.items()
    ]


def _word_features(member, suffix):
    word = member["name"]
    prefix = word[: -len(suffix)] if suffix else word
    path = tuple(row * GRID_SIZE + col for row, col, _letter in member["path"])
    if prefix and len(path) >= len(prefix):
        link_letter = prefix[-1]
        base = prefix[:-1]
        link_position = path[len(prefix) - 1]
        bundle = (link_letter, link_position)
    else:
        link_letter = ""
        base = ""
        link_position = -1
        bundle = ("", -1)
    normalized_link = link_letter.strip().lower()
    normalized_base = base.strip().lower()
    known = normalized_link in KNOWN_BASES and normalized_base in KNOWN_BASES[normalized_link]
    return {
        "member": member,
        "name": word,
        "score": member["score"],
        "prefix_length": len(prefix),
        "base_length": len(base),
        "known": known,
        "short_known": known and 1 <= len(base) <= 5,
        "short_any": 1 <= len(base) <= 5,
        "bundle": bundle,
    }


def _concentration(features):
    counts = Counter(feature["bundle"] for feature in features)
    values = sorted(counts.values(), reverse=True)
    return len(counts), sum(values[:3]) / len(features) if features else 0


def _main_window(features, table_aware):
    if table_aware:

        def key(feature):
            category = (
                0
                if feature["short_known"]
                else 1
                if feature["known"]
                else 2
                if feature["short_any"]
                else 3
            )
            return category, feature["base_length"], feature["score"], feature["name"]
    else:

        def key(feature):
            return feature["prefix_length"], feature["score"], feature["name"]

    return sorted(features, key=key)[:MAIN_EVALUATION_WINDOW]


def _value_window(features):
    def adjusted(feature):
        return feature["score"] - VALUE_LENGTH_PENALTY * max(feature["prefix_length"] - 5, 0)

    return sorted(
        features,
        key=lambda feature: (
            -adjusted(feature),
            feature["prefix_length"],
            -feature["score"],
            feature["name"],
        ),
    )[:VALUE_EVALUATION_WINDOW]


def _main_key(series):
    features = [_word_features(member, series["suffix"]) for member in series["good_members"]]
    table_aware = series["suffix"] in TABLE_AWARE_SUFFIXES
    window = _main_window(features, table_aware)
    distinct, coverage = _concentration(window)
    scores = [feature["score"] for feature in window]
    if table_aware:
        return (
            -sum(feature["short_known"] for feature in window),
            -sum(feature["known"] for feature in window),
            -coverage,
            distinct,
            -median(scores),
            -sum(scores) / len(scores),
            tuple(series["suffix_path"]),
        )
    lengths = [feature["prefix_length"] for feature in window]
    return (
        -sum(feature["short_any"] for feature in window),
        -coverage,
        distinct,
        median(lengths),
        -median(scores),
        -sum(scores) / len(scores),
        tuple(series["suffix_path"]),
    )


def _value_key(series):
    features = [_word_features(member, series["suffix"]) for member in series["good_members"]]
    window = _value_window(features)
    adjusted = [
        feature["score"] - VALUE_LENGTH_PENALTY * max(feature["prefix_length"] - 5, 0)
        for feature in window
    ]
    scores = [feature["score"] for feature in window]
    distinct, coverage = _concentration(window)
    value_index = (
        sum(adjusted)
        / len(adjusted)
        * min(len(window), VALUE_EVALUATION_WINDOW)
        / VALUE_EVALUATION_WINDOW
    )
    return (
        -value_index,
        -median(adjusted),
        -sum(scores) / len(scores),
        -coverage,
        distinct,
        tuple(series["suffix_path"]),
    )


def _display_members(series, role):
    table_aware = series["suffix"] in TABLE_AWARE_SUFFIXES
    features = [_word_features(member, series["suffix"]) for member in series["good_members"]]
    window = _main_window(features, table_aware) if role == "main" else _value_window(features)
    window_counts = Counter(feature["bundle"] for feature in window)
    window_ids = {id(feature) for feature in window}
    adjusted = {
        id(feature): feature["score"] - VALUE_LENGTH_PENALTY * max(feature["prefix_length"] - 5, 0)
        for feature in features
    }
    groups = {}
    for feature in features:
        groups.setdefault(feature["bundle"], []).append(feature)

    def word_key(feature):
        if table_aware:
            return not feature["known"], feature["base_length"], feature["score"], feature["name"]
        return feature["prefix_length"], feature["score"], feature["name"]

    def bundle_key(item):
        bundle, members = item
        if role == "value":
            in_window = [member for member in members if id(member) in window_ids]
            return (
                -window_counts[bundle],
                -sum(adjusted[id(member)] for member in in_window),
                -(
                    sum(adjusted[id(member)] for member in in_window) / len(in_window)
                    if in_window
                    else 0
                ),
                -len(members),
                (bundle[0] + series["suffix"]),
                bundle[1],
            )
        scores = [member["score"] for member in members]
        if table_aware:
            return (
                -window_counts[bundle],
                -sum(member["short_known"] for member in members),
                -sum(member["known"] for member in members),
                -len(members),
                -median(scores),
                bundle[0] + series["suffix"],
                bundle[1],
            )
        return (
            -window_counts[bundle],
            -len(members),
            median(member["prefix_length"] for member in members),
            -median(scores),
            bundle[0] + series["suffix"],
            bundle[1],
        )

    return [
        member["member"]
        for _bundle, members in sorted(groups.items(), key=bundle_key)
        for member in sorted(members, key=word_key)
    ]


def _with_role(series, role):
    unique = {}
    for member in series["good_members"]:
        previous = unique.get(member["name"])
        if previous is None or member["score"] > previous["score"]:
            unique[member["name"]] = member
    selected = _series_metrics(series["suffix"], series["suffix_path"], unique.values())
    selected["role"] = role
    selected["display_members"] = _display_members(selected, role)
    return selected


def select_series(results, min_suffix_length=MIN_SERIES_SUFFIX_LENGTH):
    candidates = build_series(results, min_suffix_length)
    priority = []
    for suffix in PRIORITY_SERIES_SUFFIXES:
        paths = [candidate for candidate in candidates if candidate["suffix"] == suffix]
        if paths:
            priority.extend(
                (
                    _with_role(min(paths, key=_main_key), "main"),
                    _with_role(min(paths, key=_value_key), "value"),
                )
            )

    ordered = sorted(
        candidates, key=lambda series: (-series["suffix_length"],) + _ranking_key(series)
    )
    suppressors = []
    protected = []
    for candidate in ordered:
        if candidate["suffix"] in PRIORITY_SERIES_SUFFIXES:
            suppressors.append(candidate)
            continue
        if any(_suppresses(longer, candidate) for longer in suppressors):
            continue
        suppressors.append(candidate)
        protected.append(candidate)
    normal = []
    for suffix in sorted({candidate["suffix"] for candidate in protected}):
        paths = [candidate for candidate in protected if candidate["suffix"] == suffix]
        normal.append(_with_role(min(paths, key=_value_key), "value"))
    normal.sort(key=_ranking_key)
    return (priority + normal)[:MAX_SERIES]


def serialize_series(series):
    members = series.get("display_members", series["good_members"])
    if series["suffix"] not in PRIORITY_SERIES_SUFFIXES:
        members = members[:MAX_SERIES_WORDS]
    payload = {
        "suffix": series["suffix"],
        "suffix_path": series["suffix_path"],
        "good_count": series["good_count"],
        "best_score": series["best_score"],
        "top3_sum": series["top3_sum"],
        "top5_sum": series["top5_sum"],
        "average_score": series["average_score"],
        "words": [serialize_word(member) for member in members],
    }
    if "role" in series:
        payload["role"] = series["role"]
    return payload


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
