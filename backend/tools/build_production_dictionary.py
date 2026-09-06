"""Build a conservative production-candidate dictionary from research accepted.csv.

This offline tool never writes the application's production dictionary.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

REQUIRED_COLUMNS = {
    "word",
    "length",
    "sources",
    "kinds",
    "flags",
    "reasons",
    "source_forms",
    "evidence",
    "confidence_tier",
    "confidence_reasons",
}
INCLUDED_TIERS = {"A_DUAL_EXTERNAL", "B_LEGACY_CONFIRMED", "C_OC_LONG_PARTICIPLE"}
FAMILY_SUFFIXES = ["ировать", "ироваться", "ирование", "ированный", "ованный", "ывание", "ивание"]
CYRILLIC_PROPER = r"[А-ЯЁ][А-ЯЁа-яё]*(?:[-\s]+[А-ЯЁа-яё][А-ЯЁа-яё]*)*"
RELATION_RISK = re.compile(
    rf"(?:имеющ\w*\s+отношение\s+к|относящ\w*|связанн\w*|соотносящ\w*|принадлежащ\w*|потомок|происходящ\w*|фамили\w*|жител\w*|урожен\w*)[^.;]{{0,80}}{CYRILLIC_PROPER}"
)
HOLDOUT_PATTERNS = (
    ("possible_proper_relation", RELATION_RISK),
    (
        "missed_diminutive_wording",
        re.compile(
            r"уменьшительное\s+(?:для|к)|уменьшительно-ласкательн\w*\s+форма", re.IGNORECASE
        ),
    ),
    ("pejorative_form", re.compile(r"уничижительная\s+форма", re.IGNORECASE)),
    (
        "explicit_jargon_definition",
        re.compile(r"(?:^|;gloss=)\s*лагерн\w*\s+жаргон\b", re.IGNORECASE),
    ),
    ("explicit_vernacular_label", re.compile(r"(?:^|[\s,;:(.\-])простореч\.")),
)
DEFAULT_MANUAL_HOLDOUT = Path(__file__).with_name("dictionary_production_holdout.txt")
MANUAL_WORD = re.compile(r"^[а-яё]{2,25}$")


def holdout_reason(evidence: str) -> str | None:
    """Return the first conservative audit risk found in compact evidence."""
    for reason, pattern in HOLDOUT_PATTERNS:
        if pattern.search(evidence):
            return reason
    return None


def load_manual_holdout(path: Path) -> set[str]:
    """Load a deliberately explicit policy list without silently normalizing it."""
    words: set[str] = set()
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        word = raw_line.strip()
        if not word or word.startswith("#"):
            continue
        if not MANUAL_WORD.fullmatch(word):
            raise ValueError(f"invalid manual holdout word at line {line_number}: {word!r}")
        if word in words:
            raise ValueError(f"duplicate manual holdout word at line {line_number}: {word}")
        words.add(word)
    return words


def _write_csv(path: Path, fields: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build(
    accepted_csv: Path, output_dir: Path, manual_holdout: Path | None = None
) -> dict[str, object]:
    manual_words = load_manual_holdout(manual_holdout or DEFAULT_MANUAL_HOLDOUT)
    with accepted_csv.open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        actual_fields = set(reader.fieldnames or [])
        missing = sorted(REQUIRED_COLUMNS - actual_fields)
        if missing:
            raise ValueError("accepted.csv is missing required columns: " + ", ".join(missing))
        fields = reader.fieldnames or []
        rows = list(reader)

    output_dir.mkdir(parents=True, exist_ok=True)
    included_rows: list[dict[str, str]] = []
    review_rows: list[dict[str, str]] = []
    tiers = Counter(row["confidence_tier"] for row in rows)
    reasons: Counter[str] = Counter()
    excluded_d = 0
    manual_matched: set[str] = set()
    for row in rows:
        if row["confidence_tier"] not in INCLUDED_TIERS:
            if row["confidence_tier"] == "D_SINGLE_SOURCE":
                excluded_d += 1
            continue
        reason = holdout_reason(row["evidence"])
        if row["word"] in manual_words:
            manual_matched.add(row["word"])
        if reason is None and row["word"] in manual_words:
            reason = "manual_proper_derived"
        if reason:
            reasons[reason] += 1
            review_rows.append(
                {**row, "production_status": "HOLDOUT", "production_review_reason": reason}
            )
        else:
            included_rows.append({**row, "production_status": "INCLUDE"})

    included_rows.sort(key=lambda row: row["word"])
    review_rows.sort(key=lambda row: (row["word"], row["production_review_reason"]))
    words = sorted({row["word"] for row in included_rows})
    (output_dir / "production_candidate.json").write_text(
        json.dumps(words, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    _write_csv(
        output_dir / "production_candidate.csv", fields + ["production_status"], included_rows
    )
    _write_csv(
        output_dir / "production_review.csv",
        fields + ["production_status", "production_review_reason"],
        review_rows,
    )
    summary = {
        "base_selected": sum(row["confidence_tier"] in INCLUDED_TIERS for row in rows),
        "included": len(words),
        "held_out": len(review_rows),
        "excluded_d_single_source": excluded_d,
        "manual_holdout_words_loaded": len(manual_words),
        "manual_holdout_words_matched": len(manual_matched),
        "counts_by_confidence_tier": dict(sorted(tiers.items())),
        "holdout_reason_counts": dict(sorted(reasons.items())),
        "length_counts": {
            str(limit): sum(len(word) >= limit for word in words) for limit in (10, 12, 15, 18, 20)
        },
        "suffix_counts": {
            suffix: sum(word.endswith(suffix) for word in words) for suffix in FAMILY_SUFFIXES
        },
    }
    (output_dir / "production_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--accepted-csv", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--manual-holdout", type=Path, default=DEFAULT_MANUAL_HOLDOUT)
    args = parser.parse_args()
    summary = build(args.accepted_csv, args.output_dir, args.manual_holdout)
    print(json.dumps({key: summary[key] for key in ("included", "held_out")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
