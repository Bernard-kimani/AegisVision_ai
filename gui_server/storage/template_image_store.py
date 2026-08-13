"""
TemplateImageStore - storage for the Agent 2 "gold standard" template images
(ideal bullish setup, ideal bearish setup, ideal fail/trap setup).

Each slot can hold 1-4 curated sub-images (see TemplateSourceImage), stitched
by template_compositor.py into a single composite.png -- that composite is
what get_template()/get_template_base64() expose, so vision_compliance.py
(and any future consumer) is completely unaware sub-images/compositing exist
at all; it only ever sees "one image per slot," exactly as before.

Local-file implementation for v1: PNGs + a metadata JSON sidecar. A future
Supabase implementation (Storage bucket + rows) would implement the same
interface with zero change to consumers.
"""

import base64
import json
import os
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PIL import Image

from . import template_compositor

# Fixed slots the vision-compliance prompt expects. Not user-extensible in v1 -
# the 2-shot (well, 3-image) design is a specific prompt structure, not an
# arbitrary gallery.
TEMPLATE_SLOTS = ("bullish_ideal", "bearish_ideal", "fail_trap")

MAX_SOURCES_PER_SLOT = 4


@dataclass
class TemplateRecord:
    slot: str
    filename: str  # path relative to storage_dir, e.g. "bullish_ideal/composite.png"
    caption: str
    updated_at: str = ""


@dataclass
class TemplateSourceImage:
    slot: str
    position: int  # 0-3, which of the up-to-4 thumbnail boxes
    filename: str  # path relative to storage_dir, e.g. "bullish_ideal/sources/0.png"
    crop_x: float  # normalized 0..1 fractions of the source image
    crop_y: float
    crop_w: float
    crop_h: float
    source_width: int
    source_height: int
    updated_at: str = ""


class TemplateImageStore(ABC):
    @abstractmethod
    def save_template(self, slot: str, source_image_path: str, caption: str) -> TemplateRecord:
        """Convenience shortcut: single whole-image upload at position 0.
        Equivalent to save_template_source(slot, 0, source_image_path, (0,0,1,1), caption)."""

    @abstractmethod
    def save_template_source(
        self, slot: str, position: int, source_image_path: str,
        crop_box: Tuple[float, float, float, float], caption: Optional[str] = None,
    ) -> TemplateRecord:
        """Save/replace the sub-image at `position` (0-3) with its normalized
        crop rectangle (x, y, w, h fractions of the source image), recomposite
        the slot's composite.png from all its current sub-images, and return
        the updated TemplateRecord for the slot."""

    @abstractmethod
    def get_template_sources(self, slot: str) -> List[TemplateSourceImage]:
        """List this slot's sub-images (for the crop tool's re-edit path)."""

    @abstractmethod
    def remove_template_source(self, slot: str, position: int) -> Optional[TemplateRecord]:
        """Remove one sub-image and recomposite the remainder. Returns None
        if the slot has no image left after removal."""

    @abstractmethod
    def get_template(self, slot: str) -> Optional[TemplateRecord]:
        """Get metadata for a slot's template, or None if not yet uploaded."""

    @abstractmethod
    def get_template_base64(self, slot: str) -> Optional[str]:
        """Get the raw image bytes for a slot, base64-encoded, ready for an LLM request."""

    @abstractmethod
    def list_templates(self) -> Dict[str, TemplateRecord]:
        """Get metadata for every slot that has an uploaded template."""

    @abstractmethod
    def update_caption(self, slot: str, caption: str) -> Optional[TemplateRecord]:
        """Update a slot's caption without re-uploading its image. Returns None if
        the slot has no image yet (nothing to caption)."""


class LocalFileTemplateImageStore(TemplateImageStore):
    def __init__(self, storage_dir: str):
        self.storage_dir = storage_dir
        os.makedirs(self.storage_dir, exist_ok=True)
        self._meta_path = os.path.join(self.storage_dir, "templates_meta.json")

    # -- meta helpers ----------------------------------------------------

    def _load_meta(self) -> Dict[str, dict]:
        if not os.path.exists(self._meta_path):
            return {}
        with open(self._meta_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _write_meta(self, meta: Dict[str, dict]) -> None:
        with open(self._meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    def _slot_dir(self, slot: str) -> str:
        return os.path.join(self.storage_dir, slot)

    def _sources_dir(self, slot: str) -> str:
        return os.path.join(self._slot_dir(slot), "sources")

    def _validate_slot(self, slot: str) -> None:
        if slot not in TEMPLATE_SLOTS:
            raise ValueError(f"Unknown template slot '{slot}', expected one of {TEMPLATE_SLOTS}")

    # -- writes ------------------------------------------------------------

    def save_template(self, slot: str, source_image_path: str, caption: str) -> TemplateRecord:
        return self.save_template_source(slot, 0, source_image_path, (0.0, 0.0, 1.0, 1.0), caption)

    def save_template_source(
        self, slot: str, position: int, source_image_path: str,
        crop_box: Tuple[float, float, float, float], caption: Optional[str] = None,
    ) -> TemplateRecord:
        self._validate_slot(slot)
        if not (0 <= position < MAX_SOURCES_PER_SLOT):
            raise ValueError(f"position must be 0-{MAX_SOURCES_PER_SLOT - 1}, got {position}")

        os.makedirs(self._sources_dir(slot), exist_ok=True)

        with Image.open(source_image_path) as img:
            img = img.convert("RGB")
            source_width, source_height = img.size
            dest_filename = f"{position}.png"
            dest_path = os.path.join(self._sources_dir(slot), dest_filename)
            img.save(dest_path, "PNG")

        crop_x, crop_y, crop_w, crop_h = crop_box
        now = datetime.now().isoformat()

        meta = self._load_meta()
        slot_meta = meta.get(slot, {"caption": "", "sources": []})
        sources = [s for s in slot_meta.get("sources", []) if s["position"] != position]
        sources.append({
            "position": position,
            "filename": f"{slot}/sources/{dest_filename}",
            "crop_x": crop_x, "crop_y": crop_y, "crop_w": crop_w, "crop_h": crop_h,
            "source_width": source_width, "source_height": source_height,
            "updated_at": now,
        })
        slot_meta["sources"] = sources
        if caption is not None:
            slot_meta["caption"] = caption
        slot_meta["updated_at"] = now
        meta[slot] = slot_meta
        self._write_meta(meta)

        self._recomposite(slot, meta)
        self._write_meta(meta)
        return TemplateRecord(slot=slot, filename=f"{slot}/composite.png", caption=slot_meta["caption"], updated_at=now)

    def remove_template_source(self, slot: str, position: int) -> Optional[TemplateRecord]:
        self._validate_slot(slot)
        meta = self._load_meta()
        slot_meta = meta.get(slot)
        if not slot_meta:
            return None

        remaining = [s for s in slot_meta.get("sources", []) if s["position"] != position]
        removed_path = os.path.join(self._sources_dir(slot), f"{position}.png")
        if os.path.exists(removed_path):
            os.remove(removed_path)

        if not remaining:
            del meta[slot]
            composite_path = os.path.join(self._slot_dir(slot), "composite.png")
            if os.path.exists(composite_path):
                os.remove(composite_path)
            self._write_meta(meta)
            return None

        slot_meta["sources"] = remaining
        slot_meta["updated_at"] = datetime.now().isoformat()
        meta[slot] = slot_meta
        self._recomposite(slot, meta)
        self._write_meta(meta)
        return TemplateRecord(slot=slot, filename=f"{slot}/composite.png", caption=slot_meta["caption"], updated_at=slot_meta["updated_at"])

    def _recomposite(self, slot: str, meta: Dict[str, dict]) -> None:
        """Rebuild {slot}/composite.png from every current sub-image + its
        stored crop, in position order. `meta` is mutated in place with the
        refreshed updated_at; caller is responsible for persisting it."""
        slot_meta = meta[slot]
        cropped: List[Tuple[Image.Image, int]] = []
        for source in slot_meta["sources"]:
            path = os.path.join(self.storage_dir, source["filename"])
            with Image.open(path) as img:
                img = img.convert("RGB")
                w, h = img.size
                box = (
                    int(source["crop_x"] * w),
                    int(source["crop_y"] * h),
                    int((source["crop_x"] + source["crop_w"]) * w),
                    int((source["crop_y"] + source["crop_h"]) * h),
                )
                cropped.append((img.crop(box).copy(), source["position"]))

        composite = template_compositor.composite_slot_images(cropped)
        composite_path = os.path.join(self._slot_dir(slot), "composite.png")
        composite.save(composite_path, "PNG")
        slot_meta["updated_at"] = datetime.now().isoformat()

    # -- reads -------------------------------------------------------------

    def get_template(self, slot: str) -> Optional[TemplateRecord]:
        meta = self._load_meta()
        if slot not in meta:
            return None
        slot_meta = meta[slot]
        return TemplateRecord(
            slot=slot, filename=f"{slot}/composite.png",
            caption=slot_meta.get("caption", ""), updated_at=slot_meta.get("updated_at", ""),
        )

    def get_template_sources(self, slot: str) -> List[TemplateSourceImage]:
        meta = self._load_meta()
        slot_meta = meta.get(slot, {})
        return [
            TemplateSourceImage(
                slot=slot, position=s["position"], filename=s["filename"],
                crop_x=s["crop_x"], crop_y=s["crop_y"], crop_w=s["crop_w"], crop_h=s["crop_h"],
                source_width=s["source_width"], source_height=s["source_height"],
                updated_at=s.get("updated_at", ""),
            )
            for s in sorted(slot_meta.get("sources", []), key=lambda s: s["position"])
        ]

    def get_template_base64(self, slot: str) -> Optional[str]:
        record = self.get_template(slot)
        if record is None:
            return None
        path = os.path.join(self.storage_dir, record.filename)
        if not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def list_templates(self) -> Dict[str, TemplateRecord]:
        meta = self._load_meta()
        return {slot: self.get_template(slot) for slot in meta.keys()}

    def update_caption(self, slot: str, caption: str) -> Optional[TemplateRecord]:
        meta = self._load_meta()
        if slot not in meta:
            return None

        meta[slot]["caption"] = caption
        meta[slot]["updated_at"] = datetime.now().isoformat()
        self._write_meta(meta)
        return self.get_template(slot)
