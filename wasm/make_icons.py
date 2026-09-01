"""Generate the PWA icons (SPEC.md 14).

Kept as a script rather than four opaque binaries so the shapes stay reviewable and a colour
change is a one-line diff. Run it when the icons need to change; the PNGs it writes are
committed, because the Pages workflow installs jinja2 and nothing else.

    python wasm/make_icons.py

The maskable pair carries the ~20 % safe-zone padding Android's mask expects. Without it the
mask crops the glyph's edges and the installed icon looks broken.
"""

from __future__ import annotations

from pathlib import Path
from typing import Final

from PIL import Image, ImageDraw, ImageFont

HERE: Final = Path(__file__).resolve().parent
BACKGROUND: Final = (255, 75, 75)  # Streamlit's red, matching theme_color in the manifest
FOREGROUND: Final = (255, 255, 255)
GLYPH: Final = "dp"


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """A bold sans face at ``size``, falling back to Pillow's bitmap font."""
    for candidate in ("/System/Library/Fonts/Helvetica.ttc", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    return ImageFont.load_default()


def draw(size: int, *, maskable: bool) -> Image.Image:
    """One icon: the glyph centred on a solid ground, inset when it has to survive a mask."""
    image = Image.new("RGBA", (size, size), (*BACKGROUND, 255))
    canvas = ImageDraw.Draw(image)
    if not maskable:
        # A rounded square reads as an app icon where nothing else masks it for us.
        rounded = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        ImageDraw.Draw(rounded).rounded_rectangle(
            (0, 0, size - 1, size - 1), radius=size // 5, fill=(*BACKGROUND, 255)
        )
        image = rounded
        canvas = ImageDraw.Draw(image)

    safe = 0.6 if maskable else 0.72  # the fraction of the icon the glyph may occupy
    font = _font(int(size * safe * 0.7))
    box = canvas.textbbox((0, 0), GLYPH, font=font)
    canvas.text(
        ((size - box[2] - box[0]) / 2, (size - box[3] - box[1]) / 2),
        GLYPH,
        font=font,
        fill=(*FOREGROUND, 255),
    )
    return image


def main() -> int:
    """Write the four icons into ``wasm/static``.

    Returns:
        A process exit code.
    """
    out = HERE / "static"
    out.mkdir(parents=True, exist_ok=True)
    for size in (192, 512):
        for maskable in (False, True):
            name = f"icon-{size}-maskable.png" if maskable else f"icon-{size}.png"
            draw(size, maskable=maskable).save(out / name)
            print("wrote", (out / name).relative_to(HERE.parent))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
