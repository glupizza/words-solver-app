import json
import logging
import os
import shutil
import tempfile
import time

from flask import Blueprint, Response, request, stream_with_context
from PIL import Image, UnidentifiedImageError

from . import metrics
from .grail_processing import (
    PRIORITY_SERIES_SUFFIXES,
    GrailMultiplierConflict,
    grail_result_from_search,
    prepare_grail_board,
    process_grail_images,
    search_grail_board,
    serialize_series,
)
from .http import error_response, json_response
from .image_processing import process_image
from .logging_config import request_id_var

logger = logging.getLogger(__name__)


def _validate_grail_files(files, allowed_mime_types):
    if len(files) != 5:
        return error_response(
            code="bad_request", message="Exactly five images are required", status=400
        )
    if any(not file.filename for file in files):
        return error_response(code="bad_request", message="No selected file", status=400)
    for file in files:
        mimetype = (getattr(file, "mimetype", None) or "").lower()
        if mimetype and mimetype not in allowed_mime_types:
            return error_response(
                code="unsupported_media_type", message="Unsupported image type", status=415
            )
        try:
            probe = Image.open(file.stream)
            probe.verify()
        except (UnidentifiedImageError, Image.DecompressionBombError):
            return error_response(code="bad_request", message="Invalid image", status=400)
        finally:
            try:
                file.stream.seek(0)
            except Exception:
                pass
    return None


def _save_grail_files(files):
    suffix_by_mimetype = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/webp": ".webp",
    }
    paths = []
    try:
        for file in files:
            mimetype = (getattr(file, "mimetype", None) or "").lower()
            fd, path = tempfile.mkstemp(suffix=suffix_by_mimetype.get(mimetype, ".img"))
            with os.fdopen(fd, "wb") as temporary_file:
                shutil.copyfileobj(file.stream, temporary_file)
            paths.append(path)
        return paths
    except Exception:
        _remove_grail_files(paths)
        raise


def _remove_grail_files(paths):
    for path in paths:
        try:
            os.remove(path)
        except OSError:
            logger.exception("failed to remove grail tmp file tmp_path=%s", path)


def _json_default(value):
    if isinstance(value, set):
        return sorted(value)
    raise TypeError(f"{type(value).__name__} is not JSON serializable")


def _ndjson_event(payload):
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            default=_json_default,
        )
        + "\n"
    )


def create_routes(model, trie, priority_trie=None):
    bp = Blueprint("routes", __name__)
    priority_trie = priority_trie or trie

    allowed_mime_types = {"image/png", "image/jpeg", "image/jpg", "image/webp"}

    @bp.get("/api/documents")
    def documents():
        return json_response({"documents": []}, status=200)

    @bp.post("/upload")
    def upload_file():
        start = time.perf_counter()
        metrics.inc("app_upload_requests_total")

        if "image" not in request.files:
            logger.info("upload missing image part")
            return error_response(code="bad_request", message="No image part", status=400)

        file = request.files["image"]
        if not file.filename:
            logger.info("upload empty filename")
            return error_response(code="bad_request", message="No selected file", status=400)

        mimetype = (getattr(file, "mimetype", None) or "").lower()
        if mimetype and mimetype not in allowed_mime_types:
            logger.info("upload unsupported mimetype=%s filename=%s", mimetype, file.filename)
            return error_response(
                code="unsupported_media_type",
                message="Unsupported image type",
                status=415,
            )

        logger.info(
            "upload start filename=%s content_type=%s",
            file.filename,
            getattr(file, "content_type", None),
        )

        tmp_path = None
        try:
            try:
                img_probe = Image.open(file.stream)
                img_probe.verify()
            except (UnidentifiedImageError, Image.DecompressionBombError) as e:
                logger.info(
                    "upload invalid image filename=%s err=%s",
                    file.filename,
                    type(e).__name__,
                )
                return error_response(code="bad_request", message="Invalid image", status=400)
            finally:
                try:
                    file.stream.seek(0)
                except Exception:
                    pass

            suffix_by_mimetype = {
                "image/png": ".png",
                "image/jpeg": ".jpg",
                "image/jpg": ".jpg",
                "image/webp": ".webp",
            }
            fd, tmp_path = tempfile.mkstemp(suffix=suffix_by_mimetype.get(mimetype, ".img"))
            with os.fdopen(fd, "wb") as temporary_file:
                shutil.copyfileobj(file.stream, temporary_file)

            t0 = time.perf_counter()
            result = process_image(tmp_path, model=model, trie=trie)
            elapsed = time.perf_counter() - t0

            metrics.add("app_process_image_seconds_sum", elapsed)
            metrics.inc("app_process_image_seconds_count")

            logger.info("upload ok seconds=%.3f", time.perf_counter() - start)
            return json_response(result, status=200)

        except Exception:
            metrics.inc("app_upload_failures_total")
            logger.exception("upload failed seconds=%.3f", time.perf_counter() - start)
            return error_response(code="internal_error", message="Upload failed", status=500)

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    logger.exception("failed to remove tmp file tmp_path=%s", tmp_path)

    @bp.post("/upload-grail")
    def upload_grail():
        files = request.files.getlist("images")
        validation_error = _validate_grail_files(files, allowed_mime_types)
        if validation_error is not None:
            return validation_error
        paths = []
        try:
            paths = _save_grail_files(files)
            result = process_grail_images(paths, model=model, trie=trie)
            result.pop("timings", None)
            result.pop("debug", None)
            return json_response(result, status=200)
        except GrailMultiplierConflict as exc:
            logger.info("grail multiplier conflict err=%s", exc)
            return error_response(code="bad_request", message=str(exc), status=400)
        except Exception:
            logger.exception("grail upload failed")
            return error_response(code="internal_error", message="Upload failed", status=500)
        finally:
            _remove_grail_files(paths)

    @bp.post("/upload-grail-stream")
    def upload_grail_stream():
        files = request.files.getlist("images")
        validation_error = _validate_grail_files(files, allowed_mime_types)
        if validation_error is not None:
            return validation_error
        paths = []
        try:
            paths = _save_grail_files(files)
            prepared = prepare_grail_board(paths, model)
            fast_results, fast_series, fast_timings = search_grail_board(
                prepared["cell_letters"], prepared["multipliers"], priority_trie
            )
            priority_series = [
                serialize_series(item)
                for item in fast_series
                if item["suffix"] in PRIORITY_SERIES_SUFFIXES
            ]
            priority_timings = {
                **prepared["timings"],
                "priority_search_seconds": fast_timings["grail_search_seconds"],
                "priority_series_processing_seconds": fast_timings["series_processing_seconds"],
            }
            priority_timings["time_to_priority_seconds"] = sum(priority_timings.values())
            priority_event = {
                "type": "priority",
                "series": priority_series,
                "meta": {
                    "phase": "priority",
                    "priority_result_count": len(fast_results),
                    "returned_series": len(priority_series),
                },
                "timings": priority_timings,
            }
        except GrailMultiplierConflict as exc:
            logger.info("grail multiplier conflict err=%s", exc)
            return error_response(code="bad_request", message=str(exc), status=400)
        except Exception:
            logger.exception("grail stream preparation failed")
            return error_response(code="internal_error", message="Upload failed", status=500)
        finally:
            _remove_grail_files(paths)

        request_id = request_id_var.get() or "-"

        @stream_with_context
        def generate():
            yield _ndjson_event(priority_event)
            try:
                full_results, full_series, full_timings = search_grail_board(
                    prepared["cell_letters"], prepared["multipliers"], trie
                )
                complete = grail_result_from_search(
                    prepared, full_results, full_series, full_timings
                )
                complete["type"] = "complete"
                complete["timings"].update(priority_timings)
                complete["timings"]["request_core_seconds"] = (
                    priority_timings["time_to_priority_seconds"]
                    + full_timings["grail_search_seconds"]
                    + full_timings["series_processing_seconds"]
                )
                yield _ndjson_event(complete)
            except Exception:
                logger.exception("grail stream full search failed")
                yield _ndjson_event(
                    {
                        "type": "error",
                        "error": "Upload failed",
                        "error_code": "internal_error",
                        "request_id": request_id,
                    }
                )

        response = Response(generate(), content_type="application/x-ndjson; charset=utf-8")
        response.headers["Cache-Control"] = "no-cache"
        response.headers["X-Accel-Buffering"] = "no"
        return response

    return bp
