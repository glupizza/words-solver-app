import importlib
from pathlib import Path

from flask import Blueprint

from backend.tools import benchmark_grail_search, debug_grail_pipeline
from backend.words_solver.dictionary import load_words

ASSETS = Path(__file__).resolve().parents[1] / "assets"
DEFAULT_DICTIONARY = ASSETS / "cleaned_filtered_russian_words_no_past.json"


def test_cleaned_dictionary_contents():
    words = load_words(DEFAULT_DICTIONARY)
    assert len(words) == len(set(words)) == 120429
    assert set(
        "\u0445\u043e\u0434\u0438\u0432\u0448\u0438\u0439 \u043d\u043e\u0441\u0438\u0432\u0448\u0438\u0439 \u0430\u0433\u0438\u0442\u0438\u0440\u043e\u0432\u0430\u0432\u0448\u0438\u0439 \u043b\u0430\u043a\u0438\u0440\u043e\u0432\u0430\u0432\u0448\u0438\u0439 \u0435\u0445\u0430\u0432\u0448\u0438\u0439 \u0448\u0435\u0434\u0448\u0438\u0439 "
        "\u043f\u0440\u0438\u043d\u0435\u0441\u0448\u0438\u0439 \u0430\u0433\u0438\u0442\u0438\u0440\u043e\u0432\u0430\u0432\u0448\u0438\u0439\u0441\u044f \u043e\u0442\u0447\u0438\u0442\u0430\u0432\u0448\u0438\u0439\u0441\u044f \u0440\u0430\u0437\u043e\u0448\u0435\u0434\u0448\u0438\u0439\u0441\u044f".split()
    ).isdisjoint(words)
    assert set(
        "\u0438\u0434\u0443\u0449\u0438\u0439 \u0435\u0434\u0443\u0449\u0438\u0439 \u0432\u0435\u0434\u0443\u0449\u0438\u0439 \u043b\u0443\u0447\u0448\u0438\u0439 \u043c\u043b\u0430\u0434\u0448\u0438\u0439 \u0432\u044b\u0441\u0448\u0438\u0439".split()
    ).issubset(words)


def test_tool_dictionary_defaults_and_override(monkeypatch, tmp_path):
    monkeypatch.delenv("DICTIONARY_PATH", raising=False)
    for tool in (benchmark_grail_search, debug_grail_pipeline):
        assert tool._dictionary_path() == DEFAULT_DICTIONARY
    alternative = tmp_path / "alternative.json"
    monkeypatch.setenv("DICTIONARY_PATH", str(alternative))
    for tool in (benchmark_grail_search, debug_grail_pipeline):
        assert tool._dictionary_path() == alternative


def test_app_loads_one_dictionary_for_both_tries(monkeypatch, tmp_path):
    import dotenv

    from backend.words_solver import dictionary, model, routes

    observed = []
    monkeypatch.setattr(dotenv, "load_dotenv", lambda: None)
    monkeypatch.setattr(model, "load_letter_model", lambda _path: object())
    monkeypatch.setattr(dictionary, "build_trie", lambda words: tuple(words))

    def capture_routes(model, trie, batch_tries):
        observed.append((trie, batch_tries))
        return Blueprint("test_routes", __name__)

    monkeypatch.setattr(routes, "create_routes", capture_routes)
    monkeypatch.delenv("DICTIONARY_PATH", raising=False)
    app_module = importlib.import_module("backend.app")
    app = app_module.create_app()
    assert app.test_client().get("/ready").get_json()["words_loaded"] == 120429
    all_words, batches = observed[-1]
    assert len(all_words) == 120429
    for suffixes, batch_words in batches:
        assert batch_words == tuple(word for word in all_words if word.lower().endswith(suffixes))

    alternative = tmp_path / "alternative.json"
    alternative.write_text(
        '["\u0445\u043e\u0434\u0438\u0432\u0448\u0438\u0439", "\u043f\u043b\u0430\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435"]',
        encoding="utf-8",
    )
    monkeypatch.setenv("DICTIONARY_PATH", str(alternative))
    app_module.create_app()
    assert len(observed[-1][0]) == 2
    assert observed[-1][1][0][1] == (
        "\u043f\u043b\u0430\u043d\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435",
    )
