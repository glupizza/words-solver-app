import logging
import os
import tempfile
import time

from flask import Blueprint, request
from PIL import Image, UnidentifiedImageError

from . import metrics
from .grid_solver import GridValidationError, solve_grid
from .http import error_response, json_response
from .image_processing import process_image

logger = logging.getLogger(__name__)


def create_routes(model, trie):
    bp = Blueprint("routes", __name__)

    allowed_mime_types = {"image/png", "image/jpeg", "image/jpg", "image/webp"}

    @bp.get("/api/documents")
    def documents():
        return json_response({"documents": []}, status=200)

    @bp.post("/solve-grid")
    def solve_grid_endpoint():
        payload = request.get_json(silent=True)
        if payload is None:
            return error_response(
                code="bad_request",
                message="Request body must be valid JSON",
                status=400,
            )

        try:
            result = solve_grid(payload, trie=trie)
        except GridValidationError as e:
            return error_response(code="bad_request", message=str(e), status=400)
        except Exception:
            logger.exception("solve_grid failed")
            return error_response(code="internal_error", message="Grid solving failed", status=500)

        return json_response(result, status=200)

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

            img = Image.open(file.stream)
            img = img.convert("RGB")
            img = img.resize((590, 1280), Image.Resampling.LANCZOS)

            fd, tmp_path = tempfile.mkstemp(suffix=".jpg")
            os.close(fd)
            img.save(tmp_path, format="JPEG", quality=95)

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

    return bp
