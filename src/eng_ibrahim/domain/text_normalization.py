"""Arabic-aware search normalization (SPEC 4.5).

Pure and Qt-free so the same rules run when writing `search_norm` and when
searching. The original text is never modified — this is comparison-only.
"""
from __future__ import annotations

import re

# Harakat, tatweel and Quranic marks: removed for comparison.
_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]")
_ARABIC_INDIC = "٠١٢٣٤٥٦٧٨٩"
_EXTENDED_INDIC = "۰۱۲۳۴۵۶۷۸۹"
_DIGITS = str.maketrans(_ARABIC_INDIC + _EXTENDED_INDIC, "0123456789" * 2)
_FOLD = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
    "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
})
_SPACES = re.compile(r"\s+")


def normalize_search(text: str | None) -> str:
    """Fold Arabic variants and digits so `مضخه` finds `مضخة` and `احمد` finds `أحمد`.

    Order matters: digits first (they are separate code points), then lowercasing,
    then diacritics, then letter folding, then whitespace.
    """
    if not text:
        return ""
    value = str(text).translate(_DIGITS).lower()
    value = _DIACRITICS.sub("", value)
    value = value.translate(_FOLD)
    return _SPACES.sub(" ", value).strip()


def normalize_code(text: str | None) -> str:
    """Codes are compared case-insensitively after trimming, but never folded."""
    return (text or "").strip()


def search_pattern(text: str | None) -> str:
    """Value for `LIKE '%...%'`, with % and _ escaped (SQLite ESCAPE '\\')."""
    value = normalize_search(text)
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
