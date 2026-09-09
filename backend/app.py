import logging
import os
import time
import warnings

from dotenv import load_dotenv
from flask import Flask, Response, g, request, send_from_directory
from werkzeug.exceptions import NotFound, RequestEntityTooLarge

from backend.words_solver import metrics
from backend.words_solver.dictionary import build_trie, load_words
from backend.words_solver.grail_processing import priority_dictionary_words
from backend.words_solver.http import error_response, json_response
from backend.words_solver.logging_config import configure_logging, request_id_var, set_request_id
from backend.words_solver.model import load_letter_model
from backend.words_solver.routes import create_routes

logger = logging.getLogger(__name__)


def create_app() -> Flask:
    load_dotenv()
    configure_logging()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    assets_dir = os.path.join(base_dir, "assets")

    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "3")
    warnings.filterwarnings("ignore", category=FutureWarning)

    default_model_path = os.path.join(assets_dir, "letter_recognition_model.h5")
    default_dictionary_path = os.path.join(assets_dir, "cleaned_filtered_russian_words.json")

    model_path = os.getenv("MODEL_PATH", default_model_path)
    dictionary_path = os.getenv("DICTIONARY_PATH", default_dictionary_path)

    logger.info("using model_path=%s", model_path)
    logger.info("using dictionary_path=%s", dictionary_path)

    app = Flask(__name__, static_folder="static")

    max_upload_bytes = int(os.getenv("MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
    app.config["MAX_CONTENT_LENGTH"] = max_upload_bytes

    @app.errorhandler(RequestEntityTooLarge)
    def _handle_too_large(_e):
        return error_response(code="payload_too_large", message="File too large", status=413)

    @app.before_request
    def _before_request():
        g.request_start = time.perf_counter()

        incoming = request.headers.get("X-Request-Id")
        set_request_id(incoming)

        logger.info(
            "request start method=%s path=%s",
            getattr(request, "method", "?"),
            getattr(request, "path", "?"),
        )

    @app.after_request
    def _after_request(response):
        response.headers["X-Request-Id"] = request_id_var.get() or "-"

        rule = getattr(request, "url_rule", None)
        route = rule.rule if rule is not None else getattr(request, "path", "?")

        if route == "/<path:path>":
            logger.info("request end status=%s", response.status_code)
            return response

        labels = {
            "method": getattr(request, "method", "?"),
            "route": route,
            "status": str(getattr(response, "status_code", 0)),
        }

        request_start = getattr(g, "request_start", time.perf_counter())

        def record_request_end():
            metrics.inc("app_http_requests_total", **labels)
            elapsed = time.perf_counter() - request_start
            metrics.add("app_http_request_duration_seconds_sum", elapsed, **labels)
            metrics.inc("app_http_request_duration_seconds_count", **labels)
            logger.info("request end status=%s", response.status_code)

        if response.is_streamed:
            response.call_on_close(record_request_end)
            return response

        record_request_end()
        return response

    @app.teardown_request
    def _teardown_request(_exc):
        request_id_var.set(None)

    model = load_letter_model(model_path)
    words = load_words(dictionary_path)
    trie = build_trie(words)
    priority_trie = build_trie(priority_dictionary_words(words))

    app.register_blueprint(create_routes(model=model, trie=trie, priority_trie=priority_trie))

    @app.get("/health")
    def health():
        return json_response({"status": "ok"}, status=200)

    @app.get("/ready")
    def ready():
        return json_response(
            {
                "status": "ready",
                "model_loaded": model is not None,
                "words_loaded": len(words),
            },
            status=200,
        )

    @app.get("/metrics")
    def metrics_endpoint():
        if os.getenv("ENABLE_METRICS", "1") != "1":
            return error_response(code="not_found", message="Not found", status=404)

        text = metrics.render_prometheus()
        return Response(text, status=200, mimetype="text/plain; version=0.0.4; charset=utf-8")

    @app.route("/")
    def index():
        resp = send_from_directory(app.static_folder, "index.html")
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @app.route("/<path:path>")
    def static_files(path):
        try:
            return send_from_directory(app.static_folder, path)
        except NotFound:
            resp = send_from_directory(app.static_folder, "index.html")
            resp.headers["Cache-Control"] = "no-cache"
            return resp

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    app.run(host="0.0.0.0", port=port)
