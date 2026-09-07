import numpy as np

from backend.words_solver.image_processing import crop_board_image, fallback_crop_bbox
from backend.words_solver.smart_crop import BBox


def test_fallback_bbox_keeps_historical_590x1280_coordinates():
    image = np.zeros((1280, 590, 3), dtype=np.uint8)

    assert fallback_crop_bbox(image) == BBox(37, 445, 552, 975)


def test_fallback_bbox_scales_to_native_resolution_inside_bounds():
    image = np.zeros((2796, 1290, 3), dtype=np.uint8)

    bbox = fallback_crop_bbox(image)

    assert bbox == BBox(81, 972, 1207, 2130)
    assert 0 <= bbox.x0 < bbox.x1 <= image.shape[1]
    assert 0 <= bbox.y0 < bbox.y1 <= image.shape[0]


def test_smart_crop_disabled_uses_scaled_fallback(monkeypatch):
    image = np.zeros((2796, 1290, 3), dtype=np.uint8)
    monkeypatch.setenv("SMART_CROP", "0")

    board, details = crop_board_image(image)

    assert details["smart_crop_used"] is False
    assert details["fallback_bbox"] == BBox(81, 972, 1207, 2130)
    assert board.shape[:2] == (1158, 1126)
