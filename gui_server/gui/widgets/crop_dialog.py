"""
CropDialog - a modal crop-selection tool for a template sub-image.

CustomTkinter has no native crop/drawing widget; the standard approach is to
embed a raw tkinter.Canvas inside a CTkToplevel and draw the image plus a
draggable/resizable rectangle ourselves. That's what this is.

Usage (standard Tk modal pattern):
    dialog = CropDialog(parent, source_path, target_aspect_ratio, initial_crop)
    parent.wait_window(dialog)
    if dialog.result is not None:
        ...  # dialog.result is a CropResult
"""

import tkinter as tk
from typing import NamedTuple, Optional, Tuple

import customtkinter as ctk
from PIL import Image, ImageTk

from gui.theme import colors, spacing

MAX_PREVIEW = 700
HANDLE_SIZE = 10
MIN_RECT_PX = 40

# handle index -> (x_side, y_side): which direction the dragged (free) corner
# moves relative to the fixed anchor corner (the opposite one).
_HANDLE_SIDES = {0: (-1, -1), 1: (1, -1), 2: (-1, 1), 3: (1, 1)}


def _anchor_for(handle_index: int, x0: float, y0: float, x1: float, y1: float) -> Tuple[float, float]:
    return {0: (x1, y1), 1: (x0, y1), 2: (x1, y0), 3: (x0, y0)}[handle_index]


class CropResult(NamedTuple):
    crop_x: float
    crop_y: float
    crop_w: float
    crop_h: float
    source_width: int
    source_height: int


class CropDialog(ctk.CTkToplevel):
    def __init__(
        self, parent, source_image_path: str, target_aspect_ratio: float,
        initial_crop: Optional[Tuple[float, float, float, float]] = None,
    ):
        super().__init__(parent)
        self.title("Crop Image")
        self.result: Optional[CropResult] = None
        self.target_aspect_ratio = max(0.1, target_aspect_ratio)

        source = Image.open(source_image_path).convert("RGB")
        self.source_width, self.source_height = source.size

        scale = min(MAX_PREVIEW / self.source_width, MAX_PREVIEW / self.source_height, 1.0)
        self.preview_w = max(1, int(self.source_width * scale))
        self.preview_h = max(1, int(self.source_height * scale))
        preview_img = source.resize((self.preview_w, self.preview_h), Image.LANCZOS)
        self._tk_image = ImageTk.PhotoImage(preview_img)

        self.resizable(False, False)

        self.canvas = tk.Canvas(
            self, width=self.preview_w, height=self.preview_h,
            highlightthickness=0, bg="#1a1a1a",
        )
        self.canvas.pack(padx=spacing.LG, pady=(spacing.LG, spacing.SM))
        self.canvas.create_image(0, 0, anchor="nw", image=self._tk_image)

        self.rect = list(self._initial_rect(initial_crop))
        self._rect_id = self.canvas.create_rectangle(*self.rect, outline="#c6a75e", width=2)
        self._handle_ids = [
            self.canvas.create_rectangle(0, 0, 0, 0, fill="#c6a75e", outline="") for _ in range(4)
        ]
        self._redraw()

        self._drag_mode = None  # "move" or a handle index (0-3)
        self._drag_start = None
        self._drag_rect_start = None

        self.canvas.tag_bind(self._rect_id, "<Button-1>", self._on_body_press)
        self.canvas.tag_bind(self._rect_id, "<B1-Motion>", self._on_drag)
        self.canvas.tag_bind(self._rect_id, "<ButtonRelease-1>", self._on_release)
        for i, hid in enumerate(self._handle_ids):
            self.canvas.tag_bind(hid, "<Button-1>", lambda e, idx=i: self._on_handle_press(e, idx))
            self.canvas.tag_bind(hid, "<B1-Motion>", self._on_drag)
            self.canvas.tag_bind(hid, "<ButtonRelease-1>", self._on_release)

        button_row = ctk.CTkFrame(self, fg_color="transparent")
        button_row.pack(pady=(0, spacing.LG))
        ctk.CTkButton(button_row, text="Apply", command=self._on_apply, width=120).pack(side="left", padx=(0, spacing.SM))
        ctk.CTkButton(
            button_row, text="Cancel", command=self._on_cancel, width=120,
            fg_color=colors.SURFACE_ALT, hover_color=colors.SURFACE_ALT,
        ).pack(side="left")

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.transient(parent)
        self.grab_set()

    def _initial_rect(self, initial_crop):
        if initial_crop:
            cx, cy, cw, ch = initial_crop
            return (
                cx * self.preview_w, cy * self.preview_h,
                (cx + cw) * self.preview_w, (cy + ch) * self.preview_h,
            )
        # best-fit rectangle at the target aspect ratio, centered
        if self.preview_w / self.preview_h > self.target_aspect_ratio:
            rh = self.preview_h
            rw = rh * self.target_aspect_ratio
        else:
            rw = self.preview_w
            rh = rw / self.target_aspect_ratio
        x0 = (self.preview_w - rw) / 2
        y0 = (self.preview_h - rh) / 2
        return (x0, y0, x0 + rw, y0 + rh)

    def _redraw(self):
        x0, y0, x1, y1 = self.rect
        corners = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
        for hid, (cx, cy) in zip(self._handle_ids, corners):
            self.canvas.coords(hid, cx - HANDLE_SIZE / 2, cy - HANDLE_SIZE / 2, cx + HANDLE_SIZE / 2, cy + HANDLE_SIZE / 2)
        self.canvas.coords(self._rect_id, *self.rect)

    def _on_body_press(self, event):
        self._drag_mode = "move"
        self._drag_start = (event.x, event.y)
        self._drag_rect_start = list(self.rect)

    def _on_handle_press(self, event, idx):
        self._drag_mode = idx
        self._drag_start = (event.x, event.y)
        self._drag_rect_start = list(self.rect)

    def _on_drag(self, event):
        if self._drag_mode is None:
            return
        x0, y0, x1, y1 = self._drag_rect_start

        if self._drag_mode == "move":
            dx = event.x - self._drag_start[0]
            dy = event.y - self._drag_start[1]
            w, h = x1 - x0, y1 - y0
            nx0 = min(max(0, x0 + dx), self.preview_w - w)
            ny0 = min(max(0, y0 + dy), self.preview_h - h)
            self.rect = [nx0, ny0, nx0 + w, ny0 + h]
        else:
            idx = self._drag_mode
            x_side, y_side = _HANDLE_SIDES[idx]
            ax, ay = _anchor_for(idx, x0, y0, x1, y1)

            new_w = max(MIN_RECT_PX, abs(event.x - ax))
            new_w = min(new_w, (self.preview_w - ax) if x_side == 1 else ax)
            new_h = new_w / self.target_aspect_ratio

            max_h = (self.preview_h - ay) if y_side == 1 else ay
            if new_h > max_h > 0:
                new_h = max_h
                new_w = new_h * self.target_aspect_ratio

            free_x = ax + x_side * new_w
            free_y = ay + y_side * new_h
            self.rect = [min(ax, free_x), min(ay, free_y), max(ax, free_x), max(ay, free_y)]

        self._redraw()

    def _on_release(self, event):
        self._drag_mode = None

    def _on_apply(self):
        x0, y0, x1, y1 = self.rect
        self.result = CropResult(
            crop_x=x0 / self.preview_w, crop_y=y0 / self.preview_h,
            crop_w=(x1 - x0) / self.preview_w, crop_h=(y1 - y0) / self.preview_h,
            source_width=self.source_width, source_height=self.source_height,
        )
        self.grab_release()
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.grab_release()
        self.destroy()
