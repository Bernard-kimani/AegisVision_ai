"""
Stitches 1-4 curated example images into a single composite per template slot
(bullish_ideal/bearish_ideal/fail_trap). This keeps the live pipeline seeing
exactly one image per slot (see template_image_store.py's TemplateRecord /
get_template_base64, consumed by server/agents/vision_compliance.py) while
the Strategies tab lets a user curate up to 4 examples for that one slot.

This module is a pure function over in-memory PIL images -- no disk I/O, no
knowledge of where sources/composites live on disk (that's
LocalFileTemplateImageStore's job).
"""

from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

CANVAS_SIZE = (1024, 768)  # 4:3 -- matches the JPEG the composite is saved as
GUTTER = 6
GUTTER_COLOR = (128, 128, 128)
NUMERAL_BADGE_COLOR = (0, 0, 0)
NUMERAL_TEXT_COLOR = (255, 255, 255)

_W, _H = CANVAS_SIZE
_HALF_W = (_W - 3 * GUTTER) // 2
_HALF_H = (_H - 3 * GUTTER) // 2

# One cell per possible sub-image position (0-3), keyed by how many images
# the slot currently holds. Cells are filled in position order. Width and
# height halves are computed independently since the canvas isn't square --
# reusing one "_HALF" for both axes (as a square canvas would allow) would
# distort every multi-image layout.
CELL_LAYOUTS = {
    1: [
        (GUTTER, GUTTER, _W - 2 * GUTTER, _H - 2 * GUTTER),
    ],
    2: [
        (GUTTER, GUTTER, _HALF_W, _H - 2 * GUTTER),
        (GUTTER + _HALF_W + GUTTER, GUTTER, _HALF_W, _H - 2 * GUTTER),
    ],
    3: [
        (GUTTER, GUTTER, _W - 2 * GUTTER, _HALF_H),
        (GUTTER, GUTTER + _HALF_H + GUTTER, _HALF_W, _HALF_H),
        (GUTTER + _HALF_W + GUTTER, GUTTER + _HALF_H + GUTTER, _HALF_W, _HALF_H),
    ],
    4: [
        (GUTTER, GUTTER, _HALF_W, _HALF_H),
        (GUTTER + _HALF_W + GUTTER, GUTTER, _HALF_W, _HALF_H),
        (GUTTER, GUTTER + _HALF_H + GUTTER, _HALF_W, _HALF_H),
        (GUTTER + _HALF_W + GUTTER, GUTTER + _HALF_H + GUTTER, _HALF_W, _HALF_H),
    ],
}


def cell_aspect_ratio(count: int, index: int) -> float:
    """width/height of the cell a sub-image at display order `index` (0-based,
    NOT the stored `position`) will land in for a slot holding `count` images
    total -- used to lock the crop tool's aspect ratio to the eventual
    composite cell shape."""
    layout = CELL_LAYOUTS.get(max(1, min(count, 4)), CELL_LAYOUTS[4])
    _, _, w, h = layout[min(index, len(layout) - 1)]
    return w / h


def composite_slot_images(cropped_sources: List[Tuple[Image.Image, int]]) -> Image.Image:
    """cropped_sources: list of (already-cropped PIL Image, position 0-3), in
    any order, any subset of the 4 positions present (1-4 items -- gaps in
    position numbering are fine, e.g. positions 0 and 2 populated composites
    as a 2-image layout packed in position order). Returns the final
    composite ready to be saved as the slot's composite.png."""
    if not cropped_sources:
        raise ValueError("composite_slot_images requires at least one image")

    ordered = sorted(cropped_sources, key=lambda pair: pair[1])
    layout = CELL_LAYOUTS.get(max(1, min(len(ordered), 4)), CELL_LAYOUTS[4])

    canvas = Image.new("RGB", CANVAS_SIZE, GUTTER_COLOR)  # RGB, not RGBA -- required for JPEG output
    draw = ImageDraw.Draw(canvas)

    for index, (img, _position) in enumerate(ordered):
        x, y, w, h = layout[min(index, len(layout) - 1)]
        resized = img.convert("RGB").resize((w, h), Image.LANCZOS)
        canvas.paste(resized, (x, y))
        if len(ordered) > 1:
            _draw_numeral(draw, index + 1, x, y)

    return canvas


def _draw_numeral(draw: ImageDraw.ImageDraw, n: int, x: int, y: int):
    """Small numbered badge in each cell's top-left corner -- keeps a caption
    that references "images 1-2 vs 3-4" disambiguated once stitched."""
    pad = 8
    size = 24
    draw.rectangle([x + pad, y + pad, x + pad + size, y + pad + size], fill=NUMERAL_BADGE_COLOR)
    try:
        font = ImageFont.load_default()
    except Exception:
        font = None
    draw.text((x + pad + 8, y + pad + 5), str(n), fill=NUMERAL_TEXT_COLOR, font=font)
