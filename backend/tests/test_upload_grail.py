import io
import json

from flask import Flask
from PIL import Image

from backend.words_solver import routes
from backend.words_solver.grail_constants import GRAIL_SUFFIX_BATCHES
from backend.words_solver.grail_processing import (
    PRIORITY_SERIES_SUFFIXES,
    priority_dictionary_words,
)


def _image():
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def _files(count, mimetype="image/png"):
    return [(_image(), f"board-{index}.png", mimetype) for index in range(count)]


def _client(monkeypatch):
    monkeypatch.setattr(
        routes,
        "process_grail_images",
        lambda paths, model, trie: {
            "words": [{"name": "\u0430\u0431", "score": 10, "path": [0, 1]}],
            "series": [],
            "meta": {"total_found": 1, "returned_words": 1, "returned_series": 0},
            "timings": {},
            "debug": {},
        },
    )
    app = Flask(__name__)
    app.register_blueprint(routes.create_routes(model=object(), trie=object()))
    return app.test_client()


def test_upload_grail_requires_exactly_five_images(monkeypatch):
    client = _client(monkeypatch)

    assert client.post("/upload-grail").status_code == 400
    for count in (1, 2, 3, 4, 6):
        response = client.post("/upload-grail", data={"images": _files(count)})
        assert response.status_code == 400
        assert response.get_json()["error_code"] == "bad_request"


def test_upload_grail_rejects_invalid_or_unsupported_files(monkeypatch):
    client = _client(monkeypatch)
    unsupported = client.post("/upload-grail", data={"images": _files(5, "image/gif")})
    invalid = client.post(
        "/upload-grail",
        data={"images": [(io.BytesIO(b"no"), f"bad-{i}.png", "image/png") for i in range(5)]},
    )

    assert unsupported.status_code == 415
    assert unsupported.get_json()["error_code"] == "unsupported_media_type"
    assert invalid.status_code == 400
    assert invalid.get_json()["error_code"] == "bad_request"


def test_upload_grail_success_and_processing_error(monkeypatch):
    client = _client(monkeypatch)
    response = client.post("/upload-grail", data={"images": _files(5)})
    assert response.status_code == 200
    assert response.mimetype == "application/json"
    assert set(response.get_json()) == {"words", "series", "meta"}

    def fail(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "process_grail_images", fail)
    failed = client.post("/upload-grail", data={"images": _files(5)})
    assert failed.status_code == 500
    assert failed.get_json()["error_code"] == "internal_error"


def test_upload_grail_multiplier_conflict_is_bad_request(monkeypatch):
    client = _client(monkeypatch)

    def fail(*_args, **_kwargs):
        raise routes.GrailMultiplierConflict("multiplier inconsistency at R2C4: {'c3': 1, 'x3': 4}")

    monkeypatch.setattr(routes, "process_grail_images", fail)

    response = client.post("/upload-grail", data={"images": _files(5)})

    assert response.status_code == 400
    assert response.get_json()["error_code"] == "bad_request"


def test_upload_grail_preserves_native_image_bytes(monkeypatch):
    originals = []
    files = []

    for index in range(5):
        buffer = io.BytesIO()
        Image.new(
            "RGB",
            (10 + index, 10 + index),
            (index * 20, index * 20, index * 20),
        ).save(buffer, format="PNG")

        payload = buffer.getvalue()
        originals.append(payload)
        files.append(
            (
                io.BytesIO(payload),
                f"board-{index}.png",
                "image/png",
            )
        )

    captured = []

    def capture(paths, model, trie):
        captured.extend(open(path, "rb").read() for path in paths)
        return {
            "words": [],
            "series": [],
            "meta": {
                "total_found": 0,
                "returned_words": 0,
                "returned_series": 0,
            },
            "timings": {},
            "debug": {},
        }

    monkeypatch.setattr(routes, "process_grail_images", capture)

    app = Flask(__name__)
    app.register_blueprint(routes.create_routes(model=object(), trie=object()))
    client = app.test_client()

    response = client.post(
        "/upload-grail",
        data={"images": files},
    )

    assert response.status_code == 200
    assert captured == originals


def _stream_client(monkeypatch, search):
    prepared = {
        "cell_letters": [[{"\u0430"} for _ in range(5)] for _ in range(5)],
        "multipliers": [[None for _ in range(5)] for _ in range(5)],
        "timings": {"ocr_all_5_seconds": 1.0, "merge_seconds": 0.1},
        "debug": {"cell_letters": [[{"\u0430"}]], "multipliers": []},
    }
    monkeypatch.setattr(routes, "prepare_grail_board", lambda _paths, _model: prepared)
    monkeypatch.setattr(routes, "search_grail_board", search)
    monkeypatch.setattr(routes, "serialize_series", lambda item: item)
    monkeypatch.setattr(
        routes,
        "grail_result_from_search",
        lambda _prepared, results, series, _timings: {
            "words": [{"name": "\u0430\u0431", "score": 10, "path": [0, 1]}],
            "series": series,
            "meta": {
                "total_found": len(results),
                "returned_words": 1,
                "returned_series": len(series),
            },
            "timings": {},
            "debug": _prepared["debug"],
        },
    )
    app = Flask(__name__)
    priority_trie = object()
    full_trie = object()
    app.register_blueprint(
        routes.create_routes(model=object(), trie=full_trie, priority_trie=priority_trie)
    )
    return app.test_client(), prepared, priority_trie, full_trie


def test_upload_grail_stream_yields_each_batch_before_full_search(monkeypatch):
    calls = []
    prepared_calls = []
    prepared = {
        "cell_letters": [[{"a"}] * 5 for _ in range(5)],
        "multipliers": [[None] * 5 for _ in range(5)],
        "timings": {"ocr_all_5_seconds": 0.1, "merge_seconds": 0.0},
        "debug": {},
    }

    def prepare(*_args):
        prepared_calls.append(1)
        return prepared

    def search(_letters, _multipliers, batch):
        calls.append(batch)
        series = [] if batch == 1 else [{"suffix": GRAIL_SUFFIX_BATCHES[batch][0]}]
        return {}, series, {"grail_search_seconds": 0.1, "series_processing_seconds": 0.01}

    def best(*_args):
        calls.append("full")
        return {}, 0.2

    monkeypatch.setattr(routes, "prepare_grail_board", prepare)
    monkeypatch.setattr(routes, "search_grail_board", search)
    monkeypatch.setattr(routes, "search_grail_best_words", best)
    monkeypatch.setattr(routes, "serialize_series", lambda item: item)
    monkeypatch.setattr(
        routes,
        "grail_result_from_search",
        lambda _prepared, _results, series, timings: {
            "series": series,
            "words": [],
            "timings": timings,
        },
    )
    app = Flask(__name__)
    app.register_blueprint(
        routes.create_routes(
            object(),
            object(),
            batch_tries=list(zip(GRAIL_SUFFIX_BATCHES, range(len(GRAIL_SUFFIX_BATCHES)))),
        )
    )
    response = app.test_client().post(
        "/upload-grail-stream", data={"images": _files(5)}, buffered=False
    )
    iterator = iter(response.response)
    all_cards = []
    for index, suffixes in enumerate(GRAIL_SUFFIX_BATCHES):
        event = json.loads(next(iterator))
        assert event["type"] == ("priority" if index == 0 else "series_batch")
        assert event["meta"]["suffixes"] == list(suffixes)
        assert len(event["series"]) <= 3
        assert calls == list(range(index + 1))
        all_cards.extend(event["series"])
    complete = json.loads(next(iterator))
    assert complete["type"] == "complete"
    assert complete["series"] == all_cards
    assert calls[-1] == "full"
    assert complete["timings"]["processed_batches"] == 10
    assert len(prepared_calls) == 1
    response.close()


def test_upload_grail_stream_uses_json_validation_errors_before_streaming(monkeypatch):
    client, _prepared, _priority_trie, _full_trie = _stream_client(monkeypatch, lambda *_args: None)

    response = client.post("/upload-grail-stream", data={"images": _files(4)})

    assert response.status_code == 400
    assert response.mimetype == "application/json"
    assert response.get_json()["error_code"] == "bad_request"


def test_upload_grail_stream_yields_error_after_priority_when_full_search_fails(monkeypatch):
    calls = 0

    def search(_letters, _multipliers, _trie):
        nonlocal calls
        calls += 1
        if calls == 1:
            return (
                {"\u0430": {}},
                [{"suffix": PRIORITY_SERIES_SUFFIXES[0], "role": "main"}],
                {
                    "grail_search_seconds": 0.2,
                    "series_processing_seconds": 0.03,
                },
            )
        raise RuntimeError("full failure")

    client, _prepared, _priority_trie, _full_trie = _stream_client(monkeypatch, search)
    response = client.post("/upload-grail-stream", data={"images": _files(5)}, buffered=False)
    iterator = iter(response.response)

    assert json.loads(next(iterator))["type"] == "priority"
    error = json.loads(next(iterator))
    assert error["type"] == "error"
    assert error["error_code"] == "internal_error"
    assert "full failure" not in error["error"]
    response.close()


def test_priority_dictionary_words_uses_exact_lowercase_suffix_matching():
    words = [
        "\u041f\u041b\u0410\u041d\u0418\u0420\u041e\u0412\u0410\u041d\u0418\u0415",
        "\u043f\u0435\u0440\u0435\u0441\u0442\u0440\u043e\u0435\u043d\u0438\u0435",
        "\u043d\u0435\u043f\u043e\u0434\u0445\u043e\u0434\u0438\u0442",
        "\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435\u043c",
    ]

    assert priority_dictionary_words(words) == words[:2]


def test_stream_filters_series_in_both_phases_with_fixed_suffix(monkeypatch):
    from backend.words_solver import grail_processing

    suffix = PRIORITY_SERIES_SUFFIXES[0]
    results = {}
    for index in range(10):
        name = chr(0x430 + index) + suffix
        path = [(0, 0, name[0])] + [
            (position // 5, position % 5, letter) for position, letter in enumerate(suffix, start=1)
        ]
        results[name] = {"name": name, "score": 500 if index < 8 else 269, "path": path}
    prepared = {
        "cell_letters": [[{"a"}] * 5 for _ in range(5)],
        "multipliers": [[None] * 5 for _ in range(5)],
        "timings": {"ocr_all_5_seconds": 0.0, "merge_seconds": 0.0},
        "debug": {},
    }
    monkeypatch.setattr(routes, "prepare_grail_board", lambda *_args: prepared)

    def search(*_args, series_results=None):
        if series_results is not None:
            series_results.update(results)
        return results

    monkeypatch.setattr(grail_processing, "find_grail_words", search)
    app = Flask(__name__)
    app.register_blueprint(
        routes.create_routes(model=object(), trie=object(), priority_trie=object())
    )
    response = app.test_client().post("/upload-grail-stream", data={"images": _files(5)})
    events = [json.loads(line) for line in response.get_data(as_text=True).splitlines()]
    assert [event["type"] for event in events] == ["priority"] + ["series_batch"] * 9 + ["complete"]
    assert events[0]["series"] == events[-1]["series"]
    card = events[0]["series"][0]
    assert card["suffix"] == suffix
    route = card["routes"][0]
    assert card["good_count"] == len(route["words"]) == 8
    assert all(
        word["score"] == 500 and word["path"][-len(suffix) :] == route["suffix_path"]
        for word in route["words"]
    )


def test_stream_cross_batch_overlapping_suffixes_do_not_repeat_words(monkeypatch):
    from backend.words_solver import grail_processing

    specific = GRAIL_SUFFIX_BATCHES[5][-1]
    broad = GRAIL_SUFFIX_BATCHES[6][0]
    assert specific.endswith(broad)
    results = {}
    for offset, ending in ((0, specific), (20, broad)):
        for index in range(8):
            name = chr(0x430 + offset + index) + ending
            path = [(0, 0, name[0])] + [
                (position // 5, position % 5, letter)
                for position, letter in enumerate(ending, start=1)
            ]
            results[name] = {"name": name, "score": 500, "path": path}
    prepared = {
        "cell_letters": [[{"a"}] * 5 for _ in range(5)],
        "multipliers": [[None] * 5 for _ in range(5)],
        "timings": {"ocr_all_5_seconds": 0.0, "merge_seconds": 0.0},
        "debug": {},
    }
    monkeypatch.setattr(routes, "prepare_grail_board", lambda *_args: prepared)

    def search(_letters, _multipliers, suffixes, *, series_results=None):
        found = {name: item for name, item in results.items() if name.endswith(suffixes)}
        if series_results is not None:
            series_results.update(found)
        return found

    monkeypatch.setattr(grail_processing, "find_grail_words", search)
    app = Flask(__name__)
    app.register_blueprint(
        routes.create_routes(
            object(),
            (specific, broad),
            batch_tries=[(batch, batch) for batch in GRAIL_SUFFIX_BATCHES],
        )
    )
    response = app.test_client().post("/upload-grail-stream", data={"images": _files(5)})
    events = [json.loads(line) for line in response.get_data(as_text=True).splitlines()]
    assert [card["suffix"] for card in events[5]["series"]] == [specific]
    assert [card["suffix"] for card in events[6]["series"]] == [broad]
    cards = events[-1]["series"]
    names = [word["name"] for card in cards for route in card["routes"] for word in route["words"]]
    assert len(names) == len(set(names)) == 16
    assert cards == [
        grail_processing.serialize_series(card) for card in grail_processing.select_series(results)
    ]


def test_new_batch_overlap_caps_specific_and_returns_remaining_in_broad(monkeypatch):
    from backend.words_solver import grail_processing
    from backend.words_solver.grail_constants import GRAIL_SERIES_SUFFIXES

    specific, broad = GRAIL_SERIES_SUFFIXES[9], GRAIL_SERIES_SUFFIXES[25]
    results = {}
    for start, count, ending in ((0x400, 40, specific), (0x500, 8, broad)):
        for index in range(count):
            name = chr(start + index) + ending
            # Identical trailing cells give the broad ending one physical route.
            tail = list(range(1, len(specific) + 1))[-len(ending) :]
            path = [(0, 0, name[0])] + [
                (position // 5, position % 5, letter)
                for position, letter in zip(tail, ending, strict=True)
            ]
            results[name] = {"name": name, "score": 500 + index, "path": path}
    prepared = {
        "cell_letters": [[{"a"}] * 5 for _ in range(5)],
        "multipliers": [[None] * 5 for _ in range(5)],
        "timings": {"ocr_all_5_seconds": 0.0, "merge_seconds": 0.0},
        "debug": {},
    }
    monkeypatch.setattr(routes, "prepare_grail_board", lambda *_args: prepared)

    def search(_letters, _multipliers, suffixes, *, series_results=None):
        found = {name: item for name, item in results.items() if name.endswith(suffixes)}
        if series_results is not None:
            series_results.update(found)
        return found

    monkeypatch.setattr(grail_processing, "find_grail_words", search)
    app = Flask(__name__)
    app.register_blueprint(
        routes.create_routes(
            object(),
            (specific, broad),
            batch_tries=[(batch, batch) for batch in GRAIL_SUFFIX_BATCHES],
        )
    )
    response = app.test_client().post("/upload-grail-stream", data={"images": _files(5)})
    events = [json.loads(line) for line in response.get_data(as_text=True).splitlines()]
    assert [event["type"] for event in events] == ["priority"] + ["series_batch"] * 9 + ["complete"]
    cards = events[-1]["series"]
    assert [card["suffix"] for card in cards] == [specific, broad]
    assert [card["good_count"] for card in cards] == [30, 18]
    assert cards == [
        grail_processing.serialize_series(card) for card in grail_processing.select_series(results)
    ]
    names = [word["name"] for card in cards for route in card["routes"] for word in route["words"]]
    assert len(names) == len(set(names)) == 48


def test_stream_complete_keeps_best_300_including_low_scores(monkeypatch):
    prepared = {
        "cell_letters": [[{"a"}] * 5 for _ in range(5)],
        "multipliers": [[None] * 5 for _ in range(5)],
        "timings": {"ocr_all_5_seconds": 0.0, "merge_seconds": 0.0},
        "debug": {},
    }
    monkeypatch.setattr(routes, "prepare_grail_board", lambda *_args: prepared)
    monkeypatch.setattr(
        routes,
        "search_grail_board",
        lambda *_args: ({}, [], {"grail_search_seconds": 0.0, "series_processing_seconds": 0.0}),
    )
    results = {
        f"word{i}": {"name": f"word{i}", "score": i % 270, "path": [(0, 0, "a")]}
        for i in range(350)
    }
    monkeypatch.setattr(routes, "search_grail_best_words", lambda *_args: (results, 0.0))
    app = Flask(__name__)
    app.register_blueprint(routes.create_routes(object(), object()))
    response = app.test_client().post("/upload-grail-stream", data={"images": _files(5)})
    complete = json.loads(response.get_data(as_text=True).splitlines()[-1])
    assert complete["type"] == "complete"
    assert complete["meta"]["total_found"] == 350
    assert complete["meta"]["returned_words"] == len(complete["words"]) == 300
    assert all(word["score"] <= 269 for word in complete["words"])
    assert complete["series"] == []
