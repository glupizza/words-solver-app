import io

from flask import Flask
from PIL import Image

from backend.words_solver import routes


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
