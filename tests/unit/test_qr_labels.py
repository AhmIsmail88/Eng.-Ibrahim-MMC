"""QR label generation (UI-023)."""
from __future__ import annotations

from PIL import Image

from eng_ibrahim.infrastructure.exports.qr_labels import write_qr_png, write_sheet


def test_single_qr_is_a_real_png(tmp_path):
    path = write_qr_png("PMP-101", tmp_path / "qr.png")
    assert path.exists()
    with Image.open(path) as image:
        assert image.format == "PNG" and image.width > 50


def test_sheet_contains_all_labels(tmp_path):
    path = write_sheet([("PMP-1", "مضخة 1"), ("PMP-2", "مضخة 2")], tmp_path / "sheet.png")
    assert path.exists() and path.stat().st_size > 1000
    with Image.open(path) as image:
        assert image.width > 400
    assert not list(tmp_path.glob(".qr_*.png"))  # temp files cleaned up
