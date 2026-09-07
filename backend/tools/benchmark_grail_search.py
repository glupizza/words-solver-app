"""Deterministic synthetic benchmark for the Grail Trie DFS search."""

import argparse
import os
import random
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.words_solver.dictionary import build_trie, load_words  # noqa: E402
from backend.words_solver.grail_search import GRID_SIZE, find_grail_words  # noqa: E402

SEED = 20260907
LAYER_COUNT = 5


def _dictionary_path():
    default_path = (
        Path(__file__).resolve().parents[1] / "assets" / "cleaned_filtered_russian_words.json"
    )
    return Path(os.getenv("DICTIONARY_PATH", default_path))


def _letter_distribution(words):
    counts = Counter(letter for word in words for letter in word)
    letters = tuple(sorted(counts))
    return letters, tuple(counts[letter] for letter in letters)


def _sample_unique_cell(randomizer, letters, weights, target_unique):
    chosen = set()
    while len(chosen) < target_unique:
        chosen.add(randomizer.choices(letters, weights=weights, k=1)[0])
    return chosen


def _build_board(case_name, letters, weights):
    randomizer = random.Random(SEED)
    if case_name == "singleton":
        target_unique = 1
        return [
            [
                _sample_unique_cell(randomizer, letters, weights, target_unique)
                for _col in range(GRID_SIZE)
            ]
            for _row in range(GRID_SIZE)
        ]
    if case_name in {"grail-3", "grail-5"}:
        target_unique = int(case_name[-1])
        return [
            [
                _sample_unique_cell(randomizer, letters, weights, target_unique)
                for _col in range(GRID_SIZE)
            ]
            for _row in range(GRID_SIZE)
        ]
    if case_name == "natural-five-layers":
        layers = [
            [randomizer.choices(letters, weights=weights, k=GRID_SIZE) for _row in range(GRID_SIZE)]
            for _layer in range(LAYER_COUNT)
        ]
        return [
            {layers[layer][row][col] for layer in range(LAYER_COUNT)}
            for row in range(GRID_SIZE)
            for col in range(GRID_SIZE)
        ]
    raise ValueError(f"unknown case: {case_name}")


def _as_rows(cells):
    if len(cells) == GRID_SIZE and all(len(row) == GRID_SIZE for row in cells):
        return cells
    return [cells[offset : offset + GRID_SIZE] for offset in range(0, len(cells), GRID_SIZE)]


def _empty_multipliers():
    return [[None for _col in range(GRID_SIZE)] for _row in range(GRID_SIZE)]


def _print_case(case_name, cells, results, elapsed_runs, dictionary_words):
    unique_counts = [len(cell) for row in cells for cell in row]
    values = list(results.values())
    ranked = sorted(values, key=lambda result: (-result["score"], result["name"]))
    longest = max(values, key=lambda result: (len(result["name"]), result["name"]), default=None)
    best = ranked[0] if ranked else None
    print(f"case: {case_name} (synthetic benchmark)")
    print(f"dictionary_words: {dictionary_words}")
    print("cells: 25")
    print(f"avg_unique_letters_per_cell: {statistics.mean(unique_counts):.2f}")
    print(f"min_unique_letters_per_cell: {min(unique_counts)}")
    print(f"max_unique_letters_per_cell: {max(unique_counts)}")
    print(f"words_found: {len(values)}")
    print(f"longest_word_length: {len(longest['name']) if longest else 0}")
    print(f"longest_word: {longest['name'] if longest else '-'}")
    print(f"best_score: {best['score'] if best else 0}")
    print(f"best_word: {best['name'] if best else '-'}")
    print(f"elapsed_seconds_min: {min(elapsed_runs):.6f}")
    print(f"elapsed_seconds_median: {statistics.median(elapsed_runs):.6f}")
    print(f"elapsed_seconds_max: {max(elapsed_runs):.6f}")
    print("top_10: score | word | length")
    for result in ranked[:10]:
        print(f"{result['score']} | {result['name']} | {len(result['name'])}")
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3, help="number of measured runs per case")
    args = parser.parse_args()
    if args.repeats < 1:
        parser.error("--repeats must be at least 1")

    words = load_words(_dictionary_path())
    trie = build_trie(words)
    letters, weights = _letter_distribution(words)
    multipliers = _empty_multipliers()

    for case_name in ("singleton", "grail-3", "grail-5", "natural-five-layers"):
        cells = _as_rows(_build_board(case_name, letters, weights))
        find_grail_words(cells, multipliers, trie)  # warmup
        elapsed_runs = []
        results = None
        for _repeat in range(args.repeats):
            started = time.perf_counter()
            results = find_grail_words(cells, multipliers, trie)
            elapsed_runs.append(time.perf_counter() - started)
        _print_case(case_name, cells, results, elapsed_runs, len(words))


if __name__ == "__main__":
    main()
