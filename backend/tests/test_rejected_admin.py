import os
import time

import pytest
from flask import Flask
from werkzeug.security import generate_password_hash

from backend.words_solver.admin import create_admin_routes
from backend.words_solver.rejected import RejectedStore, normalize_word


@pytest.fixture
def store(tmp_path):
    return RejectedStore(tmp_path / "rejected.sqlite3")


@pytest.fixture
def client(store):
    app = Flask(__name__)
    app.secret_key = "test-key"
    app.config["ADMIN_PASSWORD_HASH"] = generate_password_hash("correct-password")
    app.register_blueprint(create_admin_routes(store))
    return app.test_client()


def csrf(client):
    return client.get("/api/admin/session").get_json()["csrf_token"]


def post(client, path, value, token):
    return client.post(path, json=value, headers={"X-CSRF-Token": token})


def login(client):
    response = post(client, "/api/admin/login", {"password": "correct-password"}, csrf(client))
    assert response.status_code == 200
    return response.get_json()["csrf_token"]


def test_storage_normalization_and_reopening(store):
    assert store.snapshot() == frozenset()
    word = normalize_word("  ЁЖ  ")
    store.reject(word)
    store.reject(word)
    assert RejectedStore(store.path).snapshot() == {"ёж"}
    store.restore(word)
    store.restore(word)
    assert store.snapshot() == frozenset()
    for invalid in ("", "а' OR 1=1 --", "a", "я" * 26, None):
        with pytest.raises(ValueError):
            normalize_word(invalid)


def test_removed_database_is_not_recreated(store):
    os.unlink(store.path)
    with pytest.raises(Exception):
        store.snapshot()
    assert not store.path.exists()


def test_auth_csrf_export_and_revocation(client, store):
    assert client.get("/api/admin/rejected").status_code == 401
    assert client.get("/api/admin/rejected/export").status_code == 401
    assert post(client, "/api/admin/rejected", {"word": "ёж"}, "invalid").status_code == 401
    token = csrf(client)
    assert post(client, "/api/admin/login", {"password": "wrong"}, token).status_code == 401
    assert (
        post(client, "/api/admin/login", {"password": "correct-password"}, "bad").status_code == 403
    )
    token = login(client)
    assert post(client, "/api/admin/rejected", {"word": "ЁЖ"}, "bad").status_code == 403
    assert post(client, "/api/admin/rejected", {"word": " ЁЖ "}, token).status_code == 200
    assert client.get("/api/admin/rejected?search=Ё").get_json()["words"][0]["word"] == "ёж"
    assert client.get("/api/admin/rejected/export").data == "ёж\n".encode()
    assert post(client, "/api/admin/rejected/restore", {"word": "ёж"}, token).status_code == 200
    assert store.snapshot() == frozenset()
    with client.session_transaction() as saved:
        old_session = dict(saved)
    assert post(client, "/api/admin/logout", {}, token).status_code == 200
    with client.session_transaction() as saved:
        saved.update(old_session)
    assert client.get("/api/admin/rejected").status_code == 401


def test_rate_limit_shared_across_clients(client):
    token = csrf(client)
    for _ in range(5):
        assert post(client, "/api/admin/login", {"password": "wrong"}, token).status_code == 401
    assert (
        post(client, "/api/admin/login", {"password": "correct-password"}, token).status_code == 429
    )


def test_expired_server_session_and_password_change(client, store):
    login(client)
    with client.session_transaction() as saved:
        session_id = saved["session_id"]
    with store.connect() as db:
        db.execute(
            "UPDATE admin_sessions SET expires_at = ? WHERE token = ?",
            (time.time() - 1, session_id),
        )
    assert client.get("/api/admin/rejected").status_code == 401
    login(client)
    client.application.config["ADMIN_PASSWORD_HASH"] = generate_password_hash("new-password")
    assert client.get("/api/admin/rejected").status_code == 401


def test_corrupt_database_reports_error(client, store):
    token = login(client)
    store.path.write_bytes(b"not a database")
    response = post(client, "/api/admin/rejected", {"word": "кот"}, token)
    assert response.status_code == 503
    assert response.get_json()["error_code"] == "database_error"


def test_grail_filter_before_selection_and_best_limit(monkeypatch):
    from backend.words_solver import grail_processing as gp

    suffix = gp.GRAIL_SERIES_SUFFIXES[0]
    results = {}
    for i in range(40):
        name = chr(0x400 + i) + suffix
        results[name] = {
            "name": name,
            "score": 500 + i,
            "path": tuple((0, j % 5, c) for j, c in enumerate(name)),
        }

    def search(_letters, _multipliers, _trie, series_results=None):
        if series_results is not None:
            series_results.update(results)
        return results.copy()

    monkeypatch.setattr(gp, "find_grail_words", search)
    rejected = frozenset(list(results)[-5:])
    filtered, series, _ = gp.search_grail_board(None, None, None, rejected)
    route = series[0]["routes"][0]
    assert len(filtered) == 35
    assert route["good_count"] == 30
    assert set(member["name"] for member in route["good_members"]).isdisjoint(rejected)
    assert min(member["score"] for member in route["good_members"]) == 505
    assert route["average_score"] == sum(member["score"] for member in route["good_members"]) / 30
    best, _ = gp.search_grail_best_words(None, None, None, rejected)
    assert set(best).isdisjoint(rejected)
    assert set(gp.top_words(best)[0]) == {"name", "score", "path"}


def test_stream_uses_one_snapshot(monkeypatch, store):
    import io
    import json

    from PIL import Image

    from backend.words_solver import routes

    def image():
        data = io.BytesIO()
        Image.new("RGB", (2, 2)).save(data, format="PNG")
        data.seek(0)
        return data, "image.png", "image/png"

    store.reject("ёж")
    observed = []
    prepared = {"cell_letters": [], "multipliers": [], "timings": {}, "debug": {}}
    monkeypatch.setattr(routes, "prepare_grail_board", lambda *_args: prepared)

    def search(_letters, _multipliers, _trie, rejected):
        observed.append(rejected)
        store.restore("ёж")
        store.reject("кот")
        return {}, [], {"grail_search_seconds": 0, "series_processing_seconds": 0}

    monkeypatch.setattr(routes, "search_grail_board", search)
    monkeypatch.setattr(
        routes,
        "search_grail_best_words",
        lambda _a, _b, _c, rejected: (observed.append(rejected) or {}, 0),
    )
    app = Flask(__name__)
    app.register_blueprint(
        routes.create_routes(
            object(),
            object(),
            batch_tries=[(("x",), object()), (("y",), object())],
            rejected_store=store,
        )
    )
    client = app.test_client()
    response = client.post("/upload-grail-stream", data={"images": [image() for _ in range(5)]})
    assert [json.loads(line)["type"] for line in response.data.splitlines()] == [
        "priority",
        "series_batch",
        "complete",
    ]
    assert observed == [frozenset({"ёж"})] * 3
    observed.clear()
    client.post("/upload-grail-stream", data={"images": [image() for _ in range(5)]}).data
    assert observed[0] == frozenset({"кот"})


def test_normal_upload_uses_current_snapshot(monkeypatch, store):
    import io

    from PIL import Image

    from backend.words_solver import routes

    monkeypatch.setattr(
        routes,
        "process_image",
        lambda *_args, **_kwargs: {
            "words": [{"name": "ёж", "score": 7}, {"name": "кот", "score": 8}]
        },
    )
    app = Flask(__name__)
    app.register_blueprint(routes.create_routes(object(), object(), rejected_store=store))
    client = app.test_client()

    def upload():
        image = io.BytesIO()
        Image.new("RGB", (2, 2)).save(image, format="PNG")
        image.seek(0)
        return client.post("/upload", data={"image": (image, "image.png", "image/png")}).get_json()

    store.reject("ёж")
    assert upload() == {"words": [{"name": "кот", "score": 8}]}
    store.restore("ёж")
    assert len(upload()["words"]) == 2


def test_rate_limit_separates_clients_and_ignores_untrusted_headers(client):
    token = csrf(client)
    path = "/api/admin/login"
    for i in range(5):
        response = client.post(
            path,
            json={"password": "wrong"},
            headers={
                "X-CSRF-Token": token,
                "X-Forwarded-For": f"198.51.100.{i + 1}",
                "X-Real-IP": f"198.51.100.{i + 1}",
            },
            environ_base={"REMOTE_ADDR": "203.0.113.1"},
        )
        assert response.status_code == 401
    assert (
        client.post(
            path,
            json={"password": "correct-password"},
            headers={"X-CSRF-Token": token, "X-Real-IP": "198.51.100.200"},
            environ_base={"REMOTE_ADDR": "203.0.113.1"},
        ).status_code
        == 429
    )
    assert (
        client.post(
            path,
            json={"password": "correct-password"},
            headers={"X-CSRF-Token": token},
            environ_base={"REMOTE_ADDR": "203.0.113.2"},
        ).status_code
        == 200
    )


def test_trusted_proxy_overwritten_header_and_scoped_reset(client, store):
    import ipaddress

    client.application.config["TRUSTED_PROXY_CIDRS"] = (ipaddress.ip_network("127.0.0.1/32"),)
    token = csrf(client)
    path = "/api/admin/login"

    def attempt(ip, password, forwarded="192.0.2.200"):
        return client.post(
            path,
            json={"password": password},
            headers={"X-CSRF-Token": token, "X-Real-IP": ip, "X-Forwarded-For": forwarded},
        )

    for _ in range(5):
        assert attempt("203.0.113.10", "wrong").status_code == 401
    assert attempt("203.0.113.10", "correct-password").status_code == 429
    assert attempt("203.0.113.11", "correct-password").status_code == 200
    token = csrf(client)
    assert attempt("203.0.113.10", "correct-password").status_code == 429
    with store.connect() as db:
        assert db.execute("SELECT count(*) FROM login_attempts").fetchone()[0] == 5


def test_rate_limit_migration_expiry_and_shared_connections(tmp_path):
    import sqlite3

    path = tmp_path / "old.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE login_attempts (id INTEGER PRIMARY KEY, attempted_at REAL NOT NULL)"
        )
        db.execute("INSERT INTO login_attempts (attempted_at) VALUES (?)", (1000,))
    first = RejectedStore(path)
    second = RejectedStore(path)
    for _ in range(5):
        assert first.login_attempt("client-a", 1000)
    assert not second.login_attempt("client-a", 1001)
    assert second.login_attempt("client-b", 1001)
    second.clear_attempts("client-b")
    assert not first.login_attempt("client-a", 1002)
    assert first.login_attempt("client-a", 1901)


def test_rate_limit_atomic_across_simultaneous_connections(store):
    from concurrent.futures import ThreadPoolExecutor

    def attempt(_):
        return RejectedStore(store.path).login_attempt("same-client", 1000)

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(attempt, range(12)))
    assert sum(results) == 5


def test_csrf_rotation_login_mutations_logout_and_login_again(client):
    initial = csrf(client)
    first = post(client, "/api/admin/login", {"password": "correct-password"}, initial)
    assert first.status_code == 200
    authenticated = first.get_json()["csrf_token"]
    assert authenticated != initial
    assert post(client, "/api/admin/rejected", {"word": "кот"}, initial).status_code == 403
    assert post(client, "/api/admin/rejected", {"word": "кот"}, authenticated).status_code == 200
    assert (
        post(client, "/api/admin/rejected/restore", {"word": "кот"}, authenticated).status_code
        == 200
    )
    assert post(client, "/api/admin/logout", {}, initial).status_code == 403
    logout = post(client, "/api/admin/logout", {}, authenticated)
    assert logout.status_code == 200
    anonymous = logout.get_json()["csrf_token"]
    assert anonymous not in (initial, authenticated)
    assert (
        post(
            client, "/api/admin/login", {"password": "correct-password"}, authenticated
        ).status_code
        == 403
    )
    second = post(client, "/api/admin/login", {"password": "correct-password"}, anonymous)
    assert second.status_code == 200
    assert second.get_json()["csrf_token"] not in (initial, authenticated, anonymous)
