"""QR labels for assets (UI-023, P1): one PNG per asset code, printable A4 sheet."""
from __future__ import annotations

from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont


def write_qr_png(code: str, target: Path, box: int = 8) -> Path:
    qr = qrcode.QRCode(version=None, box_size=box, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(code)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#11345A", back_color="white").convert("RGB")
    target.parent.mkdir(parents=True, exist_ok=True)
    image.save(target, "PNG")
    return target


def write_sheet(items: list[tuple[str, str]], target: Path, columns: int = 4) -> Path:
    """A4-ish sheet: QR + code + name per cell. `items` = [(code, name)]."""
    cell_w, cell_h, margin = 420, 300, 40
    rows = max(1, (len(items) + columns - 1) // columns)
    sheet = Image.new("RGB", (columns * cell_w + margin, rows * cell_h + margin), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.load_default()
    except OSError:  # pragma: no cover
        font = None
    for index, (code, name) in enumerate(items):
        x = margin + (index % columns) * cell_w
        y = margin + (index // columns) * cell_h
        tmp = target.parent / f".qr_{index}.png"
        write_qr_png(code, tmp, box=5)
        qr_img = Image.open(tmp)
        sheet.paste(qr_img, (x, y))
        tmp.unlink(missing_ok=True)
        draw.rectangle([x - 4, y - 4, x + qr_img.width + 4, y + qr_img.height + 4],
                       outline="#C9D4E1")
        if font is not None:
            draw.text((x, y + qr_img.height + 10), f"{code}", fill="#11345A", font=font)
            if name.isascii():  # Pillow here cannot shape Arabic: never print it garbled
                draw.text((x, y + qr_img.height + 28), name[:38], fill="#162B43", font=font)
    target.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(target, "PNG")
    return target


PER_PAGE = 24  # 4 x 6 labels on an A4 page


def write_sheets(items: list[tuple[str, str]], target: Path) -> list[Path]:
    """Every item, PER_PAGE labels per page: target.png, target_2.png, … (review F-16)."""
    pages = [items[i:i + PER_PAGE] for i in range(0, len(items), PER_PAGE)] or [[]]
    paths = []
    for number, page in enumerate(pages, start=1):
        out = target if number == 1 else target.with_name(f"{target.stem}_{number}{target.suffix}")
        paths.append(write_sheet(page, out))
    return paths
