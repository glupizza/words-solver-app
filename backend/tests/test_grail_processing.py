import pytest

from backend.words_solver.grail_processing import (
    KNOWN_BASES,
    PRIORITY_SERIES_SUFFIXES,
    GrailMultiplierConflict,
    _main_key,
    _merge_series_by_suffix,
    _series_metrics,
    _suppresses,
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


def _series_results(suffix, scores, prefixes):
    return {
        prefix + suffix: _result(prefix + suffix, score, [index] + list(range(1, len(suffix) + 1)))
        for index, (prefix, score) in enumerate(zip(prefixes, scores))
    }


def test_minimum_unique_members_and_complete_serialization():
    suffix = "longtail"
    results = _series_results(suffix, [399] * 31, [chr(0x400 + i) for i in range(31)])
    assert select_series(dict(list(results.items())[:7])) == []
    assert select_series(dict(list(results.items())[:8]))
    series = select_series(results)[0]
    payload = serialize_series(series)
    assert payload["good_count"] == len(payload["words"]) == 31
    assert len({word["name"] for word in payload["words"]}) == 31
    assert payload["average_score"] == 399
    assert all(
        word["path"][-len(payload["suffix"]) :] == payload["suffix_path"]
        for word in payload["words"]
    )


def test_nested_groups_prefer_broad_and_keep_independent_paths():
    suffix = "\u0438\u0432\u0430\u043d\u0438\u0435"
    nested = "\u043a" + suffix
    results = _series_results(nested, [500] * 10, [chr(0x400 + i) for i in range(10)])
    for i in range(20):
        name = chr(0x430 + i) + suffix
        results[name] = _result(name, 500, [i] + list(range(2, len(suffix) + 2)))
    other = "othend"
    results.update(_series_results(other, [500] * 8, [chr(0x450 + i) for i in range(8)]))
    selected = select_series(results)
    assert suffix in {item["suffix"] for item in selected}
    assert nested not in {item["suffix"] for item in selected}
    assert other in {item["suffix"] for item in selected}
    for series in selected:
        assert all(
            serialize_word(word)["path"][-len(series["suffix"]) :] == series["suffix_path"]
            for word in series["good_members"]
        )


def test_identical_nested_members_choose_broad_suffix():
    broad = "\u0438\u0432\u0430\u043d\u0438\u0435"
    nested = "\u043a" + broad
    results = _series_results(nested, [500] * 20, [chr(0x400 + i) for i in range(20)])
    selected = select_series(results)
    assert [item["suffix"] for item in selected] == [broad]
    assert selected == select_series(dict(reversed(list(results.items()))))


def test_nested_different_paths_do_not_suppress_each_other():
    nested = PRIORITY_SERIES_SUFFIXES[0]
    broad = nested[-6:]
    results = _series_results(nested, [500] * 8, [chr(0x400 + i) for i in range(8)])
    for i in range(9):
        name = chr(0x430 + i) + broad
        results[name] = _result(name, 500, [i] + list(range(12, 18)))
    selected = select_series(results)
    assert {item["suffix"] for item in selected} == {broad, nested}
    assert all(
        serialize_word(member)["path"][-len(item["suffix"]) :] == item["suffix_path"]
        for item in selected
        for member in item["good_members"]
    )


def test_partial_overlap_requires_compatible_path_and_mostly_shared_words():
    broad = _series_metrics(
        "suffix", [2, 3, 4, 5, 6, 7], [_result(str(i), 500, [i]) for i in range(10)]
    )
    shared = [_result(str(i), 500, [i]) for i in range(8)]
    nested = _series_metrics(
        "xsuffix", [1, 2, 3, 4, 5, 6, 7], shared + [_result("a", 500, [1]), _result("b", 500, [1])]
    )
    independent = _series_metrics(
        "xsuffix",
        nested["suffix_path"],
        shared[:7] + [_result(str(i), 500, [1]) for i in range(10, 13)],
    )
    different_path = _series_metrics("xsuffix", [8, 9, 10, 11, 12, 13, 14], shared)
    assert _suppresses(broad, nested)
    assert not _suppresses(broad, independent)
    assert not _suppresses(broad, different_path)


def test_priority_identical_roles_are_not_duplicated():
    suffix = PRIORITY_SERIES_SUFFIXES[0]
    results = _series_results(suffix, [500] * 8, [chr(0x400 + i) for i in range(8)])
    series = [item for item in select_series(results) if item["suffix"] == suffix]
    assert [item["role"] for item in series] == ["main"]


def test_distinct_priority_paths_stay_adjacent_and_preserve_word_paths():
    suffix = PRIORITY_SERIES_SUFFIXES[5]
    results = _series_results(suffix, [500] * 8, [chr(0x400 + i) for i in range(8)])
    for i in range(8):
        prefix = "abcdefgh" + chr(0x430 + i)
        name = prefix + suffix
        results[name] = _result(name, 900, list(range(9)) + list(range(10, 10 + len(suffix))))
    other = _series_results("otherend", [600] * 8, [chr(0x450 + i) for i in range(8)])
    results.update(other)
    selected = select_series(results)
    positions = [i for i, item in enumerate(selected) if item["suffix"] == suffix]
    assert len(positions) == 2 and positions[1] == positions[0] + 1
    assert [selected[i]["role"] for i in positions] == ["main", "value"]
    assert selected[positions[0]]["suffix_path"] != selected[positions[1]]["suffix_path"]
    for i in positions:
        item = serialize_series(selected[i])
        assert all(word["path"][-len(suffix) :] == item["suffix_path"] for word in item["words"])


def test_ranking_prefers_more_high_scoring_words():
    results = _series_results("firsttail", [500] * 6 + [300] * 2, list("abcdefgh"))
    results.update(_series_results("secondtail", [500] * 2 + [300] * 6, list("ijklmnop")))
    assert [item["suffix"] for item in select_series(results)][:2] == ["sttail", "ndtail"]


def test_alternative_dictionary_words_are_not_filtered(monkeypatch):
    from backend.words_solver import grail_processing

    suffix = "\u043e\u0432\u0430\u0432\u0448\u0438\u0439"
    results = _series_results(suffix, [500] * 8, [chr(0x430 + i) for i in range(8)])
    monkeypatch.setattr(grail_processing, "find_grail_words", lambda *_args: results)
    found, series, _timings = grail_processing.search_grail_board(None, None, None)
    assert found == results
    assert len(series) == 1
    assert serialize_series(series[0])["good_count"] == 8


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


def test_known_base_asset_has_expected_shape():
    assert len(KNOWN_BASES) == 18
    assert sum(len(bases) for bases in KNOWN_BASES.values()) == 428


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
