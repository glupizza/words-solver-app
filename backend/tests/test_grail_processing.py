import pytest

from backend.words_solver.grail_processing import (
    GRAIL_SERIES_SUFFIXES,
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


def _group(suffix, count, start, path, score=500):
    return {
        chr(start + i) + suffix: _result(chr(start + i) + suffix, score, [i % 25] + path)
        for i in range(count)
    }


def test_fixed_suffixes_exact_order():
    expected = (
        "\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u0438\u0440\u043e\u0432\u0430\u0442\u044c\u0441\u044f \u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0438\u0440\u043e\u0432\u0430\u043d\u043d\u044b\u0439 \u0438\u0440\u043e\u0432\u043a\u0430 \u0441\u0442\u0440\u043e\u0435\u043d\u0438\u0435 \u0430\u0441\u043a\u0438\u0432\u0430\u043d\u0438\u0435 \u0430\u0441\u043a\u0438\u0432\u0430\u0442\u044c\u0441\u044f "
        "\u0430\u0441\u043a\u0438\u0432\u0430\u0442\u044c \u0430\u0440\u0438\u0432\u0430\u043d\u0438\u0435 \u0430\u0440\u0438\u0432\u0430\u0442\u044c\u0441\u044f \u0430\u0440\u0438\u0432\u0430\u0442\u044c \u0442\u0430\u0442\u044c\u0441\u044f \u0442\u0430\u0442\u044c \u0435\u043d\u043d\u044b\u0439 \u0442\u0435\u043b\u044c\u043d\u044b\u0439 \u0447\u0435\u0441\u043a\u0438\u0439 "
        "\u043d\u043d\u043e\u0441\u0442\u044c \u043d\u043e\u0441\u0442\u044c \u0432\u0435\u0434\u0435\u043d\u0438\u0435 \u043e\u0431\u0440\u0430\u0437\u043e\u0432\u0430\u043d\u0438\u0435 \u0432\u043e\u0434\u0441\u0442\u0432\u043e"
    ).split()
    assert list(GRAIL_SERIES_SUFFIXES) == expected


def test_fixed_order_and_unknown_endings_are_excluded():
    results = {}
    # Use non-overlapping endings, deliberately supplied in reverse order.
    for index in (21, 16, 5, 0):
        suffix = GRAIL_SERIES_SUFFIXES[index]
        results.update(_group(suffix, 8, 0x500 + index * 10, list(range(len(suffix)))))
    results.update(_group("randomending", 12, 0x900, list(range(12))))
    cards = [serialize_series(item) for item in select_series(results)]
    assert [item["suffix"] for item in cards] == [GRAIL_SERIES_SUFFIXES[i] for i in (0, 5, 16, 21)]
    assert len(cards) <= 22
    assert all(len(card["routes"]) <= 2 for card in cards)
    assert cards == [
        serialize_series(item) for item in select_series(dict(reversed(list(results.items()))))
    ]


@pytest.mark.parametrize("high_count", [6, 7, 8, 25])
def test_score_filter_and_minimum(high_count):
    suffix = GRAIL_SERIES_SUFFIXES[0]
    results = _group(suffix, 100, 0x400, list(range(len(suffix))), 375)
    for index, item in enumerate(results.values()):
        if index < high_count:
            item["score"] = 376 + index
    cards = select_series(results)
    if high_count < 8:
        assert cards == []
        return
    card = serialize_series(cards[0])
    route = card["routes"][0]
    assert card["good_count"] == route["good_count"] == len(route["words"]) == high_count
    assert min(word["score"] for word in route["words"]) == 376
    assert route["average_score"] == sum(range(376, 376 + high_count)) / high_count


def test_two_best_paths_and_deduplication_after_selection():
    suffix = GRAIL_SERIES_SUFFIXES[0]
    results = {}
    for index, size in enumerate((20, 15, 11, 10)):
        path = list(range(index, index + len(suffix)))
        results.update(_group(suffix, size, 0x400 + index * 30, path, 500 + index * 10))
    cards = [serialize_series(item) for item in select_series(results)]
    assert len(cards) == 1
    assert [route["good_count"] for route in cards[0]["routes"]] == [20, 15]
    assert [route["average_score"] for route in cards[0]["routes"]] == [500, 510]
    assert cards[0]["good_count"] == 35
    for route in cards[0]["routes"]:
        assert all(word["path"][-len(suffix) :] == route["suffix_path"] for word in route["words"])


def test_tie_by_top_eight_and_duplicate_words_across_routes():
    suffix = GRAIL_SERIES_SUFFIXES[0]
    first = _group(suffix, 9, 0x400, list(range(len(suffix))), 500)
    second = _group(suffix, 9, 0x430, list(range(1, len(suffix) + 1)), 600)
    shared = next(iter(first.values()))
    second["duplicate"] = _result(shared["name"], 600, [20] + list(range(1, len(suffix) + 1)))
    cards = [serialize_series(item) for item in select_series({**first, **second})]
    routes = cards[0]["routes"]
    assert [route["good_count"] for route in routes] == [10, 8]
    names = [word["name"] for route in routes for word in route["words"]]
    assert len(names) == len(set(names)) == cards[0]["good_count"]


def test_equal_route_counts_rank_by_best_eight_then_average():
    suffix = GRAIL_SERIES_SUFFIXES[0]
    results = {}
    for index, score in enumerate((500, 600, 550)):
        path = list(range(index, index + len(suffix)))
        results.update(_group(suffix, 8, 0x400 + index * 20, path, score))
    routes = serialize_series(select_series(results)[0])["routes"]
    assert [item["average_score"] for item in routes] == [600, 550]


def test_duplicate_route_members_recompute_before_minimum():
    suffix = GRAIL_SERIES_SUFFIXES[0]
    path_a = list(range(len(suffix)))
    path_b = list(range(1, len(suffix) + 1))
    results = _group(suffix, 9, 0x400, path_a)
    for index, member in enumerate(list(results.values())[:7]):
        results[("alternate", index)] = _result(member["name"], 500, [20] + path_b)
    results.update(_group(suffix, 7, 0x450, path_b))
    card = serialize_series(select_series(results)[0])
    assert [route["good_count"] for route in card["routes"]] == [14]
    names = [word["name"] for route in card["routes"] for word in route["words"]]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("specific_count", [7, 8])
def test_overlapping_suffix_specificity_and_fallback(specific_count):
    specific, broad = GRAIL_SERIES_SUFFIXES[17:19]
    path = list(range(len(specific)))
    results = _group(specific, specific_count, 0x400, path)
    results.update(_group(broad, 8, 0x430, path[-len(broad) :]))
    cards = [serialize_series(item) for item in select_series(results)]
    assert [card["suffix"] for card in cards] == (
        [broad] if specific_count == 7 else [specific, broad]
    )
    assert [card["good_count"] for card in cards] == ([15] if specific_count == 7 else [8, 8])
    names = [word["name"] for card in cards for route in card["routes"] for word in route["words"]]
    assert len(names) == len(set(names))
