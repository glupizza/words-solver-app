import logging
import os
import time

import cv2
import numpy as np
from keras.utils import img_to_array

from .smart_crop import BBox, find_board_bbox
from .word_search import find_words

try:
    from .logging_config import request_id_var
except Exception:  # pragma: no cover
    request_id_var = None

logger = logging.getLogger(__name__)


def _log_stage(stage, start):
    logger.info("timing stage=%s seconds=%.3f", stage, time.perf_counter() - start)


def manual_crop(image, x_start, y_start, x_end, y_end):
    return image[y_start:y_end, x_start:x_end]


def avg_hsv(region):
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    return np.mean(hsv, axis=(0, 1))


def is_color_in_range(color, color_range):
    if not (
        isinstance(color_range, tuple)
        and len(color_range) == 2
        and all(isinstance(r, list) and len(r) == 3 for r in color_range)
    ):
        raise ValueError("color_range must be a tuple of two lists of length 3")

    lower_bounds, upper_bounds = color_range

    return all(
        lower <= channel <= upper
        for channel, lower, upper in zip(color, lower_bounds, upper_bounds)
    )


def color_fraction(region, color_range):
    if region.size == 0:
        return 0.0
    if not (
        isinstance(color_range, tuple)
        and len(color_range) == 2
        and all(isinstance(r, list) and len(r) == 3 for r in color_range)
    ):
        raise ValueError("color_range must be a tuple of two lists of length 3")

    lower_bounds, upper_bounds = color_range
    hsv = cv2.cvtColor(region, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(
        hsv,
        np.asarray(lower_bounds, dtype=np.uint8),
        np.asarray(upper_bounds, dtype=np.uint8),
    )
    return cv2.countNonZero(mask) / mask.size


# HSV ranges for multipliers
ORANGE_RANGE = ([0, 50, 150], [30, 255, 255])  # x2, c2
PURPLE_RANGE = ([100, 50, 150], [137, 255, 255])  # x3, c3
RED_RANGE = ([35, 80, 220], [70, 130, 250])  # red corner masking
MULTIPLIER_COLOR_MIN_FRACTION = float(os.getenv("MULTIPLIER_COLOR_MIN_FRACTION", "0.20"))


CLASS_LABELS = {
    0: "A",
    1: "B",
    2: "Ch",
    3: "D",
    4: "E",
    5: "E**",
    6: "F",
    7: "G",
    8: "H",
    9: "I",
    10: "J",
    11: "K",
    12: "L",
    13: "M",
    14: "N",
    15: "O",
    16: "P",
    17: "R",
    18: "S",
    19: "Sch",
    20: "Sh",
    21: "T",
    22: "Ts",
    23: "U",
    24: "V",
    25: "Y",
    26: "Ya",
    27: "Yu",
    28: "Z",
    29: "Zh",
    30: "c2",
    31: "c3",
    32: "hard",
    33: "soft",
    34: "x2",
    35: "x3",
}


# Keep payload letters in Cyrillic (represented as unicode escapes to keep source ASCII-only)
TRANSLIT_TO_RUS = {
    "A": "\u0430",  # а
    "B": "\u0431",  # б
    "Ch": "\u0447",  # ч
    "D": "\u0434",  # д
    "E": "\u0435",  # е
    "E**": "\u044d",  # э
    "F": "\u0444",  # ф
    "G": "\u0433",  # г
    "H": "\u0445",  # х
    "I": "\u0438",  # и
    "J": "\u0439",  # й
    "K": "\u043a",  # к
    "L": "\u043b",  # л
    "M": "\u043c",  # м
    "N": "\u043d",  # н
    "O": "\u043e",  # о
    "P": "\u043f",  # п
    "R": "\u0440",  # р
    "S": "\u0441",  # с
    "Sch": "\u0449",  # щ
    "Sh": "\u0448",  # ш
    "T": "\u0442",  # т
    "Ts": "\u0446",  # ц
    "U": "\u0443",  # у
    "V": "\u0432",  # в
    "Y": "\u044b",  # ы
    "Ya": "\u044f",  # я
    "Yu": "\u044e",  # ю
    "Z": "\u0437",  # з
    "Zh": "\u0436",  # ж
    "hard": "\u044a",  # ъ
    "soft": "\u044c",  # ь
    # these should never form words, but keep them consistent
    "c2": "\u04412",  # с2
    "c3": "\u04413",  # с3
    "x2": "\u04452",  # х2
    "x3": "\u04453",  # х3
}

GRID_SIZE = 5
FALLBACK_CROP = (37, 445, 552, 975)
FALLBACK_REFERENCE_WIDTH = 590
FALLBACK_REFERENCE_HEIGHT = 1280


def default_model_path():
    """Return the model asset used when MODEL_PATH is not configured."""
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "assets",
        "letter_recognition_model.h5",
    )


def fallback_crop_bbox(image):
    """Scale the historical 590x1280 fallback crop to the input image."""
    height, width = image.shape[:2]
    x0, y0, x1, y1 = FALLBACK_CROP
    bbox = BBox(
        int(round(x0 * width / FALLBACK_REFERENCE_WIDTH)),
        int(round(y0 * height / FALLBACK_REFERENCE_HEIGHT)),
        int(round(x1 * width / FALLBACK_REFERENCE_WIDTH)),
        int(round(y1 * height / FALLBACK_REFERENCE_HEIGHT)),
    )
    return bbox.clamp(width, height)


def crop_board_image(image, *, debug=False):
    """Run the production crop selection and return its actual intermediate data."""
    use_smart = os.getenv("SMART_CROP", "1") not in {"0", "false", "False"}
    details = {"smart_crop_enabled": use_smart, "smart_crop_used": False}
    if use_smart:
        bbox, info, mask, candidates, cluster = find_board_bbox(
            image,
            roi_top=float(os.getenv("SMART_CROP_ROI_TOP", "0.18")),
            roi_bottom=float(os.getenv("SMART_CROP_ROI_BOTTOM", "0.92")),
            s_max=int(os.getenv("SMART_CROP_S_MAX", "60")),
            v_min=int(os.getenv("SMART_CROP_V_MIN", "200")),
            min_tiles=int(os.getenv("SMART_CROP_MIN_TILES", "15")),
            pad_frac=float(os.getenv("SMART_CROP_PAD_FRAC", "0.02")),
            debug=debug,
        )
        details.update(
            {"info": info, "bbox": bbox, "mask": mask, "candidates": candidates, "cluster": cluster}
        )
        if bbox is not None:
            details["smart_crop_used"] = True
            return image[bbox.y0 : bbox.y1, bbox.x0 : bbox.x1], details
        details["fallback_reason"] = "smart_crop_no_board_found"
    else:
        details["fallback_reason"] = "smart_crop_disabled"
    fallback_bbox = fallback_crop_bbox(image)
    details["fallback_bbox"] = fallback_bbox
    return image[fallback_bbox.y0 : fallback_bbox.y1, fallback_bbox.x0 : fallback_bbox.x1], details


def grid_coordinates(board_image):
    """Return the exact fixed 5x5 production splitter coordinates."""
    height, width = board_image.shape[:2]
    cell_height, cell_width = height // GRID_SIZE, width // GRID_SIZE
    return [
        (
            row,
            col,
            col * cell_width,
            row * cell_height,
            (col + 1) * cell_width,
            (row + 1) * cell_height,
        )
        for row in range(GRID_SIZE)
        for col in range(GRID_SIZE)
    ]


def _detect_multiplier(top_left_region, bottom_left_region):
    if color_fraction(top_left_region, ORANGE_RANGE) >= MULTIPLIER_COLOR_MIN_FRACTION:
        return "x2"
    if color_fraction(top_left_region, PURPLE_RANGE) >= MULTIPLIER_COLOR_MIN_FRACTION:
        return "x3"
    if color_fraction(bottom_left_region, ORANGE_RANGE) >= MULTIPLIER_COLOR_MIN_FRACTION:
        return "c2"
    if color_fraction(bottom_left_region, PURPLE_RANGE) >= MULTIPLIER_COLOR_MIN_FRACTION:
        return "c3"
    return None


def recognize_board_cells(cropped_image, model, *, capture_debug=False):
    """Execute the production split/preprocess/predict stages, excluding word search.

    This intentionally preserves the original in-place cell masking and multiplier
    re-prediction order.  ``capture_debug`` only retains copies of intermediates.
    """
    coordinates = grid_coordinates(cropped_image)
    cell_height = cropped_image.shape[0] // GRID_SIZE
    cell_width = cropped_image.shape[1] // GRID_SIZE
    cells_batch, mapping, raw_cells, model_inputs = [], [], {}, {}
    detected_multipliers = {}

    for row, col, x0, y0, x1, y1 in coordinates:
        cell = cropped_image[y0:y1, x0:x1]
        if capture_debug:
            raw_cells[(row, col)] = cell.copy()
        shift_x, shift_y = int(cell_width * 0.15), int(cell_height * 0.15)
        corner_size = int(cell_width * 0.2)
        bottom_right_region = cell[
            -corner_size - shift_y : -shift_y, -corner_size - shift_x : -shift_x
        ]
        if is_color_in_range(avg_hsv(bottom_right_region), RED_RANGE):
            square_size = int(cell_width * 0.27)
            cv2.rectangle(
                cell,
                (cell_width - square_size, cell_height - square_size),
                (cell_width, cell_height),
                (255, 255, 255),
                -1,
            )

        top_left_region = cell[shift_y : shift_y + corner_size, shift_x : shift_x + corner_size]
        bottom_left_region = cell[
            -corner_size - shift_y : -shift_y, shift_x : shift_x + corner_size
        ]
        multiplier = _detect_multiplier(top_left_region, bottom_left_region)
        if multiplier:
            detected_multipliers[(row, col)] = multiplier
            large_corner = int(cell_width * 0.58)
            pts = (
                np.array([[0, 0], [large_corner, 0], [0, large_corner]], np.int32)
                if multiplier in ["x2", "x3"]
                else np.array(
                    [
                        [0, cell_height],
                        [large_corner, cell_height],
                        [0, cell_height - large_corner],
                    ],
                    np.int32,
                )
            )
            cv2.fillPoly(cell, [pts], (255, 255, 255))
        tensor = np.expand_dims(img_to_array(cv2.resize(cell, (64, 64))) / 255.0, axis=0)
        cells_batch.append(tensor)
        mapping.append((row, col, multiplier))
        model_inputs[(row, col)] = tensor

    predictions = model.predict(np.vstack(cells_batch))
    final_predictions = {(row, col): predictions[i] for i, (row, col, _) in enumerate(mapping)}
    update_cells, update_mapping = [], []
    for row, col in detected_multipliers:
        x0, y0, x1, y1 = (
            col * cell_width,
            row * cell_height,
            (col + 1) * cell_width,
            (row + 1) * cell_height,
        )
        tensor = np.expand_dims(
            img_to_array(cv2.resize(cropped_image[y0:y1, x0:x1], (64, 64))) / 255.0, axis=0
        )
        update_cells.append(tensor)
        update_mapping.append((row, col))
        model_inputs[(row, col)] = tensor
    if update_cells:
        update_predictions = model.predict(np.vstack(update_cells))
        final_predictions.update(
            {position: update_predictions[i] for i, position in enumerate(update_mapping)}
        )

    board = [[(None, None) for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
    for row, col, multiplier in mapping:
        board[row][col] = (CLASS_LABELS[int(np.argmax(final_predictions[(row, col)]))], multiplier)
    return {
        "board": board,
        "coordinates": coordinates,
        "raw_cells": raw_cells,
        "model_inputs": model_inputs,
        "predictions": final_predictions,
        "multipliers": detected_multipliers,
    }


def process_image(image_path, model, trie):
    overall_start = time.perf_counter()

    # Read image
    t0 = time.perf_counter()
    image = cv2.imread(image_path)
    if image is None:
        logger.warning("failed to read image image_path=%s", image_path)
        return {"error": "Failed to read the image"}
    _log_stage("read_image", t0)

    # Crop
    t0 = time.perf_counter()
    debug_dir = os.getenv("SMART_CROP_DEBUG_DIR")
    cropped_image, crop_details = crop_board_image(image, debug=bool(debug_dir))
    info = crop_details.get("info", {})
    bbox = crop_details.get("bbox")
    if crop_details["smart_crop_used"]:
        logger.info(
            "smart_crop ok bbox=(%d,%d)-(%d,%d) tiles=%d candidates=%d",
            bbox.x0,
            bbox.y0,
            bbox.x1,
            bbox.y1,
            int(info.get("cluster", 0.0)),
            int(info.get("candidates", 0.0)),
        )
        if debug_dir:
            os.makedirs(debug_dir, exist_ok=True)
            rid = request_id_var.get() if request_id_var is not None else None
            tag = f"{int(time.time() * 1000)}_{rid or '-'}"
            overlay = image.copy()
            for rect in crop_details["candidates"]:
                cv2.rectangle(overlay, (rect.x0, rect.y0), (rect.x1, rect.y1), (0, 0, 255), 1)
            for rect in crop_details["cluster"]:
                cv2.rectangle(overlay, (rect.x0, rect.y0), (rect.x1, rect.y1), (0, 255, 0), 2)
            cv2.rectangle(overlay, (bbox.x0, bbox.y0), (bbox.x1, bbox.y1), (255, 0, 0), 3)
            cv2.imwrite(os.path.join(debug_dir, f"{tag}_norm.png"), image)
            if crop_details["mask"] is not None:
                cv2.imwrite(os.path.join(debug_dir, f"{tag}_mask.png"), crop_details["mask"])
            cv2.imwrite(os.path.join(debug_dir, f"{tag}_overlay.png"), overlay)
            cv2.imwrite(os.path.join(debug_dir, f"{tag}_crop.png"), cropped_image)
    elif crop_details["smart_crop_enabled"]:
        logger.info(
            "smart_crop miss tiles=%d candidates=%d",
            int(info.get("cluster", 0.0)),
            int(info.get("candidates", 0.0)),
        )

    _log_stage("crop_image", t0)

    # Keep recognition mechanics shared with the local diagnostic tool.  The
    # helper preserves the historical two-pass multiplier behaviour exactly.
    t0 = time.perf_counter()
    recognition = recognize_board_cells(cropped_image, model)
    _log_stage("recognize_cells", t0)

    t0 = time.perf_counter()
    board_rus = [
        [(TRANSLIT_TO_RUS.get(letter, letter), multiplier) for letter, multiplier in row]
        for row in recognition["board"]
    ]
    _log_stage("build_board_rus", t0)

    t0 = time.perf_counter()
    found_words = find_words(board_rus, trie=trie, grid_size=GRID_SIZE)
    _log_stage("find_words", t0)
    sorted_words = sorted(found_words.items(), key=lambda x: x[1], reverse=True)
    logger.info("timing stage=total seconds=%.3f", time.perf_counter() - overall_start)
    return {"words": [{"name": word, "score": score} for word, score in sorted_words]}
