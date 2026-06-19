from .word_search import find_words


class GridValidationError(ValueError):
    pass


def _is_russian_letter(value):
    return ("\u0430" <= value <= "\u044f") or value == "\u0451"


def validate_grid(payload):
    if not isinstance(payload, dict) or "grid" not in payload:
        raise GridValidationError("Field 'grid' is required")

    grid = payload["grid"]
    if not isinstance(grid, list) or not grid:
        raise GridValidationError("Field 'grid' must be a non-empty two-dimensional array")

    rows = len(grid)
    if rows < 2 or rows > 9:
        raise GridValidationError("Grid must contain from 2 to 9 rows")

    first_row = grid[0]
    if not isinstance(first_row, list) or not first_row:
        raise GridValidationError("Grid must be a rectangular two-dimensional array")

    cols = len(first_row)
    if cols < 2 or cols > 9:
        raise GridValidationError("Grid must contain from 2 to 9 columns")

    normalized_grid = []
    for row_index, row in enumerate(grid):
        if not isinstance(row, list) or len(row) != cols:
            raise GridValidationError("Grid must be rectangular")

        normalized_row = []
        for col_index, value in enumerate(row):
            if not isinstance(value, str):
                raise GridValidationError(
                    f"Cell [{row_index}, {col_index}] must contain one Russian letter"
                )

            letter = value.strip().lower()
            if len(letter) != 1 or not _is_russian_letter(letter):
                raise GridValidationError(
                    f"Cell [{row_index}, {col_index}] must contain one Russian letter"
                )

            normalized_row.append(letter)
        normalized_grid.append(normalized_row)

    return normalized_grid


def solve_grid(payload, trie):
    grid = validate_grid(payload)
    board = [[(letter, None) for letter in row] for row in grid]
    found_words = find_words(board, trie=trie, include_paths=True)

    words = [
        {
            "word": word,
            "score": result["score"],
            "path": result["path"],
        }
        for word, result in found_words.items()
    ]
    words.sort(key=lambda item: item["score"], reverse=True)

    return {
        "grid": grid,
        "words": words,
    }
