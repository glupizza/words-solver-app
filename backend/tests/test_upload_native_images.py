import io
import os

from flask import Flask
from PIL import Image

from backend.words_solver import routes


def image_bytes(image_format, size):
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=image_format)
    buffer.seek(0)
    return buffer


def upload_client(monkeypatch, observed):
    def fake_process_image(path, model, trie):
        with Image.open(path) as image:
            observed.append((image.size, path, os.path.exists(path)))
        return {"words": []}

    monkeypatch.setattr(routes, "process_image", fake_process_image)
    app = Flask(__name__)
    app.register_blueprint(routes.create_routes(model=object(), trie=object()))
    return app.test_client()


def test_upload_preserves_native_png_dimensions_and_cleans_temp_file(monkeypatch):
    observed = []
    client = upload_client(monkeypatch, observed)

    response = client.post(
        "/upload",
        data={"image": (image_bytes("PNG", (1290, 2796)), "board.png", "image/png")},
    )

    assert response.status_code == 200
    assert response.get_json() == {"words": []}
    assert observed[0][0] == (1290, 2796)
    assert observed[0][2] is True
    assert not os.path.exists(observed[0][1])


def test_upload_preserves_native_jpeg_dimensions(monkeypatch):
    observed = []
    client = upload_client(monkeypatch, observed)

    response = client.post(
        "/upload",
        data={"image": (image_bytes("JPEG", (987, 1234)), "board.jpg", "image/jpeg")},
    )

    assert response.status_code == 200
    assert observed[0][0] == (987, 1234)


def test_upload_rejects_corrupt_and_unsupported_input(monkeypatch):
    observed = []
    client = upload_client(monkeypatch, observed)

    corrupt = client.post(
        "/upload", data={"image": (io.BytesIO(b"not an image"), "bad.png", "image/png")}
    )
    unsupported = client.post(
        "/upload", data={"image": (image_bytes("PNG", (8, 8)), "board.gif", "image/gif")}
    )

    assert corrupt.status_code == 400
    assert corrupt.get_json()["error_code"] == "bad_request"
    assert unsupported.status_code == 415
    assert unsupported.get_json()["error_code"] == "unsupported_media_type"
    assert observed == []


def test_upload_limit_still_rejects_oversized_request(monkeypatch):
    observed = []
    client = upload_client(monkeypatch, observed)
    client.application.config["MAX_CONTENT_LENGTH"] = 100

    response = client.post(
        "/upload", data={"image": (image_bytes("PNG", (50, 50)), "board.png", "image/png")}
    )

    assert response.status_code == 413
    assert observed == []
