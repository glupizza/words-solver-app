import pytest

from backend.words_solver.grail_processing import (
    MAX_SERIES,
    MAX_SERIES_WORDS,
    MIN_WORD_SCORE,
    GrailMultiplierConflict,
    merge_cell_letters,
    merge_multipliers,
    select_series,
    serialize_word,
    top_words,
)


def _board(letter):
    return [[letter for _ in range(5)] for _ in range(5)]


def _result(name, score, ids):
    return {
        "name": name,
        "score": score,
        "path": tuple((i // 5, i % 5, c) for i, c in zip(ids, name)),
    }


def test_merge_requires_five_and_is_order_independent():
    boards = [
        _board("\u0440"),
        _board("\u0440"),
        _board("\u0440"),
        _board("\u0430"),
        _board("\u0437"),
    ]
    assert merge_cell_letters(boards)[0][0] == {"\u0440", "\u0430", "\u0437"}
    assert merge_cell_letters(boards) == merge_cell_letters(list(reversed(boards)))
    with pytest.raises(ValueError):
        merge_cell_letters(boards[:4])


def test_multiplier_merge_handles_none_and_conflicts():
    grids = [[row[:] for row in _board(None)] for _ in range(5)]
    grids[0][0][0] = "x3"
    grids[2][0][0] = "x3"
    assert merge_multipliers(grids)[0][0][0] == "x3"
    grids[4][0][0] = "c3"
    with pytest.raises(GrailMultiplierConflict):
        merge_multipliers(grids)


def test_top_words_and_compact_path_are_score_then_name_limited():
    results = {f"w{i}": _result(f"w{i}", 1, [0, 1]) for i in range(501)}
    results.update({"b": _result("b", 5, [0]), "a": _result("a", 5, [1])})
    ranked = top_words(results)
    assert len(ranked) == 500
    assert [item["name"] for item in ranked[:2]] == ["a", "b"]
    assert serialize_word(_result("ab", 1, [0, 6]))["path"] == [0, 6]


def test_final_series_good_threshold_ranking_and_member_limit():
    results = {}
    for index, score in enumerate((600, 500, MIN_WORD_SCORE, 399, 450, 440, 430, 420, 410, 405)):
        name = chr(97 + index) + "tail"
        results[name] = _result(name, score, [index, 1, 2, 3, 4])
    selected = select_series(results)
    tail = next(series for series in selected if series["suffix"] == "tail")
    assert tail["good_count"] == 9
    assert len(tail["good_members"][:MAX_SERIES_WORDS]) == MAX_SERIES_WORDS
    assert tail["top3_sum"] == 1550


def test_nested_suppression_requires_top_three_and_top_five_ratio():
    results = {}
    for index, score in enumerate((700, 600, 500, 450, 400)):
        name = chr(97 + index) + "xtail"
        results[name] = _result(name, score, [index, 1, 2, 3, 4, 5])
    results["ztail"] = _result("ztail", 400, [10, 2, 3, 4, 5])

    suffixes = {series["suffix"] for series in select_series(results)}

    assert "xtail" in suffixes
    assert "tail" not in suffixes
    assert len(select_series(results)) <= MAX_SERIES


def test_nested_suppression_only_uses_surviving_longer_series():
    results = {
        "ayxtail": _result("ayxtail", 600, [10, 1, 2, 3, 4, 5, 6]),
        "byxtail": _result("byxtail", 590, [11, 1, 2, 3, 4, 5, 6]),
        "cyxtail": _result("cyxtail", 580, [12, 1, 2, 3, 4, 5, 6]),
        "dyxtail": _result("dyxtail", 400, [13, 1, 2, 3, 4, 5, 6]),
        "eyxtail": _result("eyxtail", 400, [14, 1, 2, 3, 4, 5, 6]),
        "fxtail": _result("fxtail", 420, [15, 2, 3, 4, 5, 6]),
        "gtail": _result("gtail", 520, [16, 3, 4, 5, 6]),
    }

    suffixes = {series["suffix"] for series in select_series(results)}

    assert "yxtail" in suffixes
    assert "xtail" not in suffixes
    assert "tail" in suffixes
