"""Run the offline five-image Grail OCR, search, and series-analysis prototype."""

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.tools import debug_board_recognition as board_debug  # noqa: E402
from backend.words_solver.dictionary import build_trie, load_words  # noqa: E402
from backend.words_solver.grail_search import GRID_SIZE, find_grail_words  # noqa: E402

IMAGE_NAMES = tuple(f"grail_{index}.png" for index in range(1, 6))
DEFAULT_TOP_LIMIT = 500
DEFAULT_SERIES_MIN_SUFFIX_LENGTH = 4
SERIES_RANKING_LIMIT = 20


def _empty_grid(value=None):
    return [[value for _col in range(GRID_SIZE)] for _row in range(GRID_SIZE)]


def _require_five_boards(boards, name):
    if len(boards) != 5:
        raise ValueError(f"{name} must contain exactly five 5x5 boards")
    for board in boards:
        if len(board) != GRID_SIZE or any(len(row) != GRID_SIZE for row in board):
            raise ValueError(f"each {name} board must be {GRID_SIZE}x{GRID_SIZE}")


def merge_cell_letters(boards):
    """Return the order-independent unique letter alternatives for each cell."""
    _require_five_boards(boards, "letter")
    return [
        [{board[row][col] for board in boards} for col in range(GRID_SIZE)]
        for row in range(GRID_SIZE)
    ]


def merge_multipliers(multiplier_grids):
    """Merge fixed-coordinate multipliers and reject contradictory observations."""
    _require_five_boards(multiplier_grids, "multiplier")
    merged = _empty_grid()
    sightings = _empty_grid()
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            observed = [grid[row][col] for grid in multiplier_grids if grid[row][col] is not None]
            counts = dict(sorted(Counter(observed).items()))
            sightings[row][col] = counts
            if len(counts) > 1:
                label = f"R{row + 1}C{col + 1}"
                raise ValueError(f"multiplier inconsistency at {label}: {counts}")
            merged[row][col] = next(iter(counts), None)
    return merged, sightings


def unique_letter_statistics(cell_letters):
    counts = [len(cell) for row in cell_letters for cell in row]
    distribution = dict(sorted(Counter(counts).items()))
    return {
        "avg_unique_letters_per_cell": sum(counts) / len(counts),
        "min_unique_letters_per_cell": min(counts),
        "max_unique_letters_per_cell": max(counts),
        "distribution": distribution,
    }


def serialize_word(result):
    return {
        "name": result["name"],
        "score": result["score"],
        "path": [row * GRID_SIZE + col for row, col, _letter in result["path"]],
    }


def top_words(results, limit):
    if limit < 1:
        raise ValueError("top limit must be at least 1")
    ranked = sorted(results.values(), key=lambda result: (-result["score"], result["name"]))
    return [serialize_word(result) for result in ranked[:limit]]


def _series_metrics(suffix, suffix_path, members):
    sorted_members = sorted(members, key=lambda result: (-result["score"], result["name"]))
    scores = [result["score"] for result in sorted_members]
    top5_members = sorted_members[:5]
    top5_prefix_letters = sum(len(result["name"]) - len(suffix) for result in top5_members)
    top5_sum = sum(scores[:5])
    return {
        "suffix": suffix,
        "suffix_length": len(suffix),
        "suffix_path": list(suffix_path),
        "word_count": len(sorted_members),
        "best_score": scores[0],
        "total_score": sum(scores),
        "top3_sum": sum(scores[:3]),
        "top5_sum": top5_sum,
        "top8_sum": sum(scores[:8]),
        "average_score": sum(scores) / len(scores),
        "top5_prefix_letters": top5_prefix_letters,
        "top5_score_per_prefix_letter": top5_sum / max(1, top5_prefix_letters),
        "members": [serialize_word(result) for result in sorted_members],
    }


def analyze_series(results, min_suffix_length=DEFAULT_SERIES_MIN_SUFFIX_LENGTH):
    """Group all found words by an identical text suffix on identical cells."""
    if min_suffix_length < 1:
        raise ValueError("series minimum suffix length must be at least 1")
    candidates = {}
    for result in results.values():
        word = result["name"]
        path = tuple(row * GRID_SIZE + col for row, col, _letter in result["path"])
        for suffix_length in range(min_suffix_length, len(word) + 1):
            suffix = word[-suffix_length:]
            suffix_path = path[-suffix_length:]
            candidates.setdefault((suffix, suffix_path), []).append(result)

    grouped = [
        (suffix, suffix_path, members)
        for (suffix, suffix_path), members in candidates.items()
        if len(members) >= 2
    ]
    most_specific_by_members = {}
    for suffix, suffix_path, members in grouped:
        member_names = frozenset(member["name"] for member in members)
        candidate = (suffix, suffix_path, members)
        existing = most_specific_by_members.get(member_names)
        if existing is None or (len(suffix), suffix, suffix_path) > (
            len(existing[0]),
            existing[0],
            existing[1],
        ):
            most_specific_by_members[member_names] = candidate

    series = [
        _series_metrics(suffix, suffix_path, members)
        for suffix, suffix_path, members in most_specific_by_members.values()
    ]
    series.sort(key=lambda item: (item["suffix"], item["suffix_path"]))
    rankings = {
        metric: sorted(
            series,
            key=lambda item: (-item[metric], item["suffix"], item["suffix_path"]),
        )[:SERIES_RANKING_LIMIT]
        for metric in (
            "total_score",
            "top3_sum",
            "top5_sum",
            "top8_sum",
            "top5_score_per_prefix_letter",
        )
    }
    return {
        "candidate_group_count": len(grouped),
        "deduplicated_group_count": len(series),
        "groups": series,
        "rankings": rankings,
    }


def _bbox_values(crop_details):
    bbox = crop_details.get("bbox") or crop_details.get("fallback_bbox")
    return [bbox.x0, bbox.y0, bbox.x1, bbox.y1] if bbox else None


def _transliterated_board(recognition, image_processing):
    return [
        [image_processing.TRANSLIT_TO_RUS.get(letter, letter) for letter, _multiplier in row]
        for row in recognition["board"]
    ]


def _multiplier_grid(recognition):
    grid = _empty_grid()
    for (row, col), multiplier in recognition["multipliers"].items():
        grid[row][col] = multiplier
    return grid


def _ocr_cells(recognition, image_processing):
    cells = []
    for row, col, *_rest in recognition["coordinates"]:
        probabilities = recognition["predictions"][(row, col)]
        class_index = int(np.argmax(probabilities))
        label = image_processing.CLASS_LABELS[class_index]
        cells.append(
            {
                "cell_id": row * GRID_SIZE + col,
                "row": row,
                "col": col,
                "letter": image_processing.TRANSLIT_TO_RUS.get(label, label),
                "top1_probability": float(probabilities[class_index]),
            }
        )
    return cells


def recognize_image(image_path, model, image_processing):
    started = time.perf_counter()
    image = cv2.imread(str(image_path))
    if image is None:
        raise ValueError(f"could not read image: {image_path}")
    input_dimensions = [int(image.shape[1]), int(image.shape[0])]
    crop_started = time.perf_counter()
    board, crop_details = image_processing.crop_board_image(image)
    crop_seconds = time.perf_counter() - crop_started
    if board.size == 0:
        raise ValueError(f"production crop is empty: {image_path}")
    ocr_started = time.perf_counter()
    recognition = image_processing.recognize_board_cells(board, model)
    ocr_seconds = time.perf_counter() - ocr_started
    return {
        "filename": image_path.name,
        "path": str(image_path.resolve()),
        "input_dimensions": input_dimensions,
        "smart_crop": {
            "smart_crop_used": crop_details["smart_crop_used"],
            "fallback_reason": crop_details.get("fallback_reason"),
            "bbox": _bbox_values(crop_details),
        },
        "recognized_board": _transliterated_board(recognition, image_processing),
        "multipliers": _multiplier_grid(recognition),
        "ocr_cells": _ocr_cells(recognition, image_processing),
        "timings": {
            "crop_seconds": crop_seconds,
            "ocr_seconds": ocr_seconds,
            "image_total_seconds": time.perf_counter() - started,
        },
    }


def input_paths(input_dir):
    paths = [input_dir / name for name in IMAGE_NAMES]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise ValueError("expected exactly five Grail PNGs; missing: " + ", ".join(missing))
    extras = sorted(input_dir.glob("grail_*.png"))
    if len(extras) != 5:
        raise ValueError(f"expected exactly five grail_*.png files, found {len(extras)}")
    return paths


def _series_line(series):
    words = ", ".join(f"{member['name']}:{member['score']}" for member in series["members"][:5])
    return (
        f"{series['suffix']} | len={series['suffix_length']} words={series['word_count']} "
        f"best={series['best_score']} top3={series['top3_sum']} top5={series['top5_sum']} "
        f"top8={series['top8_sum']} total={series['total_score']} "
        f"prefix={series['top5_prefix_letters']} "
        f"eff={series['top5_score_per_prefix_letter']:.2f} | {words}"
    )


def report_text(report, ranking_limit=SERIES_RANKING_LIMIT):
    lines = [
        "Grail offline pipeline",
        f"total_found: {report['search']['total_found']}",
        f"top_words_count: {len(report['best_words'])}",
        "unique_letters: "
        + json.dumps(report["merged"]["unique_letter_statistics"], ensure_ascii=False),
        "timings: " + json.dumps(report["timings"], ensure_ascii=False),
        "top_30_words: score | word",
    ]
    lines.extend(f"{word['score']} | {word['name']}" for word in report["best_words"][:30])
    lines.append(
        "series: "
        f"candidates={report['series']['candidate_group_count']} "
        f"deduplicated={report['series']['deduplicated_group_count']}"
    )
    for metric, ranking in report["series"]["rankings"].items():
        lines.append(f"series_top_{ranking_limit}_by_{metric}:")
        lines.extend(_series_line(series) for series in ranking[:ranking_limit])
    return "\n".join(lines) + "\n"


def _dictionary_path():
    default_path = (
        Path(__file__).resolve().parents[1] / "assets" / "cleaned_filtered_russian_words.json"
    )
    return Path(os.getenv("DICTIONARY_PATH", default_path))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--top-limit", type=int, default=DEFAULT_TOP_LIMIT)
    parser.add_argument(
        "--series-min-suffix-length", type=int, default=DEFAULT_SERIES_MIN_SUFFIX_LENGTH
    )
    parser.add_argument("--device", choices=("cpu", "auto"), default="cpu")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.top_limit < 1:
        raise SystemExit("error: --top-limit must be at least 1")
    if args.series_min_suffix_length < 1:
        raise SystemExit("error: --series-min-suffix-length must be at least 1")
    try:
        paths = input_paths(args.input_dir)
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from exc

    total_started = time.perf_counter()
    runtime_started = time.perf_counter()
    runtime = board_debug.configure_runtime(args.device)
    image_processing = runtime["image_processing"]
    model_load_started = time.perf_counter()
    model_path = os.getenv("MODEL_PATH", image_processing.default_model_path())
    model = runtime["load_letter_model"](model_path)
    model_load_seconds = time.perf_counter() - model_load_started
    runtime_setup_seconds = time.perf_counter() - runtime_started - model_load_seconds

    dictionary_started = time.perf_counter()
    words = load_words(_dictionary_path())
    trie = build_trie(words)
    dictionary_load_seconds = time.perf_counter() - dictionary_started

    ocr_started = time.perf_counter()
    screenshots = [recognize_image(path, model, image_processing) for path in paths]
    ocr_all_seconds = time.perf_counter() - ocr_started

    merge_started = time.perf_counter()
    cell_letters = merge_cell_letters([item["recognized_board"] for item in screenshots])
    multipliers, multiplier_sightings = merge_multipliers(
        [item["multipliers"] for item in screenshots]
    )
    merge_seconds = time.perf_counter() - merge_started

    search_started = time.perf_counter()
    results = find_grail_words(cell_letters, multipliers, trie)
    search_seconds = time.perf_counter() - search_started

    series_started = time.perf_counter()
    series = analyze_series(results, args.series_min_suffix_length)
    series_seconds = time.perf_counter() - series_started

    report = {
        "metadata": {
            "created_at": datetime.now(timezone.utc).isoformat(),
            "mode": "offline_grail_prototype",
            "device_requested": args.device,
            "model_path": str(model_path),
            "dictionary_path": str(_dictionary_path()),
            "dictionary_words": len(words),
            "top_limit": args.top_limit,
            "series_min_suffix_length": args.series_min_suffix_length,
            "series_path_basis": "best_scoring_path_per_word",
        },
        "screenshots": screenshots,
        "merged": {
            "cell_letters": [[sorted(cell) for cell in row] for row in cell_letters],
            "multipliers": multipliers,
            "multiplier_sightings": multiplier_sightings,
            "unique_letter_statistics": unique_letter_statistics(cell_letters),
        },
        "search": {"total_found": len(results)},
        "best_words": top_words(results, args.top_limit),
        "series": series,
        "timings": {
            "runtime_setup_seconds": runtime_setup_seconds,
            "model_load_seconds": model_load_seconds,
            "dictionary_load_seconds": dictionary_load_seconds,
            "ocr_all_5_seconds": ocr_all_seconds,
            "merge_seconds": merge_seconds,
            "grail_search_seconds": search_seconds,
            "series_analysis_seconds": series_seconds,
        },
    }

    report_started = time.perf_counter()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    text_path = args.output_dir / "report.txt"
    json_path = args.output_dir / "report.json"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    text_path.write_text(report_text(report), encoding="utf-8")
    report["timings"]["report_generation_seconds"] = time.perf_counter() - report_started
    report["timings"]["total_pipeline_seconds"] = time.perf_counter() - total_started
    text_path.write_text(report_text(report), encoding="utf-8")
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report_text(report))
    print(f"Report created: {json_path}")


if __name__ == "__main__":
    main()
