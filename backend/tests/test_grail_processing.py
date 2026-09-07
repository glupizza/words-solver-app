import pytest

from backend.words_solver.grail_processing import (
    MAX_SERIES,
    MAX_SERIES_WORDS,
    MIN_SERIES_SUFFIX_LENGTH,
    MIN_WORD_SCORE,
    PRIORITY_SERIES_SUFFIXES,
    GrailMultiplierConflict,
    merge_cell_letters,
    merge_multipliers,
    select_series,
    serialize_series,
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
        name = chr(97 + index) + "longtail"
        results[name] = _result(name, score, [index] + list(range(1, len(name))))
    selected = select_series(results)
    tail = next(series for series in selected if series["suffix"] == "longtail")
    assert tail["good_count"] == 9
    assert len(tail["good_members"][:MAX_SERIES_WORDS]) == min(tail["good_count"], MAX_SERIES_WORDS)
    assert tail["top3_sum"] == 1550


def test_nested_suppression_requires_top_three_and_top_five_ratio():
    results = {}
    for index, score in enumerate((700, 600, 500, 450, 400)):
        name = chr(97 + index) + "xxxtail"
        results[name] = _result(name, score, [index, 1, 2, 3, 4, 5, 6, 7])
    results["zlongtail"] = _result("zlongtail", 400, [10, 2, 3, 4, 5, 6, 7, 8])

    suffixes = {series["suffix"] for series in select_series(results)}

    assert "xxxtail" in suffixes
    assert "longtail" not in suffixes
    assert len(select_series(results)) <= MAX_SERIES


def test_nested_suppression_keeps_only_eligible_suffix_lengths():
    results = {
        "ayxxxtail": _result("ayxxxtail", 600, [10, 1, 2, 3, 4, 5, 6, 7, 8]),
        "byxxxtail": _result("byxxxtail", 590, [11, 1, 2, 3, 4, 5, 6, 7, 8]),
        "cyxxxtail": _result("cyxxxtail", 580, [12, 1, 2, 3, 4, 5, 6, 7, 8]),
        "dyxxxtail": _result("dyxxxtail", 400, [13, 1, 2, 3, 4, 5, 6, 7, 8]),
        "eyxxxtail": _result("eyxxxtail", 400, [14, 1, 2, 3, 4, 5, 6, 7, 8]),
        "fxxxtail": _result("fxxxtail", 420, [15, 2, 3, 4, 5, 6, 7, 8]),
        "glongtail": _result("glongtail", 520, [16, 3, 4, 5, 6, 7, 8, 9]),
    }

    suffixes = {series["suffix"] for series in select_series(results)}

    assert "yxxxtail" in suffixes
    assert "xxxtail" not in suffixes
    assert all(len(suffix) >= MIN_SERIES_SUFFIX_LENGTH for suffix in suffixes)


def _series_results(suffix, scores, prefixes):
    return {
        prefix + suffix: _result(prefix + suffix, score, [index] + list(range(1, len(suffix) + 1)))
        for index, (prefix, score) in enumerate(zip(prefixes, scores))
    }


def test_series_minimum_length_priority_order_and_nested_priority_preservation():
    priority = PRIORITY_SERIES_SUFFIXES[0]
    second_priority = PRIORITY_SERIES_SUFFIXES[1]
    normal = "normtail"
    results = _series_results("x" + priority, [900, 800, 700], ["a", "b", "c"])
    results["z" + priority] = _result("z" + priority, 400, [99] + list(range(2, len(priority) + 2)))
    results.update(_series_results(second_priority, [750, 650, 550], ["j", "k", "l"]))
    results.update(_series_results(normal, [600, 500, 400], ["d", "e", "f"]))
    results.update(_series_results("short", [900, 800, 700], ["g", "h", "i"]))

    selected = select_series(results)
    suffixes = [series["suffix"] for series in selected]

    assert all(len(suffix) >= MIN_SERIES_SUFFIX_LENGTH for suffix in suffixes)
    assert priority in suffixes
    assert suffixes.index(priority) < suffixes.index(normal)
    assert suffixes[:2] == [priority, second_priority]


def test_priority_suffix_survives_specific_member_set_deduplication():
    priority = PRIORITY_SERIES_SUFFIXES[0]
    longer_suffix = "x" + priority
    results = _series_results(longer_suffix, [900, 800, 700], ["a", "b", "c"])

    suffixes = [series["suffix"] for series in select_series(results)]

    assert longer_suffix in suffixes
    assert priority in suffixes
    assert suffixes[0] == priority


def test_series_suffix_length_floor_ignores_smaller_requested_minimum():
    results = _series_results("short", [900, 800, 700], ["a", "b", "c"])
    results.update(_series_results("longtail", [600, 500, 400], ["d", "e", "f"]))

    selected = select_series(results, min_suffix_length=4)

    assert selected
    assert all(series["suffix_length"] >= MIN_SERIES_SUFFIX_LENGTH for series in selected)


def test_priority_series_returns_all_members_and_normal_series_selects_best_ten_first():
    priority = PRIORITY_SERIES_SUFFIXES[1]
    normal = "normtail"
    results = _series_results(priority, list(range(500, 512)), [chr(97 + i) for i in range(12)])
    results.update(
        _series_results(
            normal,
            [1000 - i * 10 for i in range(12)],
            [
                "longword",
                "a",
                "bb",
                "ccc",
                "dddd",
                "eeeee",
                "ffffff",
                "ggggggg",
                "hhhhhhhh",
                "iiiiiiiii",
                "jjjjjjjjjj",
                "kkkkkkkkkkk",
            ],
        )
    )

    serialized = {item["suffix"]: item for item in map(serialize_series, select_series(results))}
    priority_words = serialized[priority]["words"]
    normal_words = serialized[normal]["words"]

    assert len(priority_words) == 12
    assert len(normal_words) == MAX_SERIES_WORDS
    assert {word["score"] for word in normal_words} == set(range(910, 1001, 10))
    assert [word["name"] for word in normal_words] == [
        word["name"]
        for word in sorted(
            normal_words,
            key=lambda word: (len(word["name"]), word["score"], word["name"]),
        )
    ]


def test_display_order_does_not_change_metrics_or_series_ranking():
    first = "firsttail"
    second = "secondtail"
    results = _series_results(first, [900, 800, 700], ["long", "a", "bb"])
    results.update(_series_results(second, [850, 750, 650], ["c", "dd", "eee"]))

    selected = select_series(results)
    first_series = next(series for series in selected if series["suffix"] == first)
    serialized = serialize_series(first_series)

    assert [series["suffix"] for series in selected[:2]] == [first, second]
    assert first_series["top3_sum"] == 2400
    assert first_series["top5_sum"] == 2400
    assert [word["name"] for word in serialized["words"]] == [
        "afirsttail",
        "bbfirsttail",
        "longfirsttail",
    ]
