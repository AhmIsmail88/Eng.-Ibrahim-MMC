"""Every literal translation key used in the code exists in both languages (review F-09).

A missing key shows the raw key (e.g. ``parts.empty``) to the user. Dynamic keys built with
f-strings (``value.wo.{status}``) are checked by the value-list test below.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "eng_ibrahim"
LITERAL = re.compile(r"""\btr\(\s*["']([a-z][a-z0-9_]*(?:\.[A-Za-z0-9_ ]+)+)["']""")


def _table(lang: str) -> dict[str, str]:
    return json.loads((SRC / "localization" / f"{lang}.json").read_text(encoding="utf-8"))


def _literal_keys() -> set[str]:
    keys: set[str] = set()
    for path in SRC.rglob("*.py"):
        keys |= set(LITERAL.findall(path.read_text(encoding="utf-8")))
    return keys


def test_every_literal_key_exists_in_both_languages():
    keys = _literal_keys()
    assert len(keys) > 300  # the scan really found the code's keys
    for lang in ("ar", "en"):
        missing = sorted(keys - set(_table(lang)))
        assert not missing, f"{lang}.json is missing: {missing}"


def test_both_languages_have_the_same_keys():
    ar, en = set(_table("ar")), set(_table("en"))
    assert not sorted(ar - en), f"only in ar.json: {sorted(ar - en)}"
    assert not sorted(en - ar), f"only in en.json: {sorted(en - ar)}"


def test_stored_values_shown_in_lists_are_translated():
    """Values stored in English and shown through value.* keys (statuses, trades...)."""
    from eng_ibrahim.infrastructure.database.orm_models.maintenance import (
        EXPENSE_TYPE,
        TIME_CATEGORY,
        WO_STATUS,
    )
    from eng_ibrahim.presentation.pages.technicians import TRADES
    groups = {"value.expense": EXPENSE_TYPE, "value.trade": TRADES,
              "value.timec": TIME_CATEGORY, "value.wo": WO_STATUS}
    for lang in ("ar", "en"):
        table = _table(lang)
        missing = [f"{prefix}.{v}" for prefix, values in groups.items() for v in values
                   if f"{prefix}.{v}" not in table]
        assert not missing, f"{lang}.json is missing: {missing}"
