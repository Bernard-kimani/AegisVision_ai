"""
StrategySlotCard - one card for a single template slot (bullish_ideal /
bearish_ideal / fail_trap) within the Strategies tab.

Read-only by default (composite thumbnail + caption text); its own
"Configure" button reveals up to 4 sub-image boxes (each individually
uploadable/re-croppable/removable) plus an editable caption, per the
per-section configure-to-edit pattern the Strategies page uses throughout.

Expects `store` to be a concrete LocalFileTemplateImageStore for whichever
strategy is currently open in the GUI (not the ActiveStrategyTemplateStore
decorator, which is a live-pipeline-process concern) -- this widget reads
`store.storage_dir` directly to resolve preview image paths.
"""

import os
from tkinter import filedialog, messagebox

import customtkinter as ctk
from PIL import Image

from gui.theme import colors, fonts, spacing
from gui.theme.layout import card
from gui.widgets.crop_dialog import CropDialog
from storage import template_compositor
from storage.template_image_store import MAX_SOURCES_PER_SLOT

SLOT_LABELS = {
    "bullish_ideal": "Bullish Ideal Setup",
    "bearish_ideal": "Bearish Ideal Setup",
    "fail_trap": "Fail / Trap Setup (to avoid)",
}

COMPOSITE_PREVIEW = (180, 180)
SOURCE_THUMB = (90, 90)


class StrategySlotCard:
    def __init__(self, parent, slot: str, store, status_callback):
        self.slot = slot
        self.store = store
        self.status_callback = status_callback
        self._configuring = False
        self._image_refs = []  # keep CTkImage references alive

        self.frame = card(parent)
        self.frame.pack(fill="x", pady=(0, spacing.SM))

        self._build_static_chrome()
        self._render_read_only()

    def _build_static_chrome(self):
        header_row = ctk.CTkFrame(self.frame, fg_color="transparent")
        header_row.pack(fill="x", padx=spacing.MD, pady=(spacing.MD, spacing.XS))
        ctk.CTkLabel(header_row, text=SLOT_LABELS.get(self.slot, self.slot), font=fonts.section()).pack(side="left")
        self.configure_btn = ctk.CTkButton(header_row, text="Configure", width=100, command=self._toggle_configure)
        self.configure_btn.pack(side="right")

        self.body = ctk.CTkFrame(self.frame, fg_color="transparent")
        self.body.pack(fill="x", padx=spacing.MD, pady=(0, spacing.MD))

    def _clear_body(self):
        for w in self.body.winfo_children():
            w.destroy()
        self._image_refs.clear()

    def refresh(self):
        """Called by the owning tab after the underlying store instance changes
        (e.g. switching strategies) so this card re-reads from the new store."""
        self._configuring = False
        self.configure_btn.configure(text="Configure")
        self._render_read_only()

    def _toggle_configure(self):
        self._configuring = not self._configuring
        self.configure_btn.configure(text="Done" if self._configuring else "Configure")
        if self._configuring:
            self._render_editable()
        else:
            self._render_read_only()

    # -- read-only view ------------------------------------------------

    def _render_read_only(self):
        self._clear_body()
        record = self.store.get_template(self.slot)

        preview = ctk.CTkLabel(
            self.body, text="No image uploaded" if not record else "",
            text_color=colors.TEXT_SECONDARY, width=COMPOSITE_PREVIEW[0], height=COMPOSITE_PREVIEW[1],
        )
        preview.pack(side="left", padx=(0, spacing.MD))
        if record:
            self._set_preview_image(preview, os.path.join(self.store.storage_dir, record.filename), COMPOSITE_PREVIEW)

        caption_text = record.caption if record and record.caption else "No caption yet."
        ctk.CTkLabel(
            self.body, text=caption_text, text_color=colors.TEXT_SECONDARY, font=fonts.caption(),
            justify="left", wraplength=260, anchor="nw",
        ).pack(side="left", fill="both", expand=True, anchor="n")

    # -- editable view -------------------------------------------------

    def _render_editable(self):
        self._clear_body()

        boxes_row = ctk.CTkFrame(self.body, fg_color="transparent")
        boxes_row.pack(fill="x", pady=(0, spacing.SM))
        sources = {s.position: s for s in self.store.get_template_sources(self.slot)}
        for position in range(MAX_SOURCES_PER_SLOT):
            self._build_sub_box(boxes_row, position, sources.get(position))

        record = self.store.get_template(self.slot)
        ctk.CTkLabel(self.body, text="Caption:", font=fonts.caption(), text_color=colors.TEXT_SECONDARY, anchor="w").pack(fill="x")
        self.caption_box = ctk.CTkTextbox(self.body, height=60)
        self.caption_box.pack(fill="x", pady=(spacing.XS, spacing.SM))
        if record and record.caption:
            self.caption_box.insert("1.0", record.caption)

        ctk.CTkButton(self.body, text="Save Caption", command=self._on_save_caption, width=130).pack(anchor="w")

    def _build_sub_box(self, parent, position, source):
        box = card(parent, padding=spacing.XS)
        box.grid(row=position // 2, column=position % 2, padx=spacing.XS, pady=spacing.XS)

        thumb = ctk.CTkLabel(
            box, text="+ Add" if not source else "", text_color=colors.TEXT_SECONDARY,
            width=SOURCE_THUMB[0], height=SOURCE_THUMB[1],
        )
        thumb.pack(padx=spacing.XS, pady=spacing.XS)
        if source:
            self._set_preview_image(
                thumb, os.path.join(self.store.storage_dir, source.filename), SOURCE_THUMB,
                crop_box=(source.crop_x, source.crop_y, source.crop_w, source.crop_h),
            )
        thumb.bind("<Button-1>", lambda e, p=position, s=source: self._on_box_click(p, s))

        if source:
            ctk.CTkButton(
                box, text="Remove", width=SOURCE_THUMB[0], height=22,
                fg_color=colors.SURFACE_ALT, hover_color=colors.SURFACE_ALT,
                command=lambda p=position: self._on_remove(p),
            ).pack(padx=spacing.XS, pady=(0, spacing.XS))

    def _on_box_click(self, position, existing_source):
        if existing_source is not None:
            # re-edit: reopen the crop tool on the already-saved source, no file picker
            path = os.path.join(self.store.storage_dir, existing_source.filename)
        else:
            path = filedialog.askopenfilename(
                title=f"Choose image {position + 1} for {SLOT_LABELS.get(self.slot, self.slot)}",
                filetypes=[("Image files", "*.png *.jpg *.jpeg"), ("All files", "*.*")],
            )
            if not path:
                return

        current_count = len(self.store.get_template_sources(self.slot))
        count_after = current_count if existing_source else current_count + 1
        aspect = template_compositor.cell_aspect_ratio(min(max(count_after, 1), 4), position)
        initial_crop = (
            (existing_source.crop_x, existing_source.crop_y, existing_source.crop_w, existing_source.crop_h)
            if existing_source else None
        )

        try:
            dialog = CropDialog(self.frame, path, aspect, initial_crop)
        except Exception as e:
            messagebox.showerror("Error", f"Could not open image: {e}")
            return
        self.frame.wait_window(dialog)
        if dialog.result is None:
            return

        r = dialog.result
        try:
            self.store.save_template_source(self.slot, position, path, (r.crop_x, r.crop_y, r.crop_w, r.crop_h))
            self.status_callback(f"Saved image {position + 1} for '{SLOT_LABELS.get(self.slot, self.slot)}'")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save image: {e}")
            return
        self._render_editable()

    def _on_remove(self, position):
        self.store.remove_template_source(self.slot, position)
        self.status_callback(f"Removed image {position + 1} from '{SLOT_LABELS.get(self.slot, self.slot)}'")
        self._render_editable()

    def _on_save_caption(self):
        caption = self.caption_box.get("1.0", "end").strip()
        record = self.store.update_caption(self.slot, caption)
        if record is None:
            messagebox.showwarning("No Image Yet", "Upload at least one image for this slot before saving a caption.")
            return
        self.status_callback(f"Caption updated for '{SLOT_LABELS.get(self.slot, self.slot)}'")

    # -- helpers ---------------------------------------------------------

    def _set_preview_image(self, label_widget, image_path, size, crop_box=None):
        try:
            if not os.path.exists(image_path):
                return
            img = Image.open(image_path).convert("RGB")
            if crop_box:
                w, h = img.size
                cx, cy, cw, ch = crop_box
                box = (int(cx * w), int(cy * h), int((cx + cw) * w), int((cy + ch) * h))
                img = img.crop(box)
            img.thumbnail(size)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
            label_widget.configure(image=ctk_img, text="")
            label_widget.image = ctk_img
            self._image_refs.append(ctk_img)
        except Exception:
            pass
