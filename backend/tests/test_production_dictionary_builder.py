import csv
import json

import pytest

import backend.tools.build_production_dictionary as production_builder
from backend.tools.build_production_dictionary import REQUIRED_COLUMNS, build, load_manual_holdout


def _write_accepted(path, rows, fields=None):
    fields = fields or sorted(REQUIRED_COLUMNS)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _row(word, tier, evidence=""):
    return {
        "word": word,
        "length": str(len(word)),
        "sources": "wiktionary",
        "kinds": "NOUN",
        "flags": "",
        "reasons": "",
        "source_forms": word,
        "evidence": evidence,
        "confidence_tier": tier,
        "confidence_reasons": tier,
    }


def test_selects_tiers_and_audits_holdouts(tmp_path) -> None:
    source = tmp_path / "accepted.csv"
    _write_accepted(
        source,
        [
            _row("альфа", "A_DUAL_EXTERNAL"),
            _row("бета", "B_LEGACY_CONFIRMED"),
            _row("гамма", "C_OC_LONG_PARTICIPLE"),
            _row("дельта", "D_SINGLE_SOURCE"),
            _row("абинский", "A_DUAL_EXTERNAL", "относящийся к Абинску"),
            _row("вентилек", "A_DUAL_EXTERNAL", "уменьшительное для вентиль"),
            _row("уничижитель", "A_DUAL_EXTERNAL", "уничижительная форма"),
            _row("ковыряльник", "A_DUAL_EXTERNAL", "лагерный жаргон оружия"),
            _row("просторечный", "A_DUAL_EXTERNAL", "простореч. слово"),
            _row("химия", "A_DUAL_EXTERNAL", "формула C7H7O4N"),
            _row("жаргон", "A_DUAL_EXTERNAL", "слово жаргон"),
        ],
    )
    summary = build(source, tmp_path / "report")
    words = json.loads(
        (tmp_path / "report" / "production_candidate.json").read_text(encoding="utf-8")
    )
    assert words == sorted(set(words))
    assert {"альфа", "бета", "гамма", "химия", "жаргон"} <= set(words)
    assert "дельта" not in words
    assert summary["held_out"] == 5
    assert summary["excluded_d_single_source"] == 1
    assert (
        "production_status"
        in (tmp_path / "report" / "production_candidate.csv")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    review = (tmp_path / "report" / "production_review.csv").read_text(encoding="utf-8")
    assert "possible_proper_relation" in review
    assert "missed_diminutive_wording" in review


def test_validates_required_columns(tmp_path) -> None:
    source = tmp_path / "bad.csv"
    _write_accepted(source, [], fields=["word", "confidence_tier"])
    with pytest.raises(ValueError, match="missing required columns"):
        build(source, tmp_path / "report")


def test_manual_holdout_policy_and_validation(tmp_path, monkeypatch) -> None:
    source = tmp_path / "accepted.csv"
    holdout = tmp_path / "holdout.txt"
    holdout.write_text("# comment\n\nавгиев\n", encoding="utf-8")
    _write_accepted(
        source,
        [
            _row("авгиев", "A_DUAL_EXTERNAL"),
            _row("чистый", "B_LEGACY_CONFIRMED"),
            _row("авгиев", "D_SINGLE_SOURCE"),
        ],
    )
    summary = build(source, tmp_path / "report", holdout)
    review = (tmp_path / "report" / "production_review.csv").read_text(encoding="utf-8")
    words = json.loads(
        (tmp_path / "report" / "production_candidate.json").read_text(encoding="utf-8")
    )
    assert "manual_proper_derived" in review
    assert "авгиев" not in words and "чистый" in words
    assert summary["manual_holdout_words_loaded"] == 1
    assert summary["manual_holdout_words_matched"] == 1
    default = tmp_path / "default.txt"
    default.write_text("чистый\n", encoding="utf-8")
    monkeypatch.setattr(production_builder, "DEFAULT_MANUAL_HOLDOUT", default)
    assert load_manual_holdout(production_builder.DEFAULT_MANUAL_HOLDOUT) == {"чистый"}
    default_summary = build(source, tmp_path / "default-report")
    assert default_summary["manual_holdout_words_matched"] == 1
    with pytest.raises(ValueError, match="duplicate"):
        (tmp_path / "duplicate.txt").write_text("слово\nслово\n", encoding="utf-8")
        load_manual_holdout(tmp_path / "duplicate.txt")
    with pytest.raises(ValueError, match="invalid"):
        (tmp_path / "invalid.txt").write_text("Слово\n", encoding="utf-8")
        load_manual_holdout(tmp_path / "invalid.txt")
