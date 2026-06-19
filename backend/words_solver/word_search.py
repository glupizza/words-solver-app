import itertools


def calculate_word_score(word, letter_multipliers, word_multipliers):
    total_score = 0
    for i, _letter in enumerate(word):
        base_score = i + 1
        if letter_multipliers[i] == "x2":
            base_score *= 2
        elif letter_multipliers[i] == "x3":
            base_score *= 3
        total_score += base_score

    if "c2" in word_multipliers:
        total_score *= 2
    if "c3" in word_multipliers:
        total_score *= 3
    return total_score


def find_words(board_rus, trie, grid_size=None, include_paths=False):
    found_words = {}

    rows = len(board_rus)
    cols = len(board_rus[0]) if rows else 0
    if grid_size is not None:
        rows = grid_size
        cols = grid_size

    directions = [
        (-1, -1),
        (-1, 0),
        (-1, 1),
        (0, -1),
        (0, 1),
        (1, -1),
        (1, 0),
        (1, 1),
    ]

    def dfs(x, y, path, path_coords, visited, letter_multipliers, word_multipliers):
        word = "".join(path)

        if not trie.starts_with(word):
            return

        if len(word) > 1 and trie.search(word):
            score = calculate_word_score(word, letter_multipliers, word_multipliers)
            prev = found_words.get(word)
            prev_score = prev["score"] if include_paths and prev is not None else prev
            if prev is None or score > prev_score:
                if include_paths:
                    found_words[word] = {"score": score, "path": path_coords}
                else:
                    found_words[word] = score

        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if 0 <= nx < rows and 0 <= ny < cols and (nx, ny) not in visited:
                next_letter, multiplier = board_rus[nx][ny]
                dfs(
                    nx,
                    ny,
                    path + [next_letter],
                    path_coords + [[nx, ny]],
                    visited | {(nx, ny)},
                    letter_multipliers + [multiplier],
                    word_multipliers + ([multiplier] if multiplier in ["c2", "c3"] else []),
                )

    for i, j in itertools.product(range(rows), range(cols)):
        letter, multiplier = board_rus[i][j]
        dfs(
            i,
            j,
            [letter],
            [[i, j]],
            {(i, j)},
            [multiplier],
            [multiplier] if multiplier in ["c2", "c3"] else [],
        )

    return found_words
