"""Trie search for a fixed-size Grail board with per-cell letter choices."""

GRID_SIZE = 5
CELL_COUNT = GRID_SIZE * GRID_SIZE
WORD_MULTIPLIER_FACTORS = (1, 2, 3, 6)
RUSSIAN_LETTERS = frozenset(
    "\u0430\u0431\u0432\u0433\u0434\u0435\u0451\u0436\u0437\u0438\u0439\u043a\u043b\u043c\u043d\u043e\u043f\u0440\u0441\u0442\u0443\u0444\u0445\u0446\u0447\u0448\u0449\u044a\u044b\u044c\u044d\u044e\u044f"
)


def _build_neighbours():
    neighbours = []
    for row in range(GRID_SIZE):
        for col in range(GRID_SIZE):
            cell_neighbours = []
            for row_delta in (-1, 0, 1):
                for col_delta in (-1, 0, 1):
                    if row_delta == 0 and col_delta == 0:
                        continue
                    next_row = row + row_delta
                    next_col = col + col_delta
                    if 0 <= next_row < GRID_SIZE and 0 <= next_col < GRID_SIZE:
                        cell_neighbours.append(next_row * GRID_SIZE + next_col)
            neighbours.append(tuple(cell_neighbours))
    return tuple(neighbours)


NEIGHBOURS = _build_neighbours()


def _validate_grid_shape(grid, name):
    try:
        row_count = len(grid)
    except TypeError as exc:
        raise ValueError(f"{name} must be a {GRID_SIZE}x{GRID_SIZE} grid") from exc

    if row_count != GRID_SIZE:
        raise ValueError(f"{name} must be a {GRID_SIZE}x{GRID_SIZE} grid")
    for row in grid:
        try:
            column_count = len(row)
        except TypeError as exc:
            raise ValueError(f"{name} must be a {GRID_SIZE}x{GRID_SIZE} grid") from exc
        if column_count != GRID_SIZE:
            raise ValueError(f"{name} must be a {GRID_SIZE}x{GRID_SIZE} grid")


def _prepare_cell_letters(cell_letters):
    _validate_grid_shape(cell_letters, "cell_letters")
    prepared = []
    for row in cell_letters:
        for cell in row:
            if isinstance(cell, str):
                raise ValueError("each Grail cell must be a collection of letters, not a string")
            try:
                letters = tuple(sorted(set(cell)))
            except TypeError as exc:
                raise ValueError("each Grail cell must be an iterable of letters") from exc
            if not 1 <= len(letters) <= 5:
                raise ValueError("each Grail cell must contain between 1 and 5 unique letters")
            if any(letter not in RUSSIAN_LETTERS for letter in letters):
                raise ValueError("each Grail cell must contain single Russian letters")
            prepared.append(letters)
    return tuple(prepared)


def _prepare_multipliers(multipliers):
    _validate_grid_shape(multipliers, "multipliers")
    return tuple(multiplier for row in multipliers for multiplier in row)


def find_grail_words(cell_letters, multipliers, trie):
    """Find dictionary words on a 5x5 Grail board.

    ``cell_letters`` contains an iterable of one to five letter variants per
    position.  Results are keyed by word and include its production-compatible
    score and the highest-scoring geometric path.  Equal scores retain the
    first deterministic traversal path.
    """
    prepared_letters = _prepare_cell_letters(cell_letters)
    flat_multipliers = _prepare_multipliers(multipliers)
    letter_score_factors = tuple(
        2 if multiplier == "x2" else 3 if multiplier == "x3" else 1
        for multiplier in flat_multipliers
    )
    word_multiplier_bits = tuple(
        1 if multiplier == "c2" else 2 if multiplier == "c3" else 0
        for multiplier in flat_multipliers
    )
    found_words = {}
    path_letters = []
    path_positions = []

    def visit(position, node, visited, score_state):
        raw_score = score_state >> 2

        if len(path_letters) > 1 and node.is_end_of_word:
            word = "".join(path_letters)
            score = raw_score * WORD_MULTIPLIER_FACTORS[score_state & 3]
            previous = found_words.get(word)
            if previous is None or score > previous["score"]:
                found_words[word] = {
                    "name": word,
                    "score": score,
                    "path": tuple(
                        (cell // GRID_SIZE, cell % GRID_SIZE, letter)
                        for cell, letter in zip(path_positions, path_letters, strict=True)
                    ),
                }

        children = node.children
        if not children:
            return
        children_get = children.get

        for next_position in NEIGHBOURS[position]:
            next_bit = 1 << next_position
            if visited & next_bit:
                continue
            for letter in prepared_letters[next_position]:
                child = children_get(letter)
                if child is None:
                    continue
                path_letters.append(letter)
                path_positions.append(next_position)
                next_score_state = (
                    (score_state & ~3)
                    + (len(path_letters) * letter_score_factors[next_position] << 2)
                    | (score_state & 3)
                    | word_multiplier_bits[next_position]
                )
                visit(next_position, child, visited | next_bit, next_score_state)
                path_positions.pop()
                path_letters.pop()

    for position in range(CELL_COUNT):
        for letter in prepared_letters[position]:
            child = trie.root.children.get(letter)
            if child is None:
                continue
            path_letters.append(letter)
            path_positions.append(position)
            visit(
                position,
                child,
                1 << position,
                letter_score_factors[position] << 2 | word_multiplier_bits[position],
            )
            path_positions.pop()
            path_letters.pop()

    return found_words
