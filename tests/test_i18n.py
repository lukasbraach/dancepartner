"""The bilingual string tables: key parity, placeholder parity, and language selection."""

from __future__ import annotations

from string import Formatter

import pytest

from dancepartner.i18n import TABLES, Language, _initial_language, get_language, set_language, t


def placeholders(template: str) -> set[str]:
    return {field for _, field, _, _ in Formatter().parse(template) if field is not None}


def test_the_tables_share_one_key_set() -> None:
    assert TABLES[Language.EN].keys() == TABLES[Language.DE].keys()


def test_every_key_uses_the_same_placeholders_in_both_languages() -> None:
    mismatched = [
        key
        for key, template in TABLES[Language.EN].items()
        if placeholders(template) != placeholders(TABLES[Language.DE][key])
    ]
    assert mismatched == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(None, Language.EN, id="unset"),
        pytest.param("en", Language.EN, id="en"),
        pytest.param("de", Language.DE, id="de"),
        pytest.param("fr", Language.EN, id="unknown-falls-back"),
        pytest.param("", Language.EN, id="empty-falls-back"),
    ],
)
def test_initial_language(raw: str | None, expected: Language) -> None:
    assert _initial_language(raw) is expected


def test_set_language_switches_what_t_returns() -> None:
    set_language(Language.DE)
    assert get_language() is Language.DE
    german = t("check.ok")
    set_language(Language.EN)
    assert get_language() is Language.EN
    assert t("check.ok") != german
    assert t("check.ok") == TABLES[Language.EN]["check.ok"]


def test_t_formats_params() -> None:
    assert "nope.yaml" in t("error.file_not_found", path="nope.yaml")


def test_t_raises_on_a_missing_key() -> None:
    with pytest.raises(KeyError):
        t("no.such.key")
