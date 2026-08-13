"""
Strategies Tab - manage multiple named strategy bundles (each: 3 template
slots + Agent 2 prompt) for the live trading pipeline's vision-compliance
check. Replaces the old single-global-template-set "Templates" tab.

Local-first: every save writes to strategies_store/{id}/... immediately (see
active_strategy.py / storage/active_strategy_store.py) -- that's what the
live server reads, unaffected by network state. Supabase sync
(storage/supabase_sync.py) is additive and currently a no-op stub.
"""

import json
import logging
import os
import sys
import uuid
from datetime import datetime

import customtkinter as ctk
from PIL import Image

from gui.theme import colors, fonts, spacing
from gui.theme.layout import card
from gui.widgets.new_strategy_dialog import NewStrategyDialog
from gui.widgets.strategy_slot_card import StrategySlotCard, SLOT_LABELS
from gui.widgets.prompt_section import PromptSection, STRATEGY_NAME as PROMPT_STRATEGY_NAME

logger = logging.getLogger(__name__)

_GUI_SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _GUI_SERVER_ROOT not in sys.path:
    sys.path.insert(0, _GUI_SERVER_ROOT)
_SERVER_DIR = os.path.join(_GUI_SERVER_ROOT, "server")
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

import active_strategy
from storage.template_image_store import TEMPLATE_SLOTS, LocalFileTemplateImageStore
from storage.prompt_store import LocalFilePromptStore
from storage.supabase_sync import SupabaseSyncClient

COMPACT_THUMB = (110, 110)


class StrategiesTab:
    def __init__(self, parent_frame, config_manager, status_callback):
        self.parent = parent_frame
        self.config_manager = config_manager
        self.status_callback = status_callback

        self.sync = SupabaseSyncClient()
        self.current_strategy_id = None
        self.current_strategy_name = None
        self.template_store = None
        self.prompt_store = None
        self.view_mode = "compact"  # "compact" | "full"
        self._dropdown_lookup = {}

        self.root = ctk.CTkFrame(self.parent, fg_color="transparent")
        self.root.pack(fill="both", expand=True)

        self._build_top_bar()
        self.content_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, pady=(spacing.SM, 0))

        self._load_initial_strategy()

    # -- top bar -----------------------------------------------------------

    def _build_top_bar(self):
        bar = ctk.CTkFrame(self.root, fg_color="transparent")
        bar.pack(fill="x")

        ctk.CTkButton(bar, text="+ New", command=self._on_new_strategy, width=90).pack(side="left")

        self.strategy_var = ctk.StringVar(value="")
        self.strategy_menu = ctk.CTkOptionMenu(
            bar, variable=self.strategy_var, values=[""], width=220, command=self._on_dropdown_change,
        )
        self.strategy_menu.pack(side="left", padx=(spacing.SM, 0))

    def _list_local_strategies(self):
        """[(id, name), ...] sorted by name, from strategies_store/*/strategy_meta.json"""
        results = []
        if not os.path.isdir(active_strategy.STRATEGIES_STORE_DIR):
            return results
        for entry in os.listdir(active_strategy.STRATEGIES_STORE_DIR):
            meta_path = os.path.join(active_strategy.STRATEGIES_STORE_DIR, entry, "strategy_meta.json")
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    results.append((meta["id"], meta["name"]))
                except Exception as e:
                    logger.warning(f"Could not read {meta_path}: {e}")
        return sorted(results, key=lambda pair: pair[1].lower())

    def _refresh_dropdown(self):
        strategies = self._list_local_strategies()
        names = [name for _id, name in strategies]
        self._dropdown_lookup = {name: sid for sid, name in strategies}
        self.strategy_menu.configure(values=names or [""])
        if self.current_strategy_name and self.current_strategy_name in names:
            self.strategy_var.set(self.current_strategy_name)
        elif names:
            self.strategy_var.set(names[0])
        else:
            self.strategy_var.set("")

    # -- initial load --------------------------------------------------

    def _load_initial_strategy(self):
        strategies = self._list_local_strategies()
        if not strategies:
            remote = self.sync.list_remote_strategies()
            if remote:
                newest = remote[0]
                if self.sync.pull_strategy(newest["id"]):
                    strategies = self._list_local_strategies()

        self._refresh_dropdown()

        active_id = active_strategy.get_active_strategy_id()
        target = None
        if active_id and any(sid == active_id for sid, _ in strategies):
            target = active_id
        elif strategies:
            target = strategies[0][0]

        if target:
            self._switch_to(target)
        else:
            self._render_empty_state()

    # -- switching / creating -------------------------------------------

    def _on_dropdown_change(self, selected_name):
        strategy_id = self._dropdown_lookup.get(selected_name)
        if strategy_id and strategy_id != self.current_strategy_id:
            self._switch_to(strategy_id)

    def _switch_to(self, strategy_id):
        # Best-effort pull before displaying -- pull_strategy() returns False
        # today (no-op stub, see supabase_sync.py) so this always falls
        # through to whatever's already cached locally.
        self.sync.pull_strategy(strategy_id)

        strategy_dir = active_strategy.get_strategy_dir(strategy_id)
        meta_path = os.path.join(strategy_dir, "strategy_meta.json")
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                name = json.load(f)["name"]
        except Exception:
            name = strategy_id

        self.current_strategy_id = strategy_id
        self.current_strategy_name = name
        self.template_store = LocalFileTemplateImageStore(os.path.join(strategy_dir, "templates"))
        self.prompt_store = LocalFilePromptStore(os.path.join(strategy_dir, "prompts"))

        active_strategy.set_active_strategy_id(strategy_id, name)
        self.sync.push_active_strategy(strategy_id)

        self._refresh_dropdown()
        self.view_mode = "compact"
        self._render_content()
        self.status_callback(f"Strategy '{name}' is now active")

    def _on_new_strategy(self):
        existing_names = [name for _id, name in self._list_local_strategies()]
        dialog = NewStrategyDialog(self.parent, existing_names)
        self.parent.wait_window(dialog)
        if dialog.result is None:
            return

        strategy_id = str(uuid.uuid4())
        strategy_dir = active_strategy.get_strategy_dir(strategy_id)
        os.makedirs(strategy_dir, exist_ok=True)
        now = datetime.now().isoformat()
        meta = {
            "id": strategy_id, "name": dialog.result.name, "category": dialog.result.category,
            "created_at": now, "updated_at": now,
        }
        with open(os.path.join(strategy_dir, "strategy_meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        self.template_store = LocalFileTemplateImageStore(os.path.join(strategy_dir, "templates"))
        self.prompt_store = LocalFilePromptStore(os.path.join(strategy_dir, "prompts"))
        self.current_strategy_id = strategy_id
        self.current_strategy_name = dialog.result.name

        active_strategy.set_active_strategy_id(strategy_id, dialog.result.name)
        self.sync.push_strategy_create(strategy_id, dialog.result.name, dialog.result.category)
        self.sync.push_active_strategy(strategy_id)

        self._refresh_dropdown()
        self.view_mode = "full"  # per spec: OK reveals the full editing view directly
        self._render_content()
        self.status_callback(f"Created strategy '{dialog.result.name}'")

    # -- rendering -------------------------------------------------------

    def _clear_content(self):
        for w in self.content_frame.winfo_children():
            w.destroy()

    def _render_empty_state(self):
        self._clear_content()
        wrapper = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        wrapper.pack(expand=True)
        ctk.CTkLabel(
            wrapper, text="No strategies yet", font=fonts.section(), text_color=colors.TEXT_SECONDARY,
        ).pack(pady=(spacing.XL, spacing.SM))
        ctk.CTkButton(wrapper, text="Add New", command=self._on_new_strategy, width=140).pack()

    def _render_content(self):
        self._clear_content()
        if self.view_mode == "compact":
            self._render_compact()
        else:
            self._render_full()

    def _render_compact(self):
        wrapper = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        wrapper.pack(fill="both", expand=True)

        thumbs_row = ctk.CTkFrame(wrapper, fg_color="transparent")
        thumbs_row.pack(fill="x", pady=(0, spacing.SM))
        for slot in TEMPLATE_SLOTS:
            self._build_compact_thumb(thumbs_row, slot)

        latest = self.prompt_store.get_latest(PROMPT_STRATEGY_NAME)
        if latest:
            preview_text = (latest.text[:200] + "...") if len(latest.text) > 200 else latest.text
        else:
            preview_text = "No prompt saved yet."
        ctk.CTkLabel(
            wrapper, text=preview_text, text_color=colors.TEXT_SECONDARY, font=fonts.caption(),
            justify="left", anchor="w", wraplength=800,
        ).pack(fill="x", pady=(0, spacing.SM))

        ctk.CTkButton(wrapper, text="View", command=self._on_view_full, width=100).pack(anchor="w")

    def _build_compact_thumb(self, parent, slot):
        box = card(parent, padding=spacing.XS)
        box.pack(side="left", padx=(0, spacing.SM))
        record = self.template_store.get_template(slot)
        label = ctk.CTkLabel(
            box, text="" if record else SLOT_LABELS.get(slot, slot),
            text_color=colors.TEXT_SECONDARY, font=fonts.caption(),
            width=COMPACT_THUMB[0], height=COMPACT_THUMB[1], wraplength=COMPACT_THUMB[0] - 10,
        )
        label.pack(padx=spacing.XS, pady=(spacing.XS, 2))
        if record:
            path = os.path.join(self.template_store.storage_dir, record.filename)
            try:
                if os.path.exists(path):
                    img = Image.open(path).convert("RGB")
                    img.thumbnail(COMPACT_THUMB)
                    ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=img.size)
                    label.configure(image=ctk_img, text="")
                    label.image = ctk_img
            except Exception:
                pass
        ctk.CTkLabel(
            box, text=SLOT_LABELS.get(slot, slot), font=fonts.caption(), text_color=colors.TEXT_SECONDARY,
        ).pack(padx=spacing.XS, pady=(0, spacing.XS))

    def _on_view_full(self):
        self.view_mode = "full"
        self._render_content()

    def _render_full(self):
        root = ctk.CTkFrame(self.content_frame, fg_color="transparent")
        root.pack(fill="both", expand=True)

        top_row = ctk.CTkFrame(root, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, spacing.SM))
        ctk.CTkLabel(top_row, text=self.current_strategy_name or "", font=fonts.heading()).pack(side="left")
        ctk.CTkButton(
            top_row, text="Collapse", command=self._on_collapse, width=100,
            fg_color=colors.SURFACE_ALT, hover_color=colors.SURFACE_ALT,
        ).pack(side="right")

        columns = ctk.CTkFrame(root, fg_color="transparent")
        columns.pack(fill="both", expand=True)
        columns.grid_columnconfigure(0, weight=1)
        columns.grid_columnconfigure(1, weight=1)
        columns.grid_rowconfigure(0, weight=1)

        left_col = ctk.CTkScrollableFrame(columns, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, spacing.MD))
        right_col = ctk.CTkFrame(columns, fg_color="transparent")
        right_col.grid(row=0, column=1, sticky="nsew", padx=(spacing.MD, 0))

        for slot in TEMPLATE_SLOTS:
            StrategySlotCard(left_col, slot, self.template_store, self.status_callback)

        PromptSection(right_col, self.prompt_store, self.status_callback)

    def _on_collapse(self):
        self.view_mode = "compact"
        self._render_content()
