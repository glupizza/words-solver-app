# Dictionary candidate builder

`build_dictionary_candidates.py` is offline research tooling for the future
dictionary of «Слово за слово». It never changes the production dictionary or
application runtime.

Inputs are supplied explicitly. Download source dumps separately from their
official locations and do not commit the large dumps to git:

- OpenCorpora: <https://opencorpora.org/files/export/dict/dict.opcorpora.xml.bz2>
- Russian Wiktionary Wiktextract: <https://kaikki.org/ruwiktionary/raw-wiktextract-data.jsonl.gz>

Example:

```bash
python backend/tools/build_dictionary_candidates.py \
  --legacy backend/assets/cleaned_filtered_russian_words.json \
  --opencorpora /path/to/dict.opcorpora.xml.bz2 \
  --wiktionary /path/to/raw-wiktextract-data.jsonl.gz \
  --output-dir /tmp/worder-dictionary-report
```

The output directory contains research-only `accepted.json`, review/rejection
CSVs, long additions, and a diagnostic `summary.json`. Review results must be
curated before any separate future dictionary update.
