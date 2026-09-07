"""Create a local visual report for the production 5x5 OCR pipeline."""

import argparse
import csv
import html
import io
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
LOW_CONFIDENCE = 0.70
AMBIGUOUS_MARGIN = 0.15
GRID_SIZE = 5
_runtime = None


def configure_runtime(device):
    """Configure TensorFlow before importing Keras or loading the OCR model."""
    global _runtime
    if _runtime is not None:
        if _runtime["device_requested"] != device:
            raise RuntimeError("TensorFlow runtime is already configured for another device")
        return _runtime
    if device == "cpu":
        os.environ["CUDA_VISIBLE_DEVICES"] = "-1"
    import tensorflow as tf

    if device == "cpu":
        try:
            tf.config.set_visible_devices([], "GPU")
        except RuntimeError as exc:
            raise RuntimeError("TensorFlow GPU was initialized before CPU configuration") from exc
    import keras

    from backend.words_solver import image_processing
    from backend.words_solver.model import load_letter_model

    _runtime = {
        "device_requested": device,
        "tensorflow": tf,
        "keras": keras,
        "image_processing": image_processing,
        "load_letter_model": load_letter_model,
    }
    return _runtime


def runtime_metadata(device):
    runtime = configure_runtime(device)
    tf = runtime["tensorflow"]
    return {
        "device_requested": device,
        "tensorflow_version": tf.__version__,
        "keras_version": runtime["keras"].__version__,
        "opencv_version": cv2.__version__,
        "numpy_version": np.__version__,
        "python_version": platform.python_version(),
        "visible_gpu_count": len(tf.config.get_visible_devices("GPU")),
    }


def image_processing_runtime():
    return (_runtime or configure_runtime("cpu"))["image_processing"]


def validate_top_k(value):
    try:
        value = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--top-k must be an integer from 1 to 10") from exc
    if not 1 <= value <= 10:
        raise argparse.ArgumentTypeError("--top-k must be from 1 to 10")
    return value


def label_for(row, col):
    return f"R{row + 1}C{col + 1}"


def ranked_predictions(probabilities, top_k):
    image_processing = image_processing_runtime()
    indices = np.argsort(-np.asarray(probabilities), kind="stable")[:top_k]
    return [
        {
            "class_index": int(index),
            "letter": image_processing.TRANSLIT_TO_RUS.get(
                image_processing.CLASS_LABELS[int(index)], image_processing.CLASS_LABELS[int(index)]
            ),
            "probability": float(probabilities[index]),
        }
        for index in indices
    ]


def tensor_to_png(tensor):
    image = np.asarray(tensor)[0]
    return np.clip(image * 255.0, 0, 255).astype(np.uint8)


def load_input_image(image_path, *, legacy_upload_normalization=False):
    """Load native input, or explicitly reproduce the retired upload transform."""
    if not legacy_upload_normalization:
        return cv2.imread(str(image_path))
    with Image.open(image_path) as image:
        normalized = image.convert("RGB").resize((590, 1280), Image.Resampling.LANCZOS)
        encoded = io.BytesIO()
        normalized.save(encoded, format="JPEG", quality=95)
    return cv2.imdecode(np.frombuffer(encoded.getvalue(), dtype=np.uint8), cv2.IMREAD_COLOR)


def save_bgr(path, image):
    if not cv2.imwrite(str(path), image):
        raise RuntimeError(f"Could not write image: {path}")


def draw_text_bgr(image, text, xy, color=(0, 0, 0)):
    cv2.putText(image, text, xy, cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)


def smart_crop_overlay(original, details):
    overlay = original.copy()
    for rect in details.get("candidates") or []:
        cv2.rectangle(overlay, (rect.x0, rect.y0), (rect.x1, rect.y1), (0, 0, 255), 1)
    for rect in details.get("cluster") or []:
        cv2.rectangle(overlay, (rect.x0, rect.y0), (rect.x1, rect.y1), (0, 255, 0), 2)
        cv2.circle(overlay, (round(rect.cx), round(rect.cy)), 2, (0, 255, 0), -1)
    bbox = details.get("bbox") or details.get("fallback_bbox")
    if bbox is not None:
        cv2.rectangle(overlay, (bbox.x0, bbox.y0), (bbox.x1, bbox.y1), (255, 0, 0), 3)
    else:
        draw_text_bgr(overlay, "Fallback crop used", (10, 25), (0, 0, 255))
    return overlay


def grid_overlay(board, coordinates):
    overlay = board.copy()
    for row, col, x0, y0, x1, y1 in coordinates:
        cv2.rectangle(overlay, (x0, y0), (x1, y1), (0, 180, 0), 2)
        draw_text_bgr(overlay, label_for(row, col), (x0 + 4, y0 + 18), (0, 100, 0))
    return overlay


def multiplier_overlay(board, coordinates, multipliers):
    overlay = grid_overlay(board, coordinates)
    for row, col, x0, y0, _x1, _y1 in coordinates:
        multiplier = multipliers.get((row, col))
        if multiplier:
            cv2.rectangle(overlay, (x0, y0), (x0 + 48, y0 + 25), (0, 0, 0), -1)
            draw_text_bgr(overlay, multiplier, (x0 + 4, y0 + 18), (255, 255, 255))
    return overlay


def contact_sheet(cell_records, key, base_dir):
    tiles = []
    font = ImageFont.load_default()
    for record in cell_records:
        image = Image.open(base_dir / record[key]).convert("RGB")
        image.thumbnail((128, 128))
        tile = Image.new("RGB", (150, 170), "white")
        tile.paste(image, ((150 - image.width) // 2, 2))
        draw = ImageDraw.Draw(tile)
        draw.text((4, 132), record["label"], fill="black", font=font)
        draw.text(
            (4, 148),
            f"{record['predicted_letter']} {record['predicted_probability']:.1%}",
            fill="black",
            font=font,
        )
        tiles.append(tile)
    sheet = Image.new("RGB", (150 * GRID_SIZE, 170 * GRID_SIZE), "white")
    for index, tile in enumerate(tiles):
        sheet.paste(tile, ((index % GRID_SIZE) * 150, (index // GRID_SIZE) * 170))
    return sheet


def csv_rows(cells):
    for cell in cells:
        top = cell["top_k"]
        second = {
            "letter": cell.get("second_prediction", ""),
            "probability": cell.get("second_probability", 0.0),
        }
        yield {
            "row": cell["row"],
            "col": cell["col"],
            "prediction": cell["predicted_letter"],
            "confidence": cell["predicted_probability"],
            "second_prediction": second["letter"],
            "second_confidence": second["probability"],
            "margin": cell["top1_top2_margin"],
            "multiplier": cell["multiplier"] or "",
            "top_k": "|".join(f"{x['letter']}:{x['probability']:.6f}" for x in top),
        }


def write_csv(path, cells):
    fields = [
        "row",
        "col",
        "prediction",
        "confidence",
        "second_prediction",
        "second_confidence",
        "margin",
        "multiplier",
        "top_k",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(csv_rows(cells))


def report_html(data):
    metadata = data["metadata"]
    cells = data["cells"]
    board = data["board"]["recognized"]
    image_names = [
        "01_original.png",
        "02_smart_crop_overlay.png",
        "03_board_crop.png",
        "04_grid_overlay.png",
        "05_multiplier_overlay.png",
    ]
    images = "".join(
        f'<figure><img src="{name}"><figcaption>{name}</figcaption></figure>'
        for name in image_names
    )
    board_html = "".join(
        "<tr>" + "".join(f"<td>{html.escape(cell)}</td>" for cell in row) + "</tr>" for row in board
    )

    def cell_html(cell):
        classes = (
            "warn"
            if cell["predicted_probability"] < LOW_CONFIDENCE
            or cell["top1_top2_margin"] < AMBIGUOUS_MARGIN
            else ""
        )
        top = "<br>".join(
            f"{i + 1}. {x['letter']} {x['probability']:.1%}" for i, x in enumerate(cell["top_k"])
        )
        margin = cell["top1_top2_margin"]
        margin_text = f"{margin:.1%}" if margin is not None else "n/a"
        return f'''<article class="cell {classes}"><h3>{cell["label"]}</h3><img src="{cell["raw_image"]}"><img src="{cell["model_image"]}"><p><b>{cell["predicted_letter"]}</b> — {cell["predicted_probability"]:.1%}; margin {margin_text}<br>Multiplier: {cell["multiplier"] or "—"}</p><p>{top}</p></article>'''

    ambiguous = sorted(
        (
            c
            for c in cells
            if c["predicted_probability"] < LOW_CONFIDENCE
            or c["top1_top2_margin"] < AMBIGUOUS_MARGIN
        ),
        key=lambda c: (c["top1_top2_margin"], c["predicted_probability"]),
    )
    ambiguous_html = (
        "<br>".join(
            f"{c['label']}: {c['predicted_letter']} {c['predicted_probability']:.1%}, margin {c['top1_top2_margin']:.1%}"
            for c in ambiguous
        )
        or "None"
    )
    meta = "".join(
        f"<li><b>{html.escape(str(key))}</b>: {html.escape(str(value))}</li>"
        for key, value in metadata.items()
    )
    smart_crop = "".join(
        f"<li><b>{html.escape(str(key))}</b>: {html.escape(str(value))}</li>"
        for key, value in data.get("smart_crop", {}).items()
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Board OCR diagnostic</title><style>body{{font-family:system-ui;margin:24px}} img{{max-width:420px;max-height:420px}}figure{{display:inline-block;vertical-align:top;margin:8px}}table{{border-collapse:collapse}}td{{border:1px solid #aaa;padding:13px;font-size:1.5em}}.cell{{display:inline-block;vertical-align:top;width:310px;border:1px solid #ccc;margin:6px;padding:8px}}.cell img{{max-width:145px;max-height:145px}}.warn{{background:#fff2d7}}</style></head><body><h1>5x5 board OCR diagnostic</h1><h2>Run metadata</h2><ul>{meta}</ul><h2>Smart crop result</h2><ul>{smart_crop}</ul><h2>Original / Crop</h2>{images}<h2>Recognized board</h2><table>{board_html}</table><pre>{html.escape(data["board"]["plain_text"])}</pre><h2>Contact sheets</h2><img src="06_contact_sheet_raw.png"><img src="07_contact_sheet_model_input.png"><h2>Ambiguous cells</h2><p>{ambiguous_html}</p><h2>Cell predictions</h2>{"".join(cell_html(cell) for cell in cells)}</body></html>"""


def create_report(
    image_path, output_dir, top_k, model, *, legacy_upload_normalization=False, device="cpu"
):
    image_processing = configure_runtime(device)["image_processing"]
    image = load_input_image(image_path, legacy_upload_normalization=legacy_upload_normalization)
    if image is None:
        raise ValueError("Image is corrupt or cannot be decoded by OpenCV")
    original_image = image.copy()
    output_dir.mkdir(parents=True, exist_ok=True)
    cells_dir = output_dir / "cells"
    cells_dir.mkdir(exist_ok=True)
    board, crop_details = image_processing.crop_board_image(image, debug=True)
    if board.size == 0:
        raise ValueError("Production fallback crop is outside this image")
    board_before_preprocessing = board.copy()
    recognition = image_processing.recognize_board_cells(
        board_before_preprocessing.copy(), model, capture_debug=True
    )
    save_bgr(output_dir / "01_original.png", original_image)
    save_bgr(
        output_dir / "02_smart_crop_overlay.png", smart_crop_overlay(original_image, crop_details)
    )
    save_bgr(output_dir / "03_board_crop.png", board_before_preprocessing)
    save_bgr(
        output_dir / "04_grid_overlay.png",
        grid_overlay(board_before_preprocessing, recognition["coordinates"]),
    )
    save_bgr(
        output_dir / "05_multiplier_overlay.png",
        multiplier_overlay(
            board_before_preprocessing,
            recognition["coordinates"],
            recognition["multipliers"],
        ),
    )
    records = []
    for row, col, *_rest in recognition["coordinates"]:
        label = label_for(row, col)
        raw_name, model_name = (
            f"cells/r{row + 1}c{col + 1}_raw.png",
            f"cells/r{row + 1}c{col + 1}_model.png",
        )
        save_bgr(output_dir / raw_name, recognition["raw_cells"][(row, col)])
        save_bgr(output_dir / model_name, tensor_to_png(recognition["model_inputs"][(row, col)]))
        probabilities = recognition["predictions"][(row, col)]
        top = ranked_predictions(probabilities, top_k)
        top_two = ranked_predictions(probabilities, 2)
        records.append(
            {
                "row": row + 1,
                "col": col + 1,
                "label": label,
                "predicted_class_index": top[0]["class_index"],
                "predicted_letter": top[0]["letter"],
                "predicted_probability": top[0]["probability"],
                "top_k": top,
                "second_prediction": top_two[1]["letter"],
                "second_probability": top_two[1]["probability"],
                "top1_top2_margin": float(top_two[0]["probability"] - top_two[1]["probability"]),
                "multiplier": recognition["multipliers"].get((row, col)),
                "raw_image": raw_name,
                "model_image": model_name,
            }
        )
    recognized = [
        [records[row * GRID_SIZE + col]["predicted_letter"] for col in range(GRID_SIZE)]
        for row in range(GRID_SIZE)
    ]
    bbox = crop_details.get("bbox") or crop_details.get("fallback_bbox")
    data = {
        "metadata": {
            "source_image_path": str(image_path.resolve()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "model_path": os.getenv("MODEL_PATH", image_processing.default_model_path()),
            "smart_crop_enabled": crop_details["smart_crop_enabled"],
            "input_dimensions": list(image.shape[:2][::-1]),
            "upload_normalization": (
                "legacy_590x1280_jpeg95" if legacy_upload_normalization else "native"
            ),
            "board_crop_dimensions": list(board.shape[:2][::-1]),
            "model_input_shape": list(recognition["model_inputs"][(0, 0)].shape),
            "top_k": top_k,
            **runtime_metadata(device),
        },
        "smart_crop": {
            "smart_crop_used": crop_details["smart_crop_used"],
            "fallback_reason": crop_details.get("fallback_reason"),
            "bbox": [bbox.x0, bbox.y0, bbox.x1, bbox.y1] if bbox else None,
            "info": crop_details.get("info", {}),
        },
        "board": {
            "rows": GRID_SIZE,
            "cols": GRID_SIZE,
            "recognized": recognized,
            "plain_text": "\n".join("".join(row) for row in recognized),
        },
        "cells": records,
    }
    contact_sheet(records, "raw_image", output_dir).save(output_dir / "06_contact_sheet_raw.png")
    contact_sheet(records, "model_image", output_dir).save(
        output_dir / "07_contact_sheet_model_input.png"
    )
    (output_dir / "predictions.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_csv(output_dir / "predictions.csv", records)
    (output_dir / "report.html").write_text(report_html(data), encoding="utf-8")
    return data


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("debug-board-recognition"))
    parser.add_argument("--top-k", type=validate_top_k, default=5)
    parser.add_argument("--device", choices=("cpu", "auto"), default="cpu")
    parser.add_argument(
        "--legacy-upload-normalization",
        action="store_true",
        help="reproduce retired RGB -> 590x1280 LANCZOS -> JPEG quality=95 upload processing",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not args.image.is_file():
        raise SystemExit(f"error: image does not exist: {args.image}")
    if args.image.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise SystemExit("error: unsupported image extension; use png, jpg, jpeg, or webp")
    runtime = configure_runtime(args.device)
    model_path = os.getenv("MODEL_PATH", runtime["image_processing"].default_model_path())
    try:
        model = runtime["load_letter_model"](model_path)
    except Exception as exc:
        raise SystemExit(f"error: model load failed ({model_path}): {exc}") from exc
    try:
        create_report(
            args.image,
            args.output_dir,
            args.top_k,
            model,
            legacy_upload_normalization=args.legacy_upload_normalization,
            device=args.device,
        )
    except (ValueError, OSError, cv2.error) as exc:
        raise SystemExit(f"error: {exc}") from exc
    print(f"Report created: {args.output_dir / 'report.html'}")


if __name__ == "__main__":
    main()
