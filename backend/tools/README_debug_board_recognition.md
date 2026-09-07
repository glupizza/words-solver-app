# Board OCR diagnostic

Run the local recognition diagnostic without starting the web application:

```bash
python backend/tools/debug_board_recognition.py \
  --image /path/to/problem.jpg \
  --output-dir /path/to/debug-output \
  --top-k 5
```

It uses the same `MODEL_PATH`, `SMART_CROP`, and `SMART_CROP_*` settings as the
backend OCR pipeline.  The output directory contains `report.html`, JSON and CSV
predictions, crop/grid/multiplier overlays, and raw plus actual model-input images
for all 25 cells.  It only diagnoses recognition; it does not run word search.

CPU is the default, matching production Docker inference. For research using the
normal TensorFlow device selection, run:

```bash
python backend/tools/debug_board_recognition.py --image /path/to/problem.png \
  --output-dir /path/to/report --top-k 5 --device auto
```

The optional
`--legacy-upload-normalization` flag can be combined with either device mode to
reproduce the retired 590×1280 JPEG upload transformation.
