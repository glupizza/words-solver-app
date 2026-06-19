from backend.words_solver.dictionary import build_trie
from backend.words_solver.word_search import calculate_word_score, find_words


def _empty_board(fill_letter="\u0430"):
    # 5x5 board filled with one letter (default: "а")
    return [[(fill_letter, None) for _ in range(5)] for _ in range(5)]


def test_calculate_word_score_with_multipliers():
    # word length 2 -> base scores: 1, 2 -> total 3
    # first letter x2 -> 2 + 2 = 4
    # word multiplier c2 -> 8
    score = calculate_word_score("ab", ["x2", None], ["c2"])
    assert score == 8


def test_find_words_basic():
    # Build a tiny dictionary
    words = [
        "\u043e\u043c\u043b\u0435\u0442",  # омлет
        "\u043c\u043b\u0435\u0442\u044c",  # млеть
    ]
    trie = build_trie(words)

    # 5x5 board of (letter, multiplier)
    # Put: омлет on first row contiguous horizontally
    board = [
        [("\u043e", None), ("\u043c", None), ("\u043b", None), ("\u0435", None), ("\u0442", None)],
        [("\u0430", None), ("\u0430", None), ("\u0430", None), ("\u0430", None), ("\u0430", None)],
        [("\u0430", None), ("\u0430", None), ("\u0430", None), ("\u0430", None), ("\u0430", None)],
        [("\u0430", None), ("\u0430", None), ("\u0430", None), ("\u0430", None), ("\u0430", None)],
        [("\u0430", None), ("\u0430", None), ("\u0430", None), ("\u0430", None), ("\u0430", None)],
    ]

    found = find_words(board, trie=trie, grid_size=5)
    assert "\u043e\u043c\u043b\u0435\u0442" in found


def test_calculate_word_score_c3_and_x3():
    # word length 3: base scores 1+2+3=6
    # all letters x3 => 3+6+9=18
    # word c3 => 54
    score = calculate_word_score("abc", ["x3", "x3", "x3"], ["c3"])
    assert score == 54


def test_find_words_disallows_reusing_cell():
    # Word "аа" would be possible only by reusing the same cell if board has a single "а".
    # But board has many "а" so make it tricky: allow only one "а" cell and others different.
    words = ["\u0430\u0430"]  # "аа"
    trie = build_trie(words)

    board = _empty_board(fill_letter="\u0431")  # fill with "б"
    board[0][0] = ("\u0430", None)  # only one "а" on the whole board

    found = find_words(board, trie=trie, grid_size=5)
    assert "\u0430\u0430" not in found


def test_find_words_allows_diagonal_moves():
    # Place "кот" on a diagonal: (0,0)->(1,1)->(2,2)
    words = ["\u043a\u043e\u0442"]  # кот
    trie = build_trie(words)

    board = _empty_board(fill_letter="\u0430")
    board[0][0] = ("\u043a", None)
    board[1][1] = ("\u043e", None)
    board[2][2] = ("\u0442", None)

    found = find_words(board, trie=trie, grid_size=5)
    assert "\u043a\u043e\u0442" in found


def test_find_words_requires_adjacent_cells():
    # Put "кот" but with gaps so adjacency is broken.
    words = ["\u043a\u043e\u0442"]  # кот
    trie = build_trie(words)

    board = _empty_board(fill_letter="\u0430")
    board[0][0] = ("\u043a", None)
    board[0][2] = ("\u043e", None)  # not adjacent to (0,0)
    board[0][4] = ("\u0442", None)  # not adjacent to (0,2)

    found = find_words(board, trie=trie, grid_size=5)
    assert "\u043a\u043e\u0442" not in found


def test_find_words_picks_best_score_when_multiple_paths():
    # Word "омлет" can be formed on row0 and row1.
    # Put a better multiplier on row1 path so it should win.
    words = ["\u043e\u043c\u043b\u0435\u0442"]  # омлет
    trie = build_trie(words)

    board = _empty_board(fill_letter="\u0430")

    # row0: омлет with no multipliers
    board[0][0] = ("\u043e", None)
    board[0][1] = ("\u043c", None)
    board[0][2] = ("\u043b", None)
    board[0][3] = ("\u0435", None)
    board[0][4] = ("\u0442", None)

    # row1: омлет with x3 on first letter (higher score)
    board[1][0] = ("\u043e", "x3")
    board[1][1] = ("\u043c", None)
    board[1][2] = ("\u043b", None)
    board[1][3] = ("\u0435", None)
    board[1][4] = ("\u0442", None)

    found = find_words(board, trie=trie, grid_size=5)

    # Base score for "омлет": 1+2+3+4+5 = 15
    # With x3 on first letter: (1*3)+2+3+4+5 = 17
    assert found["\u043e\u043c\u043b\u0435\u0442"] == 17


def test_find_words_word_multiplier_c2_applies():
    # Make "дом" horizontally, and mark first cell with word multiplier c2
    # In your rules: c2 is a word multiplier, applied if present in path.
    words = ["\u0434\u043e\u043c"]  # дом
    trie = build_trie(words)

    board = _empty_board(fill_letter="\u0430")
    board[0][0] = ("\u0434", "c2")
    board[0][1] = ("\u043e", None)
    board[0][2] = ("\u043c", None)

    found = find_words(board, trie=trie, grid_size=5)

    # "дом" base: 1+2+3=6, c2 => 12
    assert found["\u0434\u043e\u043c"] == 12


def test_find_words_uses_rectangular_board_size():
    words = ["\u043a\u043e\u0442"]  # кот
    trie = build_trie(words)

    board = [
        [("\u043a", None), ("\u043e", None), ("\u0442", None)],
        [("\u0430", None), ("\u0430", None), ("\u0430", None)],
    ]

    found = find_words(board, trie=trie)
    assert "\u043a\u043e\u0442" in found


def test_find_words_can_return_ordered_path():
    words = ["\u043a\u043e\u0442"]  # кот
    trie = build_trie(words)

    board = [
        [("\u043a", None), ("\u043e", None), ("\u0442", None)],
        [("\u0430", None), ("\u0430", None), ("\u0430", None)],
    ]

    found = find_words(board, trie=trie, include_paths=True)
    assert found["\u043a\u043e\u0442"]["score"] == 6
    assert found["\u043a\u043e\u0442"]["path"] == [[0, 0], [0, 1], [0, 2]]
