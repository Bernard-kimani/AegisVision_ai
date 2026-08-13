"""
Procedurally-drawn icon set, replacing emoji glyphs with simple monochrome
vector-style marks (matches the approach used for assets/icon.ico -- no
external icon library or network connection needed).

Icons drawn for buttons that sit on a fixed-color background (Start/Stop/
Restart/Health Check use SUCCESS/ERROR/WARNING/ACCENT fills, which are the
same tone in both light and dark mode) use a single fixed dark stroke color
matching the button's default text_color. Icons that sit directly on the
"ground" (e.g. the header profile icon) are drawn twice and passed as
(light_image, dark_image) so they stay visible in both appearance modes.

Each function returns a ready-to-use ctk.CTkImage.
"""

import customtkinter as ctk
from PIL import Image, ImageDraw

from . import tokens as colors

_CANVAS = 128
_STROKE = 11

# Fixed dark stroke used on colored button backgrounds (matches CTkButton's
# default text_color, which is TEXT_ON_ACCENT and is intentionally the same
# tone in both light and dark mode).
_BUTTON_STROKE = (18, 18, 18, 255)


def _canvas():
    img = Image.new("RGBA", (_CANVAS, _CANVAS), (0, 0, 0, 0))
    return img, ImageDraw.Draw(img)


def _finish(img, size):
    return img.resize((size, size), Image.LANCZOS)


def _button_image(draw_fn, size=18):
    """Icon for use on a colored button (single fixed dark stroke, same in
    both appearance modes since the button's own background doesn't change)."""
    img, d = _canvas()
    draw_fn(d, _BUTTON_STROKE)
    icon = _finish(img, size)
    return ctk.CTkImage(light_image=icon, dark_image=icon, size=(size, size))


def _ground_image(draw_fn, size=20):
    """Icon for use directly on the window background -- drawn once per
    mode so it stays visible against both the light and dark ground color."""
    light_img, ld = _canvas()
    draw_fn(ld, (15, 26, 20, 255))  # dark stroke for the light background
    dark_img, dd = _canvas()
    draw_fn(dd, (243, 237, 230, 255))  # light stroke for the dark background
    return ctk.CTkImage(
        light_image=_finish(light_img, size),
        dark_image=_finish(dark_img, size),
        size=(size, size),
    )


# ---------------------------------------------------------------------
# Glyph drawers
# ---------------------------------------------------------------------

def _draw_play(d: ImageDraw.ImageDraw, color):
    d.polygon([(40, 24), (40, 104), (104, 64)], fill=color)


def _draw_stop(d: ImageDraw.ImageDraw, color):
    d.rounded_rectangle([32, 32, 96, 96], radius=14, fill=color)


def _draw_restart(d: ImageDraw.ImageDraw, color):
    bbox = [18, 18, 110, 110]
    d.arc(bbox, start=20, end=300, fill=color, width=_STROKE)
    # arrowhead at the start of the arc (~20deg position)
    d.polygon([(96, 30), (112, 40), (94, 52)], fill=color)


def _draw_health(d: ImageDraw.ImageDraw, color):
    d.ellipse([14, 14, 114, 114], outline=color, width=_STROKE)
    d.line([(40, 66), (58, 84), (92, 44)], fill=color, width=_STROKE, joint="curve")


def _draw_download(d: ImageDraw.ImageDraw, color):
    d.line([(64, 16), (64, 78)], fill=color, width=_STROKE)
    d.polygon([(38, 56), (90, 56), (64, 86)], fill=color)
    d.line([(20, 108), (108, 108)], fill=color, width=_STROKE)


def _draw_folder(d: ImageDraw.ImageDraw, color):
    d.polygon([(16, 40), (50, 40), (60, 54), (112, 54), (112, 100), (16, 100)], outline=color, width=_STROKE)


def _draw_chart(d: ImageDraw.ImageDraw, color):
    d.rectangle([22, 74, 44, 108], fill=color)
    d.rectangle([54, 52, 76, 108], fill=color)
    d.rectangle([86, 30, 108, 108], fill=color)


def _draw_profile(d: ImageDraw.ImageDraw, color):
    d.ellipse([44, 20, 84, 60], outline=color, width=_STROKE)
    d.arc([22, 66, 106, 150], start=200, end=340, fill=color, width=_STROKE)


def _draw_close(d: ImageDraw.ImageDraw, color):
    d.line([(30, 30), (98, 98)], fill=color, width=_STROKE)
    d.line([(98, 30), (30, 98)], fill=color, width=_STROKE)


# ---------------------------------------------------------------------
# Public icon factories
# ---------------------------------------------------------------------

def play_icon(size=18):
    return _button_image(_draw_play, size)


def stop_icon(size=18):
    return _button_image(_draw_stop, size)


def restart_icon(size=18):
    return _button_image(_draw_restart, size)


def health_icon(size=18):
    return _button_image(_draw_health, size)


def download_icon(size=16):
    return _button_image(_draw_download, size)


def folder_icon(size=16):
    return _button_image(_draw_folder, size)


def chart_icon(size=16):
    return _button_image(_draw_chart, size)


def profile_icon(size=22):
    return _ground_image(_draw_profile, size)


def close_icon(size=16):
    return _ground_image(_draw_close, size)
