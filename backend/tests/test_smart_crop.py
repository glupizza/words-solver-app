import numpy as np
import pytest

from backend.words_solver import smart_crop
from backend.words_solver.smart_crop import Rect, bbox_from_grid_geometry


def make_grid_rects(*, jitter=None, missing=()):
    pitch_x, pitch_y = 106, 104
    tile_w, tile_h = 96, 92
    start_x, start_y = 100, 150
    jitter = jitter or {}
    missing = set(missing)
    rects = []
    for row in range(5):
        for col in range(5):
            if (row, col) in missing:
                continue
            dx, dy = jitter.get((row, col), (0, 0))
            cx = start_x + col * pitch_x + dx
            cy = start_y + row * pitch_y + dy
            rects.append(Rect(cx - tile_w // 2, cy - tile_h // 2, tile_w, tile_h))
    return rects


def test_grid_geometry_uses_center_pitch_not_tile_edges():
    result = bbox_from_grid_geometry(make_grid_rects(), img_w=1000, img_h=1000)

    assert result is not None
    bbox, pitch_x, pitch_y = result
    assert pitch_x == pytest.approx(106)
    assert pitch_y == pytest.approx(104)
    assert bbox == smart_crop.BBox(47, 98, 577, 618)
    assert bbox != smart_crop.bbox_from_rects(make_grid_rects())
    assert (bbox.x1 - bbox.x0) % 5 == 0
    assert (bbox.y1 - bbox.y0) % 5 == 0


def test_find_board_bbox_prefers_reconstructed_geometry(monkeypatch):
    rects = make_grid_rects()
    image = np.zeros((1000, 1000, 3), dtype=np.uint8)

    monkeypatch.setattr(smart_crop, "rects_from_mask", lambda _mask: rects)
    monkeypatch.setattr(smart_crop, "filter_tile_candidates", lambda *_args, **_kwargs: rects)

    bbox, info, _mask, _candidates, _cluster = smart_crop.find_board_bbox(image)

    assert info["geometry_used"] == 1.0
    assert info["pitch_x"] == pytest.approx(106)
    assert info["pitch_y"] == pytest.approx(104)
    assert bbox == smart_crop.BBox(47, 98, 577, 618)


def test_grid_geometry_tolerates_small_center_jitter():
    jitter = {
        (row, col): ((row * 2 + col) % 5 - 2, (row + col * 2) % 5 - 2)
        for row in range(5)
        for col in range(5)
    }

    result = bbox_from_grid_geometry(make_grid_rects(jitter=jitter), img_w=1000, img_h=1000)

    assert result is not None
    _bbox, pitch_x, pitch_y = result
    assert pitch_x == pytest.approx(106, abs=3)
    assert pitch_y == pytest.approx(104, abs=3)


def test_grid_geometry_keeps_integer_cell_slots_for_fractional_pitch():
    xs = [82.5, 189.5, 295.0, 401.5, 507.5]
    ys = [501.0, 607.5, 713.0, 819.0, 925.0]
    rects = []
    for cy in ys:
        for cx in xs:
            tile_w = 97 if cx % 1 else 96
            tile_h = 97 if cy % 1 else 96
            rects.append(
                Rect(
                    int(cx - tile_w / 2),
                    int(cy - tile_h / 2),
                    tile_w,
                    tile_h,
                )
            )

    result = bbox_from_grid_geometry(rects, img_w=590, img_h=1280)

    assert result is not None
    bbox, pitch_x, pitch_y = result
    assert pitch_x == pytest.approx(106.25)
    assert pitch_y == pytest.approx(106.0)
    assert bbox.x1 - bbox.x0 == 530
    assert bbox.y1 - bbox.y0 == 530
    assert (bbox.x1 - bbox.x0) // 5 == 106
    assert (bbox.y1 - bbox.y0) // 5 == 106

    cell_centers_x = [bbox.x0 + 53 + col * 106 for col in range(5)]
    cell_centers_y = [bbox.y0 + 53 + row * 106 for row in range(5)]
    assert max(abs(actual - expected) for actual, expected in zip(cell_centers_x, xs)) <= 2
    assert max(abs(actual - expected) for actual, expected in zip(cell_centers_y, ys)) <= 2


def test_grid_geometry_handles_missing_tiles_when_all_axes_remain():
    result = bbox_from_grid_geometry(
        make_grid_rects(missing={(0, 0), (1, 3), (2, 2), (3, 4), (4, 1), (4, 3)}),
        img_w=1000,
        img_h=1000,
    )

    assert result is not None
    bbox, _pitch_x, _pitch_y = result
    assert bbox == smart_crop.BBox(47, 98, 577, 618)


def test_find_board_bbox_falls_back_when_geometry_is_not_5x5(monkeypatch):
    # Five columns but only one row cannot represent the known 5x5 grid.
    rects = [Rect(52 + col * 106, 104, 96, 92) for col in range(5)]
    image = np.zeros((1000, 1000, 3), dtype=np.uint8)

    monkeypatch.setattr(smart_crop, "rects_from_mask", lambda _mask: rects)
    monkeypatch.setattr(smart_crop, "filter_tile_candidates", lambda *_args, **_kwargs: rects)

    bbox, info, _mask, _candidates, _cluster = smart_crop.find_board_bbox(image, min_tiles=5)

    assert bbox is not None
    assert info["geometry_used"] == 0.0
    assert bbox.x0 >= 0 and bbox.y0 >= 0
    assert bbox.x1 <= image.shape[1] and bbox.y1 <= image.shape[0]
    assert bbox.x1 > bbox.x0 and bbox.y1 > bbox.y0
    assert (bbox.x1 - bbox.x0) % 5 == 0
    assert (bbox.y1 - bbox.y0) % 5 == 0
