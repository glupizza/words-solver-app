import cv2
import numpy as np

from backend.words_solver.image_processing import (
    MULTIPLIER_COLOR_MIN_FRACTION,
    ORANGE_RANGE,
    PURPLE_RANGE,
    _detect_multiplier,
    color_fraction,
)


def _bgr_from_hsv(hsv):
    return cv2.cvtColor(np.asarray([[hsv]], dtype=np.uint8), cv2.COLOR_HSV2BGR)[0, 0]


def _region(hsv, shape=(10, 10)):
    return np.full((*shape, 3), _bgr_from_hsv(hsv), dtype=np.uint8)


PURPLE_PIXEL = [134, 192, 253]
ORANGE_PIXEL = [15, 192, 253]


def test_color_fraction_recognizes_purple_region():
    assert color_fraction(_region(PURPLE_PIXEL), PURPLE_RANGE) == 1.0


def test_color_fraction_recognizes_orange_region():
    assert color_fraction(_region(ORANGE_PIXEL), ORANGE_RANGE) == 1.0


def test_color_fraction_rejects_white_background_and_empty_region():
    assert color_fraction(np.full((10, 10, 3), 255, dtype=np.uint8), PURPLE_RANGE) == 0.0
    assert color_fraction(np.empty((0, 0, 3), dtype=np.uint8), ORANGE_RANGE) == 0.0


def test_color_fraction_obeys_multiplier_threshold():
    region = np.full((10, 10, 3), 255, dtype=np.uint8)
    region.reshape(-1, 3)[:19] = _bgr_from_hsv(PURPLE_PIXEL)
    assert color_fraction(region, PURPLE_RANGE) < MULTIPLIER_COLOR_MIN_FRACTION

    region.reshape(-1, 3)[19] = _bgr_from_hsv(PURPLE_PIXEL)
    assert color_fraction(region, PURPLE_RANGE) >= MULTIPLIER_COLOR_MIN_FRACTION


def test_multiplier_corner_semantics():
    white = _region([0, 0, 255])

    assert _detect_multiplier(_region(ORANGE_PIXEL), white) == "x2"
    assert _detect_multiplier(_region(PURPLE_PIXEL), white) == "x3"
    assert _detect_multiplier(white, _region(ORANGE_PIXEL)) == "c2"
    assert _detect_multiplier(white, _region(PURPLE_PIXEL)) == "c3"


def test_multiplier_detection_obeys_fraction_threshold():
    white = _region([0, 0, 255])

    below = white.copy()
    below.reshape(-1, 3)[:19] = _bgr_from_hsv(PURPLE_PIXEL)

    at_threshold = white.copy()
    at_threshold.reshape(-1, 3)[:20] = _bgr_from_hsv(PURPLE_PIXEL)

    assert _detect_multiplier(below, white) is None
    assert _detect_multiplier(at_threshold, white) == "x3"
