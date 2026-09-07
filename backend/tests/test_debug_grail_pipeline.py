import pytest

from backend.tools.debug_grail_pipeline import (
    analyze_series,
    merge_cell_letters,
    merge_multipliers,
    top_words,
)


def _board(letter):
    return [[letter for _col in range(5)] for _row in range(5)]


def _multiplier_grid(value=None):
    return [[value for _col in range(5)] for _row in range(5)]


def _result(name, score, cell_ids):
    return {
        "name": name,
        "score": score,
        "path": tuple(
            (cell_id // 5, cell_id % 5, letter) for cell_id, letter in zip(cell_ids, name)
        ),
    }


def test_merge_cell_letters_deduplicates_and_is_order_independent():
    boards = [
        _board("\u0440"),
        _board("\u0440"),
        _board("\u0440"),
        _board("\u0430"),
        _board("\u0437"),
    ]

    merged = merge_cell_letters(boards)

    assert merged[0][0] == {"\u0440", "\u0430", "\u0437"}
    assert merge_cell_letters(list(reversed(boards))) == merged


def test_merge_multipliers_accepts_one_non_none_value_and_reports_sightings():
    grids = [_multiplier_grid() for _ in range(5)]
    for index in (0, 1, 3, 4):
        grids[index][1][2] = "x3"

    merged, sightings = merge_multipliers(grids)

    assert merged[1][2] == "x3"
    assert sightings[1][2] == {"x3": 4}


def test_merge_multipliers_rejects_conflicting_non_none_values():
    grids = [_multiplier_grid() for _ in range(5)]
    grids[0][0][0] = "x3"
    grids[1][0][0] = "c3"

    with pytest.raises(ValueError, match="R1C1"):
        merge_multipliers(grids)


def test_top_words_uses_score_then_name_and_respects_exact_limit():
    results = {
        "\u0431\u0430": _result("\u0431\u0430", 10, [0, 1]),
        "\u0430\u0431": _result("\u0430\u0431", 10, [2, 3]),
        "\u0434\u043b\u0438\u043d\u043d\u043e\u0435": _result(
            "\u0434\u043b\u0438\u043d\u043d\u043e\u0435", 9, [4, 5, 6, 7, 8, 9, 10]
        ),
    }
    results.update(
        {
            f"word{index}": _result(f"word{index}", 1, [0] * len(f"word{index}"))
            for index in range(501)
        }
    )

    ranked = top_words(results, 500)

    assert len(ranked) == 500
    assert [word["name"] for word in ranked[:3]] == [
        "\u0430\u0431",
        "\u0431\u0430",
        "\u0434\u043b\u0438\u043d\u043d\u043e\u0435",
    ]


def test_series_requires_same_text_suffix_and_same_path():
    same_path = {
        "\u0431\u0430\u0440": _result("\u0431\u0430\u0440", 10, [0, 1, 2]),
        "\u0434\u0430\u0440": _result("\u0434\u0430\u0440", 9, [3, 1, 2]),
    }
    different_path = {
        "\u0431\u0430\u0440": _result("\u0431\u0430\u0440", 10, [0, 1, 2]),
        "\u0434\u0430\u0440": _result("\u0434\u0430\u0440", 9, [3, 4, 5]),
    }
    different_text = {
        "\u0431\u0430\u0440": _result("\u0431\u0430\u0440", 10, [0, 1, 2]),
        "\u0431\u043e\u0437": _result("\u0431\u043e\u0437", 9, [3, 1, 2]),
    }

    assert [series["suffix"] for series in analyze_series(same_path, 2)["groups"]] == [
        "\u0430\u0440"
    ]
    assert analyze_series(different_path, 2)["groups"] == []
    assert analyze_series(different_text, 2)["groups"] == []


def test_series_keeps_only_longest_group_for_an_identical_member_set():
    results = {
        "\u043a\u0430\u0431\u0430\u0440": _result(
            "\u043a\u0430\u0431\u0430\u0440", 10, [0, 1, 2, 3, 4]
        ),
        "\u0442\u0430\u0431\u0430\u0440": _result(
            "\u0442\u0430\u0431\u0430\u0440", 9, [5, 1, 2, 3, 4]
        ),
    }

    groups = analyze_series(results, 2)["groups"]

    assert [series["suffix"] for series in groups] == ["\u0430\u0431\u0430\u0440"]


def test_series_metrics_and_analysis_use_all_results():
    results = {
        "\u043a\u0430\u0431\u0430\u0440": _result(
            "\u043a\u0430\u0431\u0430\u0440", 10, [0, 1, 2, 3, 4]
        ),
        "\u0442\u0430\u0431\u0430\u0440": _result(
            "\u0442\u0430\u0431\u0430\u0440", 9, [5, 1, 2, 3, 4]
        ),
        "\u043d\u0430\u0431\u0430\u0440": _result(
            "\u043d\u0430\u0431\u0430\u0440", 8, [6, 1, 2, 3, 4]
        ),
        "\u0432\u044b\u0441\u043e\u043a\u043e": _result(
            "\u0432\u044b\u0441\u043e\u043a\u043e", 100, [7, 8, 9, 10, 11, 12]
        ),
    }

    series = analyze_series(results, 4)["groups"]
    abar = next(group for group in series if group["suffix"] == "\u0430\u0431\u0430\u0440")

    assert top_words(results, 1)[0]["name"] == "\u0432\u044b\u0441\u043e\u043a\u043e"
    assert abar["word_count"] == 3
    assert abar["best_score"] == 10
    assert abar["total_score"] == 27
    assert abar["top3_sum"] == 27
    assert abar["top5_sum"] == 27
    assert abar["top8_sum"] == 27
    assert abar["top5_prefix_letters"] == 3
    assert abar["top5_score_per_prefix_letter"] == 9
