import pytest

from backend.words_solver.dictionary import build_trie
from backend.words_solver.grail_search import find_grail_words
from backend.words_solver.trie import RUSSIAN_LETTER_BITS, Trie
from backend.words_solver.word_search import find_words


def _board(fill_letter="\u0430"):
    return [[(fill_letter, None) for _ in range(5)] for _ in range(5)]


def _letters(fill_letter="\u0430"):
    return [[{fill_letter} for _ in range(5)] for _ in range(5)]


def _multipliers():
    return [[None for _ in range(5)] for _ in range(5)]


def test_trie_populates_russian_children_masks():
    trie = build_trie(["\u0434\u043e\u043c", "\u043a\u043e\u0442", "\u0434\u043e\u043c"])

    assert trie.root.children_mask & RUSSIAN_LETTER_BITS["\u0434"]
    assert trie.root.children_mask & RUSSIAN_LETTER_BITS["\u043a"]
    assert not trie.root.children_mask & RUSSIAN_LETTER_BITS["\u043c"]
    assert trie.root.children["\u0434"].children_mask & RUSSIAN_LETTER_BITS["\u043e"]


def test_trie_non_russian_children_do_not_change_search_behavior():
    trie = Trie()
    trie.insert("cat")

    assert trie.search("cat")
    assert not trie.root.children_mask


def test_singleton_board_matches_production_word_scores():
    board = _board()
    board[0][:5] = [
        ("\u043e", None),
        ("\u043c", "x2"),
        ("\u043b", None),
        ("\u0435", "c2"),
        ("\u0442", None),
    ]
    board[1][:3] = [("\u0434", None), ("\u043e", None), ("\u043c", None)]
    trie = build_trie(["\u043e\u043c\u043b\u0435\u0442", "\u0434\u043e\u043c"])

    production_found = find_words(board, trie)
    grail_found = find_grail_words(
        [[{letter} for letter, _multiplier in row] for row in board],
        [[multiplier for _letter, multiplier in row] for row in board],
        trie,
    )

    assert {word: result["score"] for word, result in grail_found.items()} == production_found


def test_mixed_cell_options_find_word_not_present_in_a_single_layer():
    letters = _letters("\u044f")
    letters[0][0] = ["\u043a", "\u0445"]
    letters[0][1] = ["\u0445", "\u043e"]
    letters[0][2] = ["\u043e", "\u0442"]
    trie = build_trie(["\u043a\u043e\u0442"])

    found = find_grail_words(letters, _multipliers(), trie)

    assert found["\u043a\u043e\u0442"]["path"] == (
        (0, 0, "\u043a"),
        (0, 1, "\u043e"),
        (0, 2, "\u0442"),
    )


def test_grail_search_disallows_reusing_a_position():
    letters = _letters("\u0431")
    letters[0][0] = {"\u0430"}
    trie = build_trie(["\u0430\u0430"])

    assert find_grail_words(letters, _multipliers(), trie) == {}


def test_grail_search_allows_diagonal_moves():
    letters = _letters()
    letters[0][0] = {"\u043a"}
    letters[1][1] = {"\u043e"}
    letters[2][2] = {"\u0442"}
    trie = build_trie(["\u043a\u043e\u0442"])

    found = find_grail_words(letters, _multipliers(), trie)

    assert found["\u043a\u043e\u0442"]["path"] == (
        (0, 0, "\u043a"),
        (1, 1, "\u043e"),
        (2, 2, "\u0442"),
    )


def test_grail_search_keeps_highest_scoring_path():
    letters = _letters("\u044f")
    multipliers = _multipliers()
    for row in (0, 4):
        letters[row][:3] = [{"\u0434"}, {"\u043e"}, {"\u043c"}]
    multipliers[4][0] = "x3"
    trie = build_trie(["\u0434\u043e\u043c"])

    found = find_grail_words(letters, multipliers, trie)

    assert found["\u0434\u043e\u043c"]["score"] == 8
    assert found["\u0434\u043e\u043c"]["path"] == (
        (4, 0, "\u0434"),
        (4, 1, "\u043e"),
        (4, 2, "\u043c"),
    )


def test_grail_search_keeps_first_path_when_scores_are_equal():
    letters = _letters("\u044f")
    for row in (0, 1):
        letters[row][:3] = [{"\u0434"}, {"\u043e"}, {"\u043c"}]
    trie = build_trie(["\u0434\u043e\u043c"])

    found = find_grail_words(letters, _multipliers(), trie)

    assert found["\u0434\u043e\u043c"]["path"] == (
        (0, 0, "\u0434"),
        (0, 1, "\u043e"),
        (0, 2, "\u043c"),
    )


def test_grail_search_keeps_first_equal_score_path_for_same_cells():
    letters = _letters("\u044f")
    letters[0][0] = {"\u0430"}
    letters[0][1] = {"\u0430"}
    letters[1][0] = {"\u0431"}
    trie = build_trie(["\u0430\u0430\u0431"])

    found = find_grail_words(letters, _multipliers(), trie)

    assert found["\u0430\u0430\u0431"]["path"] == (
        (0, 0, "\u0430"),
        (0, 1, "\u0430"),
        (1, 0, "\u0431"),
    )


def test_grail_search_keeps_higher_score_path_for_same_cells():
    letters = _letters("\u044f")
    letters[0][0] = {"\u0430"}
    letters[0][1] = {"\u0430"}
    letters[1][0] = {"\u0431"}
    multipliers = _multipliers()
    multipliers[0][0] = "x3"
    trie = build_trie(["\u0430\u0430\u0431"])

    found = find_grail_words(letters, multipliers, trie)

    assert found["\u0430\u0430\u0431"]["score"] == 10
    assert found["\u0430\u0430\u0431"]["path"] == (
        (0, 1, "\u0430"),
        (0, 0, "\u0430"),
        (1, 0, "\u0431"),
    )


def test_grail_search_applies_c2_and_c3_once_each():
    letters = _letters("\u044f")
    letters[0][:3] = [{"\u0434"}, {"\u043e"}, {"\u043c"}]
    multipliers = _multipliers()
    multipliers[0][0] = "c2"
    multipliers[0][1] = "c3"
    multipliers[0][2] = "c3"
    trie = build_trie(["\u0434\u043e\u043c"])

    found = find_grail_words(letters, multipliers, trie)

    assert found["\u0434\u043e\u043c"]["score"] == 36


def test_grail_search_applies_x2_and_x3_by_position():
    letters = _letters("\u044f")
    letters[0][:3] = [{"\u0434"}, {"\u043e"}, {"\u043c"}]
    multipliers = _multipliers()
    multipliers[0][0] = "x2"
    multipliers[0][1] = "x3"
    trie = build_trie(["\u0434\u043e\u043c"])

    found = find_grail_words(letters, multipliers, trie)

    assert found["\u0434\u043e\u043c"]["score"] == 11


def test_grail_search_deduplicates_letters_in_a_cell():
    letters = _letters("\u044f")
    letters[0][0] = ["\u043a", "\u043a", "\u043a"]
    letters[0][1] = ["\u043e", "\u043e"]
    letters[0][2] = ["\u0442", "\u0442"]
    trie = build_trie(["\u043a\u043e\u0442"])

    found = find_grail_words(letters, _multipliers(), trie)

    assert list(found) == ["\u043a\u043e\u0442"]


@pytest.mark.parametrize(
    ("letters", "multipliers"),
    [
        (_letters()[:4], _multipliers()),
        (_letters(), _multipliers()[:4]),
        ([row[:4] for row in _letters()], _multipliers()),
    ],
)
def test_grail_search_requires_a_5x5_grid(letters, multipliers):
    trie = build_trie(["\u0430\u0430"])

    with pytest.raises(ValueError, match="5x5"):
        find_grail_words(letters, multipliers, trie)
