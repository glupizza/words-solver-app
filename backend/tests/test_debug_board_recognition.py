import csv
import json

import cv2
import numpy as np
import pytest

from backend.tools import debug_board_recognition as debug
from backend.words_solver.image_processing import grid_coordinates


def test_ranked_predictions_sort_and_margin():
    ranked = debug.ranked_predictions(np.array([0.1, 0.7, 0.2]), 3)

    assert [item["class_index"] for item in ranked] == [1, 2, 0]
    assert ranked[0]["probability"] - ranked[1]["probability"] == pytest.approx(0.5)


def test_fixed_grid_labels_and_cell_count():
    board = np.zeros((50, 100, 3), dtype=np.uint8)
    coordinates = [(row, col) for row, col, *_ in grid_coordinates(board)]

    assert len(coordinates) == 25
    assert coordinates[0] == (0, 0)
    assert coordinates[-1] == (4, 4)
    assert debug.label_for(4, 4) == "R5C5"


def test_top_k_validation():
    assert debug.validate_top_k("1") == 1
    assert debug.validate_top_k("10") == 10
    with pytest.raises(Exception):
        debug.validate_top_k("0")
    with pytest.raises(Exception):
        debug.validate_top_k("11")


def test_device_arguments_default_to_cpu_and_allow_auto():
    assert debug.parse_args(["--image", "board.png"]).device == "cpu"
    assert debug.parse_args(["--image", "board.png", "--device", "auto"]).device == "auto"
    with pytest.raises(SystemExit):
        debug.parse_args(["--image", "board.png", "--device", "metal"])


def test_debug_input_normalization_default_is_native_and_legacy_is_fixed_size(tmp_path):
    source = tmp_path / "source.png"
    assert cv2.imwrite(str(source), np.zeros((2796, 1290, 3), dtype=np.uint8))

    native = debug.load_input_image(source)
    legacy = debug.load_input_image(source, legacy_upload_normalization=True)

    assert native.shape[:2] == (2796, 1290)
    assert legacy.shape[:2] == (1280, 590)


def test_json_csv_and_html_serialization(tmp_path):
    top = [
        {"class_index": 0, "letter": "а", "probability": 0.9},
        {"class_index": 1, "letter": "б", "probability": 0.1},
    ]
    cells = [
        {
            "row": 1,
            "col": 1,
            "label": "R1C1",
            "predicted_letter": "а",
            "predicted_probability": 0.9,
            "top1_top2_margin": 0.8,
            "multiplier": None,
            "top_k": top,
            "raw_image": "cells/r1c1_raw.png",
            "model_image": "cells/r1c1_model.png",
        }
    ]
    csv_path = tmp_path / "predictions.csv"
    debug.write_csv(csv_path, cells)
    assert next(csv.DictReader(csv_path.open(encoding="utf-8")))["top_k"] == "а:0.900000|б:0.100000"
    data = {
        "metadata": {"top_k": 2},
        "smart_crop": {
            "smart_crop_used": False,
            "fallback_reason": "smart_crop_disabled",
            "bbox": [37, 445, 552, 975],
            "info": {},
        },
        "board": {"recognized": [["а"] * 5] * 5, "plain_text": "а"},
        "cells": cells,
    }
    json_path = tmp_path / "predictions.json"
    json_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert json.loads(json_path.read_text(encoding="utf-8"))["cells"][0]["label"] == "R1C1"
    output = tmp_path / "report.html"
    output.write_text(debug.report_html(data), encoding="utf-8")
    assert "Recognized board" in output.read_text(encoding="utf-8")
    assert "Smart crop result" in output.read_text(encoding="utf-8")


def test_report_generation_with_synthetic_image_and_model(tmp_path, monkeypatch):
    class FakeModel:
        def predict(self, batch):
            result = np.zeros((len(batch), 36), dtype=np.float32)
            result[:, 0] = 0.8
            result[:, 1] = 0.2
            return result

    monkeypatch.setenv("SMART_CROP", "0")
    source = tmp_path / "synthetic.png"
    assert cv2.imwrite(str(source), np.zeros((1000, 600, 3), dtype=np.uint8))
    output = tmp_path / "output"
    data = debug.create_report(source, output, 2, FakeModel())

    assert len(data["cells"]) == 25
    assert (output / "report.html").is_file()
    assert (output / "predictions.json").is_file()
    assert len(list((output / "cells").glob("*.png"))) == 50
    assert data["metadata"]["device_requested"] == "cpu"
    for key in [
        "tensorflow_version",
        "keras_version",
        "opencv_version",
        "numpy_version",
        "python_version",
        "visible_gpu_count",
    ]:
        assert key in data["metadata"]


def test_report_original_artifact_is_pristine_when_recognition_mutates_board(tmp_path, monkeypatch):
    class FakeModel:
        def predict(self, batch):
            result = np.zeros((len(batch), 36), dtype=np.float32)
            result[:, 0] = 1.0
            return result

    image_processing = debug.configure_runtime("cpu")["image_processing"]
    original_recognize = image_processing.recognize_board_cells
    mutated = False

    def mutating_recognize(board, model, *, capture_debug):
        nonlocal mutated
        board[:] = 255
        mutated = True
        return original_recognize(board, model, capture_debug=capture_debug)

    monkeypatch.setenv("SMART_CROP", "0")
    monkeypatch.setattr(image_processing, "recognize_board_cells", mutating_recognize)
    source = tmp_path / "pattern.png"
    pattern = np.full((1000, 600, 3), (17, 43, 91), dtype=np.uint8)
    assert cv2.imwrite(str(source), pattern)
    output = tmp_path / "output"
    debug.create_report(source, output, 2, FakeModel())

    assert mutated
    assert np.array_equal(cv2.imread(str(output / "01_original.png")), pattern)
