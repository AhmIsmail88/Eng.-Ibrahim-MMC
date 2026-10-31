"""Arabic search normalization rules (SPEC 4.5)."""
from __future__ import annotations

import pytest

from eng_ibrahim.domain.text_normalization import (
    normalize_code,
    normalize_search,
    search_pattern,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("مضخة", "مضخه"),
        ("مضخه", "مضخه"),
        ("أحمد", "احمد"),
        ("إسماعيل", "اسماعيل"),
        ("آلة", "اله"),
        ("مُضَخَّة", "مضخه"),
        ("مضخـــة", "مضخه"),  # tatweel
        ("  مضخة   غاطسة  ", "مضخه غاطسه"),
        ("Pump-101", "pump-101"),
        ("٢٠٢٦", "2026"),
    ],
)
def test_normalize_search_folds_arabic_variants(raw: str, expected: str) -> None:
    assert normalize_search(raw) == expected


def test_normalize_is_idempotent() -> None:
    once = normalize_search("المضخة الغاطسة رقم ٣")
    assert normalize_search(once) == once


def test_empty_and_none() -> None:
    assert normalize_search("") == ""
    assert normalize_search(None) == ""


def test_codes_are_only_trimmed() -> None:
    assert normalize_code("  PMP-101 ") == "PMP-101"
    assert normalize_code(None) == ""


def test_like_pattern_escapes_wildcards() -> None:
    assert search_pattern("50%_off") == "50\\%\\_off"
