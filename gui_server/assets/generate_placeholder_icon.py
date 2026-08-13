"""
One-off generator for the AegisVision placeholder app icon.

No real artwork is available in this environment, so this draws a simple
geometric mark (a shield -- "Aegis" -- with an eye cut into it -- "Vision")
in the app's antique-gold / deep-forest palette, and exports it as both
icon.ico (multi-resolution, for Windows taskbar/title bar) and icon.png
(for the cross-platform iconphoto() fallback).

This is a PLACEHOLDER. Swap it out any time by replacing assets/icon.ico
and assets/icon.png with real artwork of the same filenames -- no code
changes are needed elsewhere, main_window.py always loads those two names.

Run manually to regenerate: python assets/generate_placeholder_icon.py
"""

import os
from PIL import Image, ImageDraw

FOREST = (15, 26, 20, 255)     # #0f1a14
GOLD = (198, 167, 94, 255)     # #c6a75e
TRANSPARENT = (0, 0, 0, 0)

SIZE = 256


def draw_mark() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), TRANSPARENT)
    draw = ImageDraw.Draw(img)

    # Deep-forest disc background
    margin = 6
    draw.ellipse(
        [margin, margin, SIZE - margin, SIZE - margin],
        fill=FOREST,
    )

    # Gold shield ("Aegis")
    cx = SIZE / 2
    shield = [
        (cx, 52),
        (SIZE - 66, 82),
        (SIZE - 66, 140),
        (cx, 212),
        (66, 140),
        (66, 82),
    ]
    draw.polygon(shield, fill=GOLD)

    # Forest eye cut into the shield ("Vision")
    eye_w, eye_h = 92, 46
    eye_cy = 128
    draw.ellipse(
        [cx - eye_w / 2, eye_cy - eye_h / 2, cx + eye_w / 2, eye_cy + eye_h / 2],
        fill=FOREST,
    )

    # Gold pupil
    pupil_r = 15
    draw.ellipse(
        [cx - pupil_r, eye_cy - pupil_r, cx + pupil_r, eye_cy + pupil_r],
        fill=GOLD,
    )

    return img


def main():
    out_dir = os.path.dirname(os.path.abspath(__file__))
    icon = draw_mark()

    png_path = os.path.join(out_dir, "icon.png")
    icon.save(png_path, format="PNG")

    ico_path = os.path.join(out_dir, "icon.ico")
    icon.save(
        ico_path,
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48), (256, 256)],
    )

    print(f"Wrote {png_path}")
    print(f"Wrote {ico_path}")


if __name__ == "__main__":
    main()
