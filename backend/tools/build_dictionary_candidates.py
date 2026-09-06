"""Build an offline, evidence-bearing candidate dictionary for research.

This module intentionally has no connection to the application dictionary or runtime.
"""

from __future__ import annotations

import argparse
import bz2
import csv
import gzip
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

CYRILLIC_WORD = re.compile(r"^[а-я]+$")
ACUTE_MARKS = {"\u0301", "\u0300", "\u0341", "\u0340"}
CANONICAL_KINDS = {"NOUN", "INFN", "ADJF", "PRTF", "ADVB"}
DIAGNOSTIC_WORDS = [
    "обкатать",
    "обкатанный",
    "перекатать",
    "перекатанный",
    "программировать",
    "программирование",
    "программированный",
    "перепрограммировать",
    "перепрограммирование",
    "перепрограммированный",
]
FAMILY_SUFFIXES = ["ировать", "ироваться", "ирование", "ированный", "ованный", "ывание", "ивание"]
HARD_FLAGS = {
    "proper_name",
    "abbreviation",
    "slang",
    "vulgar",
    "foreign",
    "gerund",
    "diminutive_only",
}
CLASSIFICATION_REASONS = HARD_FLAGS | {
    "archaic",
    "colloquial",
    "diminutive_independent_sense",
    "diminutive_metadata_ambiguous",
    "legacy_only",
    "unsupported_or_unknown_form",
    "conflicting_source_metadata",
}


def normalize_word(value: str) -> str | None:
    """Return a game-compatible Russian word, or None when it is not one word."""
    value = unicodedata.normalize("NFD", value)
    # Do not remove every combining mark: in NFD, Cyrillic "й" is "и" plus
    # COMBINING BREVE. Only stress marks are irrelevant to the game spelling.
    value = "".join(char for char in value if char not in ACUTE_MARKS)
    value = unicodedata.normalize("NFC", value).lower().replace("ё", "е")
    if not CYRILLIC_WORD.fullmatch(value) or not 2 <= len(value) <= 25:
        return None
    return value


def cleaned_source_form(value: str) -> str:
    """Apply non-destructive display normalization used for rejected source forms."""
    value = unicodedata.normalize("NFD", value)
    value = "".join(char for char in value if char not in ACUTE_MARKS)
    return unicodedata.normalize("NFC", value).lower().replace("ё", "е")


def invalid_form_reason(value: str) -> str:
    plain = cleaned_source_form(value)
    if len(plain) < 2 or len(plain) > 25:
        return "outside_length_range"
    if "-" in plain:
        return "hyphenated"
    if any(char.isspace() for char in plain):
        return "multiword"
    return "punctuation_or_non_cyrillic"


def _tag_set(value: Any) -> set[str]:
    if not isinstance(value, list):
        return set()
    return {str(item).strip().lower() for item in value if isinstance(item, str)}


def _has(tags: set[str], *names: str) -> bool:
    return any(name in tags for name in names)


def _flags_from_metadata(tags: Iterable[str], text: str = "") -> set[str]:
    tag_set = {tag.lower() for tag in tags}
    joined = text.lower()
    patterns = {
        "proper_name": {
            "proper-noun",
            "proper noun",
            "name",
            "surname",
            "patronymic",
            "toponym",
        },
        "abbreviation": {"abbreviation", "abbr"},
        "slang": {"slang"},
        "colloquial": {"colloquial"},
        "vulgar": {"vulgar"},
        "archaic": {"archaic", "obsolete"},
        "diminutive": {"diminutive", "affectionate"},
        "gerund": {"gerund", "adverbial participle"},
        "plural_only": {"plural only", "plurale tantum", "pluralia tantum"},
        "foreign": {"non-russian", "foreign"},
    }
    text_patterns = {
        "proper_name": (
            "имена собственные",
            "собственные имена",
            "мужские имена",
            "женские имена",
            "фамилии",
            "отчества",
            "топонимы",
        ),
        "abbreviation": ("сокращ", "аббревиат"),
        "slang": ("жаргон",),
        "colloquial": ("разговор",),
        "vulgar": ("бран", "простореч"),
        "archaic": ("устар", "архаич"),
        "diminutive": ("уменьш", "ласкат"),
        "gerund": ("деепричаст",),
    }
    return {
        flag
        for flag in patterns
        if tag_set & patterns[flag]
        or any(needle in joined for needle in text_patterns.get(flag, ()))
    }


def is_form_of_entry(entry: dict[str, Any]) -> bool:
    """Whether every supplied sense marks this headword as an inflected form."""
    raw_senses = entry.get("senses")
    if not isinstance(raw_senses, list):
        return False
    senses = [sense for sense in raw_senses if isinstance(sense, dict)]
    if not senses:
        return False
    return all(
        bool(sense.get("form_of"))
        or "form-of" in (_tag_set(sense.get("tags")) | _tag_set(sense.get("raw_tags")))
        for sense in senses
    )


def _compact(values: Iterable[str], limit: int = 400) -> str:
    """Make evidence useful in CSV without allowing an entry to dominate a row."""
    result = ";".join(" ".join(value.split())[:120] for value in values if value.strip())
    return result[:limit]


def _oc_flags(tags: set[str]) -> set[str]:
    mapping = {
        "proper_name": {"name", "surn", "patr", "geox", "orgn"},
        "abbreviation": {"abbr"},
        "slang": {"slng"},
        "colloquial": {"infr"},
        "archaic": {"arch"},
        "plural_only": {"pltm"},
    }
    return {flag for flag, names in mapping.items() if tags & names}


@dataclass
class Candidate:
    word: str
    sources: set[str] = field(default_factory=set)
    kinds: set[str] = field(default_factory=set)
    flags: set[str] = field(default_factory=set)
    reasons: set[str] = field(default_factory=set)
    source_forms: set[str] = field(default_factory=set)
    evidence: list[str] = field(default_factory=list)
    clean_canonical_support: bool = False
    hard_disallowed_canonical_support: bool = False
    invalid: bool = False

    def row(self) -> dict[str, str | int]:
        return {
            "word": self.word,
            "length": len(self.word),
            "sources": ";".join(sorted(self.sources)),
            "kinds": ";".join(sorted(self.kinds)),
            "flags": ";".join(sorted(self.flags)),
            "reasons": ";".join(sorted(self.reasons)),
            "source_forms": _compact(sorted(self.source_forms)),
            "evidence": _compact(self.evidence),
        }


class CandidateBuilder:
    def __init__(self) -> None:
        self.candidates: dict[str, Candidate] = {}
        self.raw_forms: dict[str, set[str]] = {}
        self.stats: Counter[str] = Counter()
        self.legacy_words: set[str] = set()
        self.source_words: dict[str, set[str]] = {
            "legacy": set(),
            "opencorpora": set(),
            "wiktionary": set(),
        }

    def add(
        self,
        raw_word: str,
        source: str,
        kind: str | None = None,
        flags: Iterable[str] = (),
        evidence: str = "",
        reasons: Iterable[str] = (),
        canonical_support: str | None = None,
    ) -> None:
        plain = cleaned_source_form(raw_word)
        if "ё" in raw_word.lower():
            self.stats["changed_yo_to_e"] += 1
        normalized = normalize_word(raw_word)
        if normalized is None:
            normalized = plain
            candidate = self.candidates.setdefault(normalized, Candidate(normalized))
            candidate.invalid = True
            reason = invalid_form_reason(raw_word)
            candidate.reasons.add(reason)
            if reason in {"hyphenated", "multiword", "punctuation_or_non_cyrillic"}:
                self.stats["removed_punctuation_or_multiword"] += 1
        else:
            candidate = self.candidates.setdefault(normalized, Candidate(normalized))
            forms = self.raw_forms.setdefault(normalized, set())
            if raw_word not in forms and forms:
                # Each extra distinct source spelling for one normalized word is one collision.
                self.stats["normalization_collisions"] += 1
            forms.add(raw_word)
        candidate.sources.add(source)
        if kind:
            candidate.kinds.add(kind)
        candidate.flags.update(flags)
        candidate.reasons.update(reasons)
        candidate.source_forms.add(raw_word)
        if evidence and evidence not in candidate.evidence:
            candidate.evidence.append(evidence)
        if canonical_support == "clean":
            candidate.clean_canonical_support = True
        elif canonical_support == "hard_disallowed":
            candidate.hard_disallowed_canonical_support = True
        elif canonical_support == "both":
            candidate.clean_canonical_support = True
            candidate.hard_disallowed_canonical_support = True
        self.source_words.setdefault(source, set()).add(normalized)

    def add_legacy(self, path: Path) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise ValueError("legacy dictionary must be a JSON list")
        self.stats["legacy_total"] = len(data)
        for item in data:
            if isinstance(item, str):
                normalized = normalize_word(item)
                if normalized:
                    self.legacy_words.add(normalized)
                self.add(item, "legacy")
        self.stats["normalized_legacy_total"] = len(self.legacy_words)

    def add_opencorpora(self, path: Path) -> None:
        count_before = len(self.source_words["opencorpora"])
        with bz2.open(path, "rb") as stream:
            for _, elem in ET.iterparse(stream, events=("end",)):
                if elem.tag != "lemma":
                    continue
                self._extract_oc_lemma(elem)
                elem.clear()
        self.stats["opencorpora_candidates"] = len(self.source_words["opencorpora"]) - count_before

    def _extract_oc_lemma(self, lemma: ET.Element) -> None:
        head = lemma.find("l")
        if head is None or not head.get("t"):
            return
        lemma_tags = {g.get("v", "").lower() for g in head.findall("g")}
        forms = [(head, True), *((form, False) for form in lemma.findall("f"))]
        for form, is_headword in forms:
            raw = form.get("t")
            if not raw:
                continue
            form_tags = {g.get("v", "").lower() for g in form.findall("g")}
            lexical_tags = lemma_tags | form_tags
            flags = _oc_flags(lexical_tags)
            kind: str | None = None
            if is_headword:
                if "infn" in lemma_tags:
                    kind = "INFN"
                elif "advb" in lemma_tags:
                    kind = "ADVB"
                elif (
                    "noun" in lemma_tags
                    and "nomn" in lemma_tags
                    and ("sing" in lemma_tags or "pltm" in lemma_tags)
                ):
                    kind = "NOUN"
                elif (
                    "adjf" in lemma_tags
                    and "adjs" not in lemma_tags
                    and {
                        "masc",
                        "sing",
                        "nomn",
                    }
                    <= lemma_tags
                ):
                    kind = "ADJF"
                elif (
                    "prtf" in lemma_tags
                    and "prts" not in lemma_tags
                    and {
                        "masc",
                        "sing",
                        "nomn",
                    }
                    <= lemma_tags
                ):
                    kind = "PRTF"
            elif "infn" in form_tags:
                kind = "INFN"
            elif (
                "noun" in lemma_tags
                and "nomn" in form_tags
                and ("sing" in form_tags or "pltm" in lemma_tags)
            ):
                kind = "NOUN"
            elif (
                "adjf" in lemma_tags
                and "adjs" not in form_tags
                and {
                    "masc",
                    "sing",
                    "nomn",
                }
                <= form_tags
            ):
                kind = "ADJF"
            elif (
                "prtf" in lemma_tags
                and "prts" not in form_tags
                and {
                    "masc",
                    "sing",
                    "nomn",
                }
                <= form_tags
            ):
                kind = "PRTF"
            elif "advb" in form_tags:
                kind = "ADVB"
            if kind:
                support = "hard_disallowed" if flags & HARD_FLAGS else "clean"
                self.add(
                    raw,
                    "opencorpora",
                    kind,
                    flags,
                    "opencorpora:lemma="
                    + ",".join(sorted(lemma_tags))
                    + ";form="
                    + ",".join(sorted(form_tags)),
                    canonical_support=support,
                )

    def add_wiktionary(self, path: Path) -> None:
        count_before = len(self.source_words["wiktionary"])
        with gzip.open(path, "rt", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, 1):
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    self.stats["wiktionary_invalid_json_lines"] += 1
                    continue
                if isinstance(entry, dict) and entry.get("lang_code") == "ru":
                    self._extract_wiktionary_entry(entry, line_number)
        self.stats["wiktionary_candidates"] = len(self.source_words["wiktionary"]) - count_before

    def _extract_wiktionary_entry(self, entry: dict[str, Any], line_number: int) -> None:
        raw_word = entry.get("word")
        if not isinstance(raw_word, str):
            return
        tags = _tag_set(entry.get("tags")) | _tag_set(entry.get("raw_tags"))
        categories = entry.get("categories", [])
        category_text = " ".join(
            item if isinstance(item, str) else str(item.get("name", ""))
            for item in categories
            if isinstance(item, (str, dict))
        )
        senses = [sense for sense in entry.get("senses", []) if isinstance(sense, dict)]
        sense_flags = []
        glosses = []
        for sense in senses:
            sense_tags = _tag_set(sense.get("tags")) | _tag_set(sense.get("raw_tags"))
            sense_glosses = [str(gloss) for gloss in sense.get("glosses", [])]
            glosses.extend(sense_glosses)
            sense_flags.append(_flags_from_metadata(sense_tags, " ".join(sense_glosses)))
        flags = _flags_from_metadata(tags, category_text) | set().union(*sense_flags)
        pos = str(entry.get("pos", "")).lower()
        evidence = (
            f"wiktionary:line={line_number};pos={pos};tags={','.join(sorted(tags))};"
            f"gloss={_compact(glosses, limit=240)}"
        )
        diminutive_senses = sum("diminutive" in flags_for_sense for flags_for_sense in sense_flags)
        independent_senses = sum(
            bool(" ".join(str(item) for item in sense.get("glosses", [])).strip())
            and "diminutive" not in flags_for_sense
            for sense, flags_for_sense in zip(senses, sense_flags)
        )
        if diminutive_senses and diminutive_senses == len(senses) and not independent_senses:
            flags.add("diminutive_only")
        elif diminutive_senses and independent_senses:
            flags.add("diminutive_independent_sense")

        entry_hard = bool(_flags_from_metadata(tags, category_text) & HARD_FLAGS)
        hard_sense = any(flags_for_sense & HARD_FLAGS for flags_for_sense in sense_flags)
        clean_sense = any(not (flags_for_sense & HARD_FLAGS) for flags_for_sense in sense_flags)
        if entry_hard or "diminutive_only" in flags or (hard_sense and not clean_sense):
            support = "hard_disallowed"
        elif hard_sense and clean_sense:
            support = "both"
        else:
            support = "clean"

        non_lemma_form = is_form_of_entry(entry)
        is_participle = pos in {"verb", "verbal"} and (
            "participle" in tags or "причаст" in " ".join(tags)
        )
        if non_lemma_form:
            return
        if is_participle:
            self._add_wiktionary_participle(raw_word, tags, flags, evidence, support)
        elif pos == "noun":
            self.add(raw_word, "wiktionary", "NOUN", flags, evidence, canonical_support=support)
        elif pos in {"verb", "verbal"} and not _has(
            tags, "imperative", "finite", "gerund", "adverbial participle"
        ):
            self.add(raw_word, "wiktionary", "INFN", flags, evidence, canonical_support=support)
        elif pos in {"adj", "adjective"}:
            self.add(raw_word, "wiktionary", "ADJF", flags, evidence, canonical_support=support)
        elif pos in {"adv", "adverb"}:
            self.add(raw_word, "wiktionary", "ADVB", flags, evidence, canonical_support=support)

        for form in entry.get("forms", []):
            if not isinstance(form, dict) or not isinstance(form.get("form"), str):
                continue
            form_tags = _tag_set(form.get("tags")) | _tag_set(form.get("raw_tags"))
            if "participle" in form_tags and {"masculine", "singular", "nominative"} <= form_tags:
                self.add(
                    form["form"],
                    "wiktionary",
                    "PRTF",
                    flags,
                    evidence + ";form=participle",
                    canonical_support=support,
                )

    def _add_wiktionary_participle(
        self, raw_word: str, tags: set[str], flags: set[str], evidence: str, support: str
    ) -> None:
        # Wiktextract's standalone participle page is its canonical headword;
        # inflected variants are separately marked form-of and are rejected above.
        if normalize_word(raw_word) is not None:
            self.add(raw_word, "wiktionary", "PRTF", flags, evidence, canonical_support=support)

    def classify(self) -> None:
        review = {"archaic", "colloquial", "diminutive_independent_sense"}
        for candidate in self.candidates.values():
            if candidate.invalid:
                continue
            candidate.reasons.difference_update(CLASSIFICATION_REASONS)
            if candidate.clean_canonical_support and candidate.hard_disallowed_canonical_support:
                candidate.reasons.add("conflicting_source_metadata")
            elif candidate.hard_disallowed_canonical_support:
                candidate.reasons.update(candidate.flags & HARD_FLAGS)
            elif candidate.flags & review:
                candidate.reasons.update(candidate.flags & review)
            elif "diminutive" in candidate.flags:
                candidate.reasons.add("diminutive_metadata_ambiguous")
            elif candidate.sources == {"legacy"}:
                candidate.reasons.add("legacy_only")
            elif not candidate.kinds & CANONICAL_KINDS:
                candidate.reasons.add("unsupported_or_unknown_form")

    def status(self, candidate: Candidate) -> str:
        hard_reasons = {
            "outside_length_range",
            "hyphenated",
            "multiword",
            "punctuation_or_non_cyrillic",
            *HARD_FLAGS,
            "unsupported_or_unknown_form",
        }
        if candidate.invalid or candidate.reasons & hard_reasons:
            return "REJECT"
        if candidate.reasons:
            return "REVIEW"
        return "ACCEPT"

    def write_outputs(self, output_dir: Path) -> dict[str, Any]:
        self.classify()
        output_dir.mkdir(parents=True, exist_ok=True)
        grouped = {status: [] for status in ("ACCEPT", "REVIEW", "REJECT")}
        for candidate in self.candidates.values():
            grouped[self.status(candidate)].append(candidate)
        accepted_words = sorted(candidate.word for candidate in grouped["ACCEPT"])
        (output_dir / "accepted.json").write_text(
            json.dumps(accepted_words, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        for status, filename in (("REVIEW", "review.csv"), ("REJECT", "rejected.csv")):
            self._write_csv(
                output_dir / filename,
                (item.row() for item in sorted(grouped[status], key=lambda c: c.word)),
            )
        additions = [
            candidate
            for candidate in self.candidates.values()
            if candidate.word not in self.legacy_words
        ]
        addition_rows = []
        for candidate in sorted(additions, key=lambda c: (-len(c.word), c.word)):
            row = candidate.row()
            row["status"] = self.status(candidate)
            row["kind"] = row.pop("kinds")
            addition_rows.append(row)
        self._write_csv(
            output_dir / "long_additions.csv",
            addition_rows,
            fields=[
                "word",
                "length",
                "status",
                "sources",
                "kind",
                "flags",
                "reasons",
                "source_forms",
                "evidence",
            ],
        )
        accepted_set = set(accepted_words)
        summary = dict(self.stats)
        summary.update(
            {
                "legacy_total": self.stats["legacy_total"],
                "normalized_legacy_total": len(self.legacy_words),
                "opencorpora_candidates": self.stats["opencorpora_candidates"],
                "wiktionary_candidates": self.stats["wiktionary_candidates"],
                "total_unique_candidates": len(self.candidates),
                "accepted": len(grouped["ACCEPT"]),
                "review": len(grouped["REVIEW"]),
                "rejected": len(grouped["REJECT"]),
                "new_vs_legacy": len(accepted_set - self.legacy_words),
                "removed_vs_legacy": len(self.legacy_words - accepted_set),
                "normalization": {
                    key: self.stats[key]
                    for key in (
                        "changed_yo_to_e",
                        "removed_punctuation_or_multiword",
                        "normalization_collisions",
                    )
                },
                "length_comparison": self._length_comparison(accepted_set),
                "suffix_comparison": self._suffix_comparison(accepted_set),
                "presence_table": self._presence_table(),
            }
        )
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        return summary

    @staticmethod
    def _write_csv(
        path: Path, rows: Iterable[dict[str, str | int]], fields: list[str] | None = None
    ) -> None:
        fields = fields or [
            "word",
            "length",
            "sources",
            "kinds",
            "flags",
            "reasons",
            "source_forms",
            "evidence",
        ]
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def _length_comparison(self, accepted: set[str]) -> dict[str, dict[str, int]]:
        additions = accepted - self.legacy_words
        return {
            str(limit): {
                "legacy": sum(len(w) >= limit for w in self.legacy_words),
                "accepted": sum(len(w) >= limit for w in accepted),
                "new_additions": sum(len(w) >= limit for w in additions),
            }
            for limit in (10, 12, 15, 18, 20)
        }

    def _suffix_comparison(self, accepted: set[str]) -> dict[str, dict[str, int]]:
        additions = accepted - self.legacy_words
        return {
            suffix: {
                "legacy": sum(w.endswith(suffix) for w in self.legacy_words),
                "accepted": sum(w.endswith(suffix) for w in accepted),
                "new_additions": sum(w.endswith(suffix) for w in additions),
            }
            for suffix in FAMILY_SUFFIXES
        }

    def _presence_table(self) -> dict[str, dict[str, Any]]:
        table = {}
        for word in DIAGNOSTIC_WORDS:
            candidate = self.candidates.get(word)
            table[word] = {
                "legacy": word in self.source_words["legacy"],
                "opencorpora": word in self.source_words["opencorpora"],
                "wiktionary": word in self.source_words["wiktionary"],
                "status": self.status(candidate) if candidate else "MISSING",
                "reasons": sorted(candidate.reasons) if candidate else [],
            }
        return table


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--legacy", required=True, type=Path)
    parser.add_argument("--opencorpora", required=True, type=Path)
    parser.add_argument("--wiktionary", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    builder = CandidateBuilder()
    builder.add_legacy(args.legacy)
    builder.add_opencorpora(args.opencorpora)
    builder.add_wiktionary(args.wiktionary)
    summary = builder.write_outputs(args.output_dir)
    print(
        json.dumps(
            {
                key: summary[key]
                for key in ("accepted", "review", "rejected", "total_unique_candidates")
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
