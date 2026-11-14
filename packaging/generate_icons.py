"""Generate MePDF application icons (.png, .ico for Windows, .icns for macOS) using Pillow."""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def draw_mepdf_icon(size: int = 512) -> Image.Image:
    """Render a modern vector-style MePDF icon at the given square pixel resolution."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded cobalt/indigo gradient-style background card
    pad = int(size * 0.06)
    radius = int(size * 0.22)
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=radius,
        fill=(30, 64, 175, 255),
        outline=(59, 130, 246, 255),
        width=max(2, int(size * 0.015)),
    )

    # Inner document sheet with folded top-right corner
    doc_l = int(size * 0.22)
    doc_t = int(size * 0.16)
    doc_r = int(size * 0.78)
    doc_b = int(size * 0.84)
    fold = int(size * 0.14)

    doc_points = [
        (doc_l, doc_t),
        (doc_r - fold, doc_t),
        (doc_r, doc_t + fold),
        (doc_r, doc_b),
        (doc_l, doc_b),
    ]
    draw.polygon(doc_points, fill=(255, 255, 255, 255))

    # Folded corner triangle
    fold_points = [
        (doc_r - fold, doc_t),
        (doc_r - fold, doc_t + fold),
        (doc_r, doc_t + fold),
    ]
    draw.polygon(fold_points, fill=(191, 219, 254, 255))

    # Yellow smart-highlight bar on the document
    hl_l = int(size * 0.29)
    hl_r = int(size * 0.66)
    hl_t = int(size * 0.34)
    hl_b = int(size * 0.40)
    draw.rounded_rectangle(
        [hl_l, hl_t, hl_r, hl_b],
        radius=max(2, int(size * 0.015)),
        fill=(250, 204, 21, 255),
    )

    # Simulated text lines
    line_color = (51, 65, 85, 255)
    for y_frac, w_frac in [(0.45, 0.42), (0.52, 0.34)]:
        y = int(size * y_frac)
        h = max(3, int(size * 0.025))
        draw.rounded_rectangle(
            [hl_l, y, hl_l + int(size * w_frac), y + h],
            radius=max(1, h // 2),
            fill=line_color,
        )

    # Crimson "PDF" badge banner across bottom of sheet
    badge_l = int(size * 0.16)
    badge_r = int(size * 0.84)
    badge_t = int(size * 0.61)
    badge_b = int(size * 0.79)
    draw.rounded_rectangle(
        [badge_l, badge_t, badge_r, badge_b],
        radius=max(4, int(size * 0.04)),
        fill=(220, 38, 38, 255),
    )

    # Draw "MePDF" text inside the crimson banner
    font_size = max(12, int(size * 0.115))
    try:
        font = ImageFont.truetype("arialbd.ttf", font_size)
    except Exception:
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

    label = "MePDF"
    bbox = draw.textbbox((0, 0), label, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (size - tw) / 2 - bbox[0]
    ty = badge_t + ((badge_b - badge_t) - th) / 2 - bbox[1]
    draw.text((tx, ty), label, fill=(255, 255, 255, 255), font=font)

    return img


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    assets_dir = root / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    master = draw_mepdf_icon(512)
    png_path = assets_dir / "mepdf.png"
    ico_path = assets_dir / "mepdf.ico"
    icns_path = assets_dir / "mepdf.icns"

    master.save(png_path, format="PNG")
    master.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    master.save(icns_path, format="ICNS")
    print(f"Generated icons in {assets_dir}:")
    print(f" - {png_path.name} ({png_path.stat().st_size} bytes)")
    print(f" - {ico_path.name} ({ico_path.stat().st_size} bytes)")
    print(f" - {icns_path.name} ({icns_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
