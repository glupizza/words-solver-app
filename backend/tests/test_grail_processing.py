import pytest

from backend.words_solver.grail_processing import (
    KNOWN_BASES,
    MAX_SERIES,
    MAX_SERIES_WORDS,
    MIN_SERIES_SUFFIX_LENGTH,
    MIN_WORD_SCORE,
    PRIORITY_SERIES_SUFFIXES,
    GrailMultiplierConflict,
    _main_key,
    _merge_series_by_suffix,
    _series_metrics,
    _value_key,
    _word_features,
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
    assert suffixes[:4] == [priority, priority, second_priority, second_priority]


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


def test_same_suffix_paths_select_one_value_path_without_merging():
    suffix = "normtail"
    results = {}
    for prefix, score in (("a", 900), ("b", 800), ("c", 700)):
        name = prefix + suffix
        results[name] = _result(name, score, [ord(prefix)] + list(range(1, len(suffix) + 1)))
    for prefix, score in (("d", 600), ("e", 500), ("f", 400)):
        name = prefix + suffix
        results[name] = _result(name, score, [ord(prefix)] + list(range(11, len(suffix) + 11)))

    selected = select_series(results)
    series = [item for item in selected if item["suffix"] == suffix]

    assert len(series) == 1
    assert {member["name"] for member in series[0]["good_members"]} == {
        "anormtail",
        "bnormtail",
        "cnormtail",
    }
    assert len([item["suffix"] for item in selected]) == len({item["suffix"] for item in selected})


def test_merged_series_deduplicates_words_and_recomputes_metrics():
    suffix = "normtail"
    first = _series_metrics(
        suffix,
        [1] * len(suffix),
        [_result("alpha", 900, [1]), _result("shared", 500, [2]), _result("beta", 800, [3])],
    )
    second = _series_metrics(
        suffix,
        [2] * len(suffix),
        [_result("shared", 600, [4]), _result("gamma", 700, [5]), _result("delta", 400, [6])],
    )

    merged = _merge_series_by_suffix([first, second])
    serialized = serialize_series(merged[0])

    assert len(merged) == 1
    assert merged[0]["good_count"] == 5
    assert merged[0]["best_score"] == 900
    assert merged[0]["top3_sum"] == 2400
    assert merged[0]["top5_sum"] == 3400
    assert next(word for word in serialized["words"] if word["name"] == "shared")["score"] == 600


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
    assert all(word["name"].endswith(normal) for word in normal_words)


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
    assert {word["name"] for word in serialized["words"]} == {
        "afirsttail",
        "bbfirsttail",
        "longfirsttail",
    }


def test_known_base_asset_has_expected_shape():
    assert len(KNOWN_BASES) == 18
    assert sum(len(bases) for bases in KNOWN_BASES.values()) == 428


def test_priority_returns_two_roles_for_the_same_path_when_it_wins_both():
    suffix = PRIORITY_SERIES_SUFFIXES[0]
    results = {
        prefix + suffix: _result(prefix + suffix, score, [index] + list(range(1, len(suffix) + 1)))
        for index, (prefix, score) in enumerate(
            (
                ("\u043f\u043b\u0430\u043d", 600),
                ("\u0441\u043a\u0430\u043d", 550),
                ("\u0437\u043e\u043d\u0434", 500),
            )
        )
    }

    selected = [item for item in select_series(results) if item["suffix"] == suffix]

    assert [item["role"] for item in selected] == ["main", "value"]
    assert selected[0]["suffix_path"] == selected[1]["suffix_path"]
    assert all(len(serialize_series(item)["words"]) == 3 for item in selected)


def test_physical_bundle_identity_and_table_aware_extraction():
    suffix = PRIORITY_SERIES_SUFFIXES[0]
    scan = _result(
        "\u0441\u043a\u0430\u043d" + suffix, 600, [4, 5, 6, 8] + list(range(1, len(suffix) + 1))
    )
    same_cell = _result(
        "\u043f\u043b\u0430\u043d" + suffix, 600, [5, 6, 7, 8] + list(range(1, len(suffix) + 1))
    )
    other_cell = _result(
        "\u043f\u043b\u0430\u043d" + suffix, 600, [5, 6, 7, 9] + list(range(1, len(suffix) + 1))
    )

    scan_feature = _word_features(scan, suffix)
    assert scan_feature["base_length"] == 3
    assert scan_feature["known"] and scan_feature["short_known"]
    assert scan_feature["bundle"] == _word_features(same_cell, suffix)["bundle"]
    assert scan_feature["bundle"] != _word_features(other_cell, suffix)["bundle"]


def test_priority_suppresses_redundant_nested_ordinary_suffix():
    priority = PRIORITY_SERIES_SUFFIXES[0]
    results = {
        prefix + priority: _result(
            prefix + priority, score, [index] + list(range(1, len(priority) + 1))
        )
        for index, (prefix, score) in enumerate(
            (("a", 900), ("b", 800), ("c", 700), ("d", 600), ("e", 500))
        )
    }

    selected = select_series(results)
    assert [(item["suffix"], item["role"]) for item in selected[:2]] == [
        (priority, "main"),
        (priority, "value"),
    ]
    assert "\u043e\u0432\u0430\u043d\u0438\u0435" not in {item["suffix"] for item in selected}


def test_main_and_value_horizons_do_not_reward_words_after_the_window():
    suffix = PRIORITY_SERIES_SUFFIXES[0]
    main_members = [
        _result(f"a{index}" + suffix, 500, [index, index + 1] + list(range(1, len(suffix) + 1)))
        for index in range(30)
    ]
    value_members = [
        _result(f"b{index}" + suffix, 700, [index, index + 1] + list(range(1, len(suffix) + 1)))
        for index in range(20)
    ]
    main_series = _series_metrics(suffix, list(range(1, len(suffix) + 1)), main_members)
    value_series = _series_metrics(suffix, list(range(1, len(suffix) + 1)), value_members)

    assert _main_key(main_series) == _main_key(
        _series_metrics(suffix, main_series["suffix_path"], main_members[:25])
    )
    assert _value_key(value_series) == _value_key(
        _series_metrics(suffix, value_series["suffix_path"], value_members[:15])
    )


def test_value_penalty_and_small_group_protection():
    suffix = PRIORITY_SERIES_SUFFIXES[0]
    short = _series_metrics(
        suffix,
        list(range(1, len(suffix) + 1)),
        [_result("aaaaa" + suffix, 720, list(range(13))) for _ in range(3)],
    )
    long = _series_metrics(
        suffix,
        list(range(1, len(suffix) + 1)),
        [_result("aaaaaaaaaa" + suffix, 760, list(range(18))) for _ in range(3)],
    )
    healthy = _series_metrics(
        suffix,
        list(range(2, len(suffix) + 2)),
        [_result("bbbbb" + suffix, 700, list(range(13))) for _ in range(12)],
    )

    assert _value_key(short) < _value_key(long)
    assert _value_key(healthy) < _value_key(long)


def test_table_aware_main_prefers_short_known_words_over_higher_scores():
    suffix = PRIORITY_SERIES_SUFFIXES[0]

    def member(prefix, score, link_cell):
        name = prefix + suffix
        ids = list(range(len(prefix) - 1)) + [link_cell] + list(range(1, len(suffix) + 1))
        return _result(name, score, ids)

    familiar = _series_metrics(
        suffix,
        [1] * len(suffix),
        [
            member("\u0441\u043a\u0430\u043d", 520, 20),
            member("\u043f\u043b\u0430\u043d", 540, 21),
            member("\u0437\u043e\u043d\u0434", 560, 22),
        ],
    )
    expensive_unknown = _series_metrics(
        suffix,
        [2] * len(suffix),
        [
            member("qqq", 900, 20),
            member("www", 880, 21),
            member("eee", 860, 22),
        ],
    )

    assert _main_key(familiar) < _main_key(expensive_unknown)


def test_fallback_main_ignores_known_table_and_favors_short_concentrated_words():
    suffix = PRIORITY_SERIES_SUFFIXES[5]

    def member(prefix, score, link_cell):
        name = prefix + suffix
        ids = list(range(len(prefix) - 1)) + [link_cell] + list(range(1, len(suffix) + 1))
        return _result(name, score, ids)

    table_matching_but_longer = [
        member("\u0441\u043a\u0430\u043d", 900, 20),
        member("\u043f\u043b\u0430\u043d", 880, 20),
        member("\u0434\u043e\u043c\u0438\u043d", 860, 20),
    ]
    short_unknown = [
        member("\u044b\u043d", 500, 20),
        member("\u044e\u043d", 500, 20),
        member("\u044d\u043d", 500, 20),
    ]

    assert _word_features(table_matching_but_longer[0], suffix)["known"]

    longer_series = _series_metrics(
        suffix,
        [3] * len(suffix),
        table_matching_but_longer,
    )
    short_series = _series_metrics(
        suffix,
        [4] * len(suffix),
        short_unknown,
    )

    assert _main_key(short_series) < _main_key(longer_series)

    spread_series = _series_metrics(
        suffix,
        [5] * len(suffix),
        [
            member("\u044b\u043d", 500, 20),
            member("\u044e\u043d", 500, 21),
            member("\u044d\u043d", 500, 22),
        ],
    )

    assert _main_key(short_series) < _main_key(spread_series)
