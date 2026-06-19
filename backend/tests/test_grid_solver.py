import pytest

from backend.words_solver.dictionary import build_trie
from backend.words_solver.grid_solver import GridValidationError, solve_grid, validate_grid


def test_validate_grid_normalizes_letters():
    payload = {
        "grid": [
            ["\u041a", "\u041e", "\u0422"],  # КОТ
            ["\u0430", "\u0440", "\u0435"],
        ]
    }

    assert validate_grid(payload) == [
        ["\u043a", "\u043e", "\u0442"],
        ["\u0430", "\u0440", "\u0435"],
    ]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"grid": []},
        {"grid": [["\u043a"]]},
        {"grid": [["\u043a", "\u043e"], ["\u0442"]]},
        {"grid": [["\u043a", "ab"], ["\u043e", "\u0442"]]},
        {"grid": [["\u043a", "1"], ["\u043e", "\u0442"]]},
    ],
)
def test_validate_grid_rejects_invalid_payloads(payload):
    with pytest.raises(GridValidationError):
        validate_grid(payload)


def test_solve_grid_returns_words_with_paths():
    trie = build_trie(["\u043a\u043e\u0442"])  # кот
    payload = {
        "grid": [
            ["\u043a", "\u043e", "\u0442"],
            ["\u0430", "\u0440", "\u0435"],
        ]
    }

    result = solve_grid(payload, trie=trie)

    assert result["grid"] == payload["grid"]
    assert result["words"] == [
        {
            "word": "\u043a\u043e\u0442",
            "score": 6,
            "path": [[0, 0], [0, 1], [0, 2]],
        }
    ]
