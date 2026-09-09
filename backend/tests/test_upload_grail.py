import io
import json

from flask import Flask
from PIL import Image

from backend.words_solver import routes
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


def test_upload_grail_stream_yields_priority_before_full_and_reuses_board(monkeypatch):
    calls = []
    preparation_calls = 0
    priority_card = {"suffix": PRIORITY_SERIES_SUFFIXES[0], "role": "main"}
    ordinary_card = {"suffix": "\u0442\u0438\u0440\u043e\u0432\u0430\u0442\u044c", "role": "value"}

    def search(letters, multipliers, trie):
        calls.append((letters, multipliers, trie))
        if len(calls) == 1:
            return (
                {"\u0430": {}},
                [priority_card, ordinary_card],
                {
                    "grail_search_seconds": 0.2,
                    "series_processing_seconds": 0.03,
                },
            )
        return (
            {"\u0430": {}},
            [priority_card],
            {
                "grail_search_seconds": 0.5,
                "series_processing_seconds": 0.06,
            },
        )

    client, prepared, priority_trie, full_trie = _stream_client(monkeypatch, search)

    def prepare_once(_paths, _model):
        nonlocal preparation_calls
        preparation_calls += 1
        return prepared

    monkeypatch.setattr(routes, "prepare_grail_board", prepare_once)
    response = client.post("/upload-grail-stream", data={"images": _files(5)}, buffered=False)

    assert response.status_code == 200
    assert response.mimetype == "application/x-ndjson"
    iterator = iter(response.response)
    priority = json.loads(next(iterator))
    assert priority["type"] == "priority"
    assert priority["series"] == [priority_card]
    assert len(calls) == 1
    assert calls[0][0] is prepared["cell_letters"]
    assert calls[0][1] is prepared["multipliers"]
    assert calls[0][2] is priority_trie

    complete = json.loads(next(iterator))
    assert complete["type"] == "complete"
    assert complete["debug"]["cell_letters"] == [[["\u0430"]]]
    assert complete["words"] == [{"name": "\u0430\u0431", "score": 10, "path": [0, 1]}]
    assert complete["meta"] == {"total_found": 1, "returned_words": 1, "returned_series": 1}
    assert len(calls) == 2
    assert calls[1][0] is prepared["cell_letters"]
    assert calls[1][1] is prepared["multipliers"]
    assert calls[1][2] is full_trie
    assert preparation_calls == 1
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
