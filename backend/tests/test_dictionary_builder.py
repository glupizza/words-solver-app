import bz2
import gzip
import json
import re

from backend.tools.build_dictionary_candidates import (
    PROPER_TARGET,
    CandidateBuilder,
    _is_possible_proper_derived_gloss,
    _is_proper_derived_gloss,
    normalize_word,
)


def test_normalize_word() -> None:
    assert normalize_word("Ёл\u0301КА") == "елка"
    assert normalize_word("край") == "край"
    assert normalize_word("кра\u0301й") == "край"
    assert normalize_word("  слово") is None
    assert normalize_word("два слова") is None
    assert normalize_word("как-то") is None
    assert normalize_word("а") is None
    assert normalize_word("а" * 25) == "а" * 25
    assert normalize_word("а" * 26) is None


def test_normalization_collisions_are_incremental() -> None:
    builder = CandidateBuilder()
    builder.add("ёж", "legacy")
    builder.add("еж", "legacy")
    builder.add("еж", "legacy")
    assert builder.stats["normalization_collisions"] == 1


def test_opencorpora_extracts_only_game_forms(tmp_path) -> None:
    xml = """<dictionary><lemmata>
    <lemma><l t="кот"><g v="NOUN"/><g v="masc"/></l><f t="кот"><g v="sing"/><g v="nomn"/></f><f t="коты"><g v="plur"/><g v="nomn"/></f></lemma>
    <lemma><l t="ножницы"><g v="NOUN"/><g v="Pltm"/></l><f t="ножницы"><g v="plur"/><g v="nomn"/></f></lemma>
    <lemma><l t="читать"><g v="INFN"/><g v="impf"/></l><f t="читать"><g v="INFN"/></f><f t="читаю"><g v="VERB"/><g v="pres"/><g v="sing"/><g v="1per"/></f><f t="читал"><g v="VERB"/><g v="past"/><g v="sing"/><g v="masc"/></f><f t="читай"><g v="VERB"/><g v="impr"/><g v="sing"/></f></lemma>
    <lemma><l t="красный"><g v="ADJF"/></l><f t="красный"><g v="masc"/><g v="sing"/><g v="nomn"/></f><f t="красен"><g v="ADJS"/><g v="masc"/><g v="sing"/><g v="nomn"/></f></lemma>
    <lemma><l t="написанный"><g v="PRTF"/></l><f t="написанный"><g v="masc"/><g v="sing"/><g v="nomn"/></f></lemma>
    <lemma><l t="быстро"><g v="ADVB"/></l></lemma>
    <lemma><l t="читаю"><g v="VERB"/></l></lemma>
    <lemma><l t="читая"><g v="GRND"/></l></lemma>
    </lemmata></dictionary>"""
    source = tmp_path / "dict.xml.bz2"
    source.write_bytes(bz2.compress(xml.encode()))
    builder = CandidateBuilder()
    builder.add_opencorpora(source)
    assert {"кот", "ножницы", "читать", "красный", "написанный", "быстро"} <= set(
        builder.candidates
    )
    assert "коты" not in builder.candidates
    assert "красен" not in builder.candidates
    assert "читаю" not in builder.candidates
    assert "читал" not in builder.candidates
    assert "читай" not in builder.candidates
    assert "читая" not in builder.candidates
    assert builder.candidates["читать"].kinds == {"INFN"}
    assert all(
        all(grammar not in evidence for grammar in ("pres", "past", "impr", "verb"))
        for evidence in builder.candidates["читать"].evidence
    )


def _write_wiktionary(path, entries) -> None:
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for entry in entries:
            stream.write(json.dumps(entry, ensure_ascii=False) + "\n")


def test_wiktionary_verb_forms_extract_real_participle(tmp_path) -> None:
    source = tmp_path / "ru.jsonl.gz"
    _write_wiktionary(
        source,
        [
            {
                "word": "перепрограммировать",
                "lang_code": "ru",
                "pos": "verb",
                "forms": [
                    {
                        "form": "перепрограммированный",
                        "tags": [
                            "participle",
                            "passive",
                            "past",
                            "singular",
                            "masculine",
                            "nominative",
                        ],
                    },
                    {"form": "перепрограммирую", "tags": ["first-person", "singular"]},
                    {"form": "перепрограммировав", "tags": ["gerund"]},
                ],
            }
        ],
    )
    builder = CandidateBuilder()
    builder.add_wiktionary(source)
    assert {"перепрограммировать", "перепрограммированный"} <= set(builder.candidates)
    assert "перепрограммирую" not in builder.candidates
    assert "перепрограммировав" not in builder.candidates


def test_standalone_participle(tmp_path) -> None:
    source = tmp_path / "ru.jsonl.gz"
    _write_wiktionary(
        source,
        [
            {
                "word": "написанный",
                "lang_code": "ru",
                "pos": "verb",
                "tags": ["participle"],
                "forms": [
                    {
                        "form": "написанный",
                        "tags": ["participle", "masculine", "singular", "nominative"],
                    }
                ],
            }
        ],
    )
    builder = CandidateBuilder()
    builder.add_wiktionary(source)
    assert builder.candidates["написанный"].kinds == {"PRTF"}


def test_wiktionary_standalone_canonical_participle_without_forms(tmp_path) -> None:
    source = tmp_path / "ru.jsonl.gz"
    _write_wiktionary(
        source,
        [
            {
                "word": "отрёпанный",
                "lang_code": "ru",
                "pos": "verb",
                "tags": ["participle"],
                "senses": [
                    {
                        "tags": ["participle"],
                        "glosses": ["страд. прич. прош. вр. от отрепать"],
                    }
                ],
            },
            {
                "word": "отрёпанная",
                "lang_code": "ru",
                "pos": "verb",
                "tags": ["participle"],
                "senses": [
                    {
                        "tags": ["form-of", "participle"],
                        "form_of": [{"word": "отрёпанный"}],
                    }
                ],
            },
        ],
    )
    builder = CandidateBuilder()
    builder.add_wiktionary(source)
    assert builder.candidates["отрепанный"].kinds == {"PRTF"}
    assert "отрепанная" not in builder.candidates


def test_wiktionary_form_of_entries_do_not_become_lemmas(tmp_path) -> None:
    source = tmp_path / "ru.jsonl.gz"
    _write_wiktionary(
        source,
        [
            {
                "word": "уходил",
                "lang_code": "ru",
                "pos": "verb",
                "senses": [{"form_of": [{"word": "уходить"}], "tags": ["form-of"]}],
            },
            {
                "word": "котам",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [
                    {
                        "form_of": [{"word": "кот"}],
                        "tags": ["form-of", "dative", "plural"],
                    }
                ],
            },
            {"word": "уходить", "lang_code": "ru", "pos": "verb", "senses": [{}]},
            {"word": "кот", "lang_code": "ru", "pos": "noun", "senses": [{}]},
        ],
    )
    builder = CandidateBuilder()
    builder.add_wiktionary(source)
    assert "уходил" not in builder.candidates
    assert "котам" not in builder.candidates
    assert builder.candidates["уходить"].kinds == {"INFN"}
    assert builder.candidates["кот"].kinds == {"NOUN"}


def test_wiktionary_russian_proper_name_category_is_rejected(tmp_path) -> None:
    source = tmp_path / "ru.jsonl.gz"
    _write_wiktionary(
        source,
        [
            {
                "word": "Ваня",
                "lang_code": "ru",
                "pos": "noun",
                "categories": ["Имена собственные/ru", "Мужские имена/ru"],
                "senses": [{}],
            }
        ],
    )
    builder = CandidateBuilder()
    builder.add_wiktionary(source)
    builder.classify()
    assert builder.status(builder.candidates["ваня"]) == "REJECT"
    assert "proper_name" in builder.candidates["ваня"].reasons


def test_wiktionary_gloss_labels_do_not_match_ordinary_words(tmp_path) -> None:
    source = tmp_path / "ru.jsonl.gz"
    _write_wiktionary(
        source,
        [
            {
                "word": "собрание",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["собрание изображений"]}],
            },
            {
                "word": "мембрана",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["мембранный белок"]}],
            },
            {
                "word": "бронхоспазм",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["вызванное сокращением мышц"]}],
            },
            {
                "word": "апокопировать",
                "lang_code": "ru",
                "pos": "verb",
                "senses": [{"glosses": ["сокращать слово в конце"]}],
            },
            {
                "word": "гиповолемия",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["уменьшение объёма крови"]}],
            },
            {
                "word": "дегрессивный",
                "lang_code": "ru",
                "pos": "adjective",
                "senses": [{"glosses": ["нисходящий, уменьшающийся"]}],
            },
        ],
    )
    builder = CandidateBuilder()
    builder.add_wiktionary(source)
    builder.classify()
    for word in (
        "собрание",
        "мембрана",
        "бронхоспазм",
        "апокопировать",
        "гиповолемия",
        "дегрессивный",
    ):
        assert not builder.candidates[word].flags & {"vulgar", "abbreviation", "diminutive"}
        assert builder.status(builder.candidates[word]) == "ACCEPT"


def test_wiktionary_explicit_gloss_labels_are_classified(tmp_path) -> None:
    source = tmp_path / "ru.jsonl.gz"
    _write_wiktionary(
        source,
        [
            {
                "word": "жаргон",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["жарг. слово"]}],
            },
            {
                "word": "просторечие",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["прост. слово"]}],
            },
            {
                "word": "обсценность",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["обсц. слово"]}],
            },
            {
                "word": "аббревиатура",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["сокр. от слова"]}],
            },
            {
                "word": "ласковость",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["ласк. к слову"]}],
            },
            {
                "word": "разговорность",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["разг. слово"]}],
            },
        ],
    )
    builder = CandidateBuilder()
    builder.add_wiktionary(source)
    builder.classify()
    assert builder.status(builder.candidates["жаргон"]) == "REJECT"
    assert "slang" in builder.candidates["жаргон"].reasons
    assert builder.status(builder.candidates["просторечие"]) == "REJECT"
    assert "vernacular" in builder.candidates["просторечие"].reasons
    assert builder.status(builder.candidates["обсценность"]) == "REJECT"
    assert "vulgar" in builder.candidates["обсценность"].reasons
    assert builder.status(builder.candidates["аббревиатура"]) == "REJECT"
    assert "abbreviation" in builder.candidates["аббревиатура"].reasons
    assert builder.status(builder.candidates["ласковость"]) == "REJECT"
    assert "diminutive_only" in builder.candidates["ласковость"].reasons
    assert builder.status(builder.candidates["разговорность"]) == "REVIEW"
    assert "colloquial" in builder.candidates["разговорность"].reasons


def test_wiktionary_capitalized_proper_and_pronominal_metadata(tmp_path) -> None:
    source = tmp_path / "ru.jsonl.gz"
    _write_wiktionary(
        source,
        [
            {
                "word": "Верхнеблаговещенское",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["село в России"]}],
            },
            {
                "word": "Лев",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["мужское имя"]}],
            },
            {
                "word": "лев",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["хищное животное"]}],
            },
            {
                "word": "этот",
                "lang_code": "ru",
                "pos": "adjective",
                "tags": ["pronominal"],
                "senses": [{"glosses": ["указательное слово"]}],
            },
            {
                "word": "байрактаровский",
                "lang_code": "ru",
                "pos": "adjective",
                "senses": [{"glosses": ["относящийся к человеку с фамилией Байрактар"]}],
            },
            {
                "word": "марьинорощинский",
                "lang_code": "ru",
                "pos": "adjective",
                "senses": [{"glosses": ["относящийся к топониму Марьина Роща"]}],
            },
        ],
    )
    builder = CandidateBuilder()
    builder.add_wiktionary(source)
    builder.classify()
    assert builder.status(builder.candidates["верхнеблаговещенское"]) == "REJECT"
    assert "proper_name" in builder.candidates["верхнеблаговещенское"].reasons
    assert builder.status(builder.candidates["лев"]) == "REVIEW"
    assert "conflicting_source_metadata" in builder.candidates["лев"].reasons
    assert builder.status(builder.candidates["этот"]) == "REJECT"
    assert "pronoun" in builder.candidates["этот"].reasons
    for word in ("байрактаровский", "марьинорощинский"):
        assert builder.status(builder.candidates[word]) == "REJECT"
        assert "proper_derived" in builder.candidates[word].reasons


def test_proper_derived_requires_a_concrete_capitalized_target(tmp_path) -> None:
    source = tmp_path / "ru.jsonl.gz"
    _write_wiktionary(
        source,
        [
            {
                "word": "нарратор",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["лицо, от имени которого ведётся повествование"]}],
            },
            {
                "word": "деноминатив",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["слово, образованное от имени существительного"]}],
            },
            {
                "word": "врез",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["сообщение от имени редакции"]}],
            },
            {
                "word": "гатчинский",
                "lang_code": "ru",
                "pos": "adjective",
                "senses": [{"glosses": ["связанный по значению с существительным Гатчина"]}],
            },
            {
                "word": "боровичанка",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["жительница или уроженка города Боровичи"]}],
            },
            {
                "word": "канец",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["этнохороним от Канск"]}],
            },
            {
                "word": "центральноамериканец",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["житель Центральной Америки"]}],
            },
        ],
    )
    builder = CandidateBuilder()
    builder.add_wiktionary(source)
    builder.classify()
    for word in ("нарратор", "деноминатив", "врез"):
        assert "proper_derived" not in builder.candidates[word].flags
        assert builder.status(builder.candidates[word]) == "ACCEPT"
    for word in ("гатчинский", "боровичанка", "канец", "центральноамериканец"):
        assert builder.status(builder.candidates[word]) == "REJECT"
        assert "proper_derived" in builder.candidates[word].reasons


def test_proper_derived_targets_are_grouped_and_complete() -> None:
    assert not _is_proper_derived_gloss("adjective", "описание восточной части Украины")
    assert not _is_proper_derived_gloss("adjective", "книга о западной части России")
    assert _is_proper_derived_gloss("adjective", "относящийся к восточной части Украины")
    assert _is_proper_derived_gloss("noun", "житель Санкт-Петербурга")
    assert _is_proper_derived_gloss("noun", "житель МГУ")
    assert _is_proper_derived_gloss("adjective", "относящийся к компании Microsoft")
    for target in ("Санкт-Петербурга", "МГУ", "Ростов-на-Дону", "Microsoft", "New-York"):
        assert re.fullmatch(PROPER_TARGET, target)
    assert re.search(PROPER_TARGET, "H2O") is None
    assert re.search(PROPER_TARGET, "C7H7O4N") is None
    assert not _is_possible_proper_derived_gloss(
        "adjective", "относящийся к кислоте с формулой C7H7O4N"
    )
    assert not _is_possible_proper_derived_gloss("adjective", "относящийся к веществу H2O")
    assert not _is_proper_derived_gloss("adjective", "связанный с H2O")


def test_residual_proper_derived_and_full_lexicographic_phrases(tmp_path) -> None:
    source = tmp_path / "ru.jsonl.gz"
    _write_wiktionary(
        source,
        [
            {
                "word": "екатеринбурженка",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["жительница Екатеринбурга"]}],
            },
            {
                "word": "санктпетербуржец",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["житель Санкт-Петербурга"]}],
            },
            {
                "word": "владивостоковец",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["житель или уроженец Владивостока"]}],
            },
            {
                "word": "восточноевропеец",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["житель Восточной Европы"]}],
            },
            {
                "word": "древнегрузинский",
                "lang_code": "ru",
                "pos": "adjective",
                "senses": [{"glosses": ["относящийся к древней Грузии"]}],
            },
            {
                "word": "майкрософтовский",
                "lang_code": "ru",
                "pos": "adjective",
                "senses": [{"glosses": ["относящийся к компании Microsoft"]}],
            },
            {
                "word": "хемингуэевский",
                "lang_code": "ru",
                "pos": "adjective",
                "senses": [{"glosses": ["принадлежащий человеку по фамилии Хемингуэй"]}],
            },
            {
                "word": "гелиометеорологический",
                "lang_code": "ru",
                "pos": "adjective",
                "senses": [
                    {"glosses": ["связанный с изучением влияния Солнца на атмосферу Земли"]}
                ],
            },
            {
                "word": "ковыряльник",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["жаргонное название оружия"]}],
            },
            {
                "word": "вентилек",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["уменьшительное от вентиль"]}],
            },
            {
                "word": "дитятце",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["уменьшительный вариант для дитя"]}],
            },
            {
                "word": "ребячка",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["сокращённое название для ребёнка"]}],
            },
        ],
    )
    builder = CandidateBuilder()
    builder.add_wiktionary(source)
    builder.classify()
    for word in (
        "екатеринбурженка",
        "санктпетербуржец",
        "владивостоковец",
        "восточноевропеец",
        "древнегрузинский",
        "майкрософтовский",
        "хемингуэевский",
    ):
        assert builder.status(builder.candidates[word]) == "REJECT"
        assert "proper_derived" in builder.candidates[word].reasons
    assert "proper_derived" not in builder.candidates["гелиометеорологический"].flags
    assert builder.status(builder.candidates["ковыряльник"]) == "REJECT"
    assert builder.status(builder.candidates["вентилек"]) == "REJECT"
    assert builder.status(builder.candidates["дитятце"]) == "REJECT"
    assert builder.status(builder.candidates["ребячка"]) == "REJECT"


def test_compound_labels_and_adjective_forms(tmp_path) -> None:
    source = tmp_path / "ru.jsonl.gz"
    _write_wiktionary(
        source,
        [
            {
                "word": "нормас",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["мол. слово"]}],
            },
            {
                "word": "крипово",
                "lang_code": "ru",
                "pos": "adverb",
                "senses": [{"glosses": ["сленг, слово"]}],
            },
            {
                "word": "криминализм",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["крим.жарг. слово"]}],
            },
            {
                "word": "грубость",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["груб.-прост. слово"]}],
            },
            {
                "word": "химически",
                "lang_code": "ru",
                "pos": "adverb",
                "senses": [{"glosses": ["хим.разг. термин"]}],
            },
            {
                "word": "сибиряк",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["рег. (Сиб.) слово"]}],
            },
            {
                "word": "старина",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["старин. слово"]}],
            },
            {
                "word": "эшелончик",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["ум.-ласк. к эшелон"]}],
            },
            {
                "word": "перепелочка",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["уменьш-ласк. к перепёлка"]}],
            },
            {
                "word": "красивее",
                "lang_code": "ru",
                "pos": "adj",
                "senses": [{"glosses": ["сравн. ст. к прил. красивый"]}],
            },
            {
                "word": "вразумительно",
                "lang_code": "ru",
                "pos": "adj",
                "tags": ["predicative"],
                "senses": [{"glosses": ["предикатив"]}],
            },
            {
                "word": "вразумительно",
                "lang_code": "ru",
                "pos": "adv",
                "senses": [{"glosses": ["наречие к вразумительный"]}],
            },
        ],
    )
    builder = CandidateBuilder()
    builder.add_wiktionary(source)
    builder.classify()
    for word in ("нормас", "крипово", "криминализм", "грубость"):
        assert builder.status(builder.candidates[word]) == "REJECT"
    assert builder.status(builder.candidates["химически"]) == "REVIEW"
    assert "colloquial" in builder.candidates["химически"].reasons
    assert "dialectal" in builder.candidates["сибиряк"].reasons
    assert "archaic" in builder.candidates["старина"].reasons
    assert builder.status(builder.candidates["эшелончик"]) == "REJECT"
    assert builder.status(builder.candidates["перепелочка"]) == "REJECT"
    assert "красивее" not in builder.candidates
    assert builder.candidates["вразумительно"].kinds == {"ADVB"}
    assert builder.stats["wiktionary_noncanonical_adjective_forms_skipped"] == 2


def test_wiktionary_gerund_introductory_and_weak_evidence(tmp_path) -> None:
    source = tmp_path / "ru.jsonl.gz"
    _write_wiktionary(
        source,
        [
            {
                "word": "делая",
                "lang_code": "ru",
                "pos": "verb",
                "tags": ["gerund", "participle"],
                "senses": [{"glosses": ["дееприч. от делать"]}],
            },
            {
                "word": "конечно",
                "lang_code": "ru",
                "pos": "adverb",
                "senses": [{"glosses": ["вводн. сл. выражает уверенность"]}],
            },
            {
                "word": "серьезно",
                "lang_code": "ru",
                "pos": "adverb",
                "senses": [
                    {"glosses": ["вводн. сл. выражает оценку"]},
                    {"glosses": ["с большой серьёзностью"]},
                ],
            },
            {"word": "безглоссовый", "lang_code": "ru", "pos": "adjective", "senses": [{}]},
        ],
    )
    builder = CandidateBuilder()
    builder.add_wiktionary(source)
    builder.classify()
    assert "делая" not in builder.candidates
    assert builder.status(builder.candidates["конечно"]) == "REJECT"
    assert "introductory_only" in builder.candidates["конечно"].reasons
    assert builder.status(builder.candidates["серьезно"]) == "REVIEW"
    assert "introductory_with_independent_sense" in builder.candidates["серьезно"].reasons
    assert builder.status(builder.candidates["безглоссовый"]) == "REVIEW"
    assert "weak_wiktionary_evidence" in builder.candidates["безглоссовый"].reasons


def test_opencorpora_excluded_grammemes(tmp_path) -> None:
    xml = """<dictionary version="0.92" revision="405913"><lemmata>
    <lemma><l t="этот"><g v="ADJF"/><g v="Apro"/></l><f t="этот"><g v="masc"/><g v="sing"/><g v="nomn"/></f></lemma>
    <lemma><l t="его"><g v="ADJF"/><g v="Apro"/></l><f t="его"><g v="masc"/><g v="sing"/><g v="nomn"/></f></lemma>
    <lemma><l t="невознобновимый"><g v="ADJF"/><g v="Erro"/></l><f t="невознобновимый"><g v="masc"/><g v="sing"/><g v="nomn"/></f></lemma>
    </lemmata></dictionary>"""
    source = tmp_path / "dict.xml.bz2"
    source.write_bytes(bz2.compress(xml.encode()))
    builder = CandidateBuilder()
    builder.add_opencorpora(source)
    builder.classify()
    assert builder.status(builder.candidates["этот"]) == "REJECT"
    assert "pronoun" in builder.candidates["этот"].reasons
    assert builder.status(builder.candidates["его"]) == "REJECT"
    assert builder.status(builder.candidates["невознобновимый"]) == "REJECT"
    assert "typo" in builder.candidates["невознобновимый"].reasons
    summary = builder.write_outputs(tmp_path / "report")
    assert summary["opencorpora_metadata"] == {"version": "0.92", "revision": "405913"}
    assert set(summary["status_by_source"]) == {"legacy", "opencorpora", "wiktionary"}
    assert set(summary["accepted_by_kind"]) == {"NOUN", "INFN", "ADJF", "PRTF", "ADVB"}


def test_clean_and_proper_homonym_is_reviewed_as_conflicting(tmp_path) -> None:
    source = tmp_path / "ru.jsonl.gz"
    _write_wiktionary(
        source,
        [
            {"word": "лев", "lang_code": "ru", "pos": "noun", "senses": [{}]},
            {
                "word": "лев",
                "lang_code": "ru",
                "pos": "noun",
                "categories": ["Имена собственные/ru"],
                "senses": [{}],
            },
        ],
    )
    builder = CandidateBuilder()
    builder.add_wiktionary(source)
    builder.classify()
    assert builder.status(builder.candidates["лев"]) == "REVIEW"
    assert builder.candidates["лев"].reasons == {"conflicting_source_metadata"}


def test_diminutive_classification(tmp_path) -> None:
    source = tmp_path / "ru.jsonl.gz"
    _write_wiktionary(
        source,
        [
            {
                "word": "сборчик",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["уменьш.-ласк. к сбор"]}],
            },
            {
                "word": "ключик",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [
                    {"glosses": ["уменьш. к ключ"]},
                    {"glosses": ["самостоятельное техническое значение"]},
                ],
            },
        ],
    )
    builder = CandidateBuilder()
    builder.add_wiktionary(source)
    builder.classify()
    assert builder.status(builder.candidates["сборчик"]) == "REJECT"
    assert "diminutive_only" in builder.candidates["сборчик"].reasons
    assert builder.status(builder.candidates["ключик"]) == "REVIEW"
    assert "diminutive_independent_sense" in builder.candidates["ключик"].reasons


def test_legacy_only_and_merge_evidence(tmp_path) -> None:
    legacy = tmp_path / "legacy.json"
    legacy.write_text(json.dumps(["старое", "кот"], ensure_ascii=False), encoding="utf-8")
    source = tmp_path / "ru.jsonl.gz"
    _write_wiktionary(source, [{"word": "кот", "lang_code": "ru", "pos": "noun"}])
    builder = CandidateBuilder()
    builder.add_legacy(legacy)
    builder.add_wiktionary(source)
    builder.classify()
    assert builder.status(builder.candidates["старое"]) == "REVIEW"
    assert builder.candidates["старое"].reasons == {"legacy_only"}
    assert builder.candidates["кот"].sources == {"legacy", "wiktionary"}
    assert builder.status(builder.candidates["кот"]) == "ACCEPT"
    summary = builder.write_outputs(tmp_path / "report")
    assert summary["new_vs_legacy"] == 0
    assert {
        "summary.json",
        "accepted.json",
        "accepted.csv",
        "review.csv",
        "rejected.csv",
        "long_additions.csv",
    } == {path.name for path in (tmp_path / "report").iterdir()}
    review_header = (tmp_path / "report" / "review.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "source_forms" in review_header
    assert "evidence" in review_header


def test_final_resident_phrases_and_conflict_semantics(tmp_path) -> None:
    source = tmp_path / "ru.jsonl.gz"
    _write_wiktionary(
        source,
        [
            {
                "word": "базарнокарабулакец",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["житель или уроженец посёлка Базарный Карабулак"]}],
            },
            {
                "word": "висконсинец",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["житель штата Висконсин"]}],
            },
            {
                "word": "барбадосец",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["житель острова Барбадос"]}],
            },
            {
                "word": "пригорожанин",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["истор. житель пригорода (в Древней Руси)"]}],
            },
            {
                "word": "компатриотка",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["уроженка одной с кем-либо страны"]}],
            },
            {
                "word": "лапуля",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["ласковое обращение"]}],
            },
            {
                "word": "механообработка",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["сокращение от: механическая обработка"]}],
            },
            {
                "word": "мышца",
                "lang_code": "ru",
                "pos": "noun",
                "senses": [{"glosses": ["сокращение мышц"]}],
            },
            {
                "word": "ломоносовский",
                "lang_code": "ru",
                "pos": "adjective",
                "senses": [
                    {"glosses": ["связанный, соотносящийся по значению с фамилией Ломоносов"]}
                ],
            },
        ],
    )
    builder = CandidateBuilder()
    builder.add_wiktionary(source)
    builder.add("висконсинец", "opencorpora", "NOUN", canonical_support="clean")
    builder.classify()
    for word in ("базарнокарабулакец", "барбадосец", "лапуля", "механообработка"):
        assert builder.status(builder.candidates[word]) == "REJECT"
    assert builder.status(builder.candidates["висконсинец"]) == "REVIEW"
    assert "conflicting_source_metadata" in builder.candidates["висконсинец"].reasons
    assert "proper_derived" not in builder.candidates["пригорожанин"].flags
    assert "proper_derived" not in builder.candidates["компатриотка"].flags
    assert "abbreviation" not in builder.candidates["мышца"].flags
    assert builder.status(builder.candidates["ломоносовский"]) == "REVIEW"
    assert "possible_proper_derived" in builder.candidates["ломоносовский"].reasons


def test_research_confidence_tiers_and_accepted_csv(tmp_path) -> None:
    builder = CandidateBuilder()
    builder.add("двойной", "opencorpora", "ADJF", canonical_support="clean")
    builder.add(
        "двойной", "wiktionary", "ADJF", canonical_support="clean", meaningful_wiktionary_gloss=True
    )
    builder.add("легаси", "legacy")
    builder.add(
        "легаси", "wiktionary", "NOUN", canonical_support="clean", meaningful_wiktionary_gloss=True
    )
    builder.add("причастидлинное", "opencorpora", "PRTF", canonical_support="clean")
    builder.add("одиннадцать", "opencorpora", "PRTF", canonical_support="clean")
    builder.add(
        "википричастидлинное",
        "wiktionary",
        "PRTF",
        canonical_support="clean",
        meaningful_wiktionary_gloss=True,
    )
    builder.add(
        "плохое",
        "wiktionary",
        "NOUN",
        {"slang"},
        canonical_support="hard_disallowed",
        meaningful_wiktionary_gloss=True,
    )
    summary = builder.write_outputs(tmp_path / "report")
    assert builder.confidence(builder.candidates["двойной"])[0] == "A_DUAL_EXTERNAL"
    assert builder.confidence(builder.candidates["легаси"])[0] == "B_LEGACY_CONFIRMED"
    assert builder.confidence(builder.candidates["причастидлинное"])[0] == "C_OC_LONG_PARTICIPLE"
    assert builder.confidence(builder.candidates["одиннадцать"])[0] == "D_SINGLE_SOURCE"
    assert builder.confidence(builder.candidates["википричастидлинное"])[0] == "D_SINGLE_SOURCE"
    assert "плохое" not in (tmp_path / "report" / "accepted.csv").read_text(encoding="utf-8")
    assert summary["confidence_tier_counts"]["A_DUAL_EXTERNAL"] == 1
    header = (tmp_path / "report" / "accepted.csv").read_text(encoding="utf-8").splitlines()[0]
    assert "confidence_tier" in header and "confidence_reasons" in header
