"""
PromptSection - the Agent 2 vision-compliance prompt editor + version
history, extracted as a reusable widget parameterized by a PromptStore
instance instead of hardcoded module-level constants (so switching strategies
just means constructing this against a different store).

Read-only by default (truncated prompt preview); its own "Configure" button
reveals the full editable textbox + Save/History controls, matching the
per-section configure-to-edit pattern used throughout the Strategies page.

STRATEGY_NAME must match VisionComplianceFilter's default strategy_name
(server/agents/vision_compliance.py) exactly, or the live pipeline reads a
different prompt file than what's edited here.
"""

from tkinter import messagebox

import customtkinter as ctk

from gui.theme import colors, fonts, spacing
from gui.theme.layout import section

STRATEGY_NAME = "vision_compliance_default"
PREVIEW_CHARS = 220


class PromptSection:
    def __init__(self, parent, store, status_callback, title="Agent 2 System Prompt"):
        self.store = store
        self.status_callback = status_callback
        self.title = title

        self.content = section(parent, title)
        self.body = ctk.CTkFrame(self.content, fg_color="transparent")
        self.body.pack(fill="both", expand=True)

        self._render_read_only()

    def refresh(self, store=None):
        """Called by the owning tab after switching strategies (a new
        PromptStore instance for the newly active strategy)."""
        if store is not None:
            self.store = store
        self._render_read_only()

    def _clear_body(self):
        for w in self.body.winfo_children():
            w.destroy()

    # -- read-only view ------------------------------------------------

    def _render_read_only(self):
        self._clear_body()
        latest = self.store.get_latest(STRATEGY_NAME)
        text = latest.text if latest else "No prompt saved yet - a default will be seeded on first run."
        preview = (text[:PREVIEW_CHARS] + "...") if len(text) > PREVIEW_CHARS else text

        ctk.CTkLabel(
            self.body, text=preview, text_color=colors.TEXT_SECONDARY, font=fonts.caption(),
            justify="left", anchor="nw", wraplength=500,
        ).pack(fill="x", anchor="w")

        if latest:
            ctk.CTkLabel(
                self.body, text=f"Currently active: version {latest.version} (saved {latest.created_at})",
                font=fonts.caption(), text_color=colors.TEXT_SECONDARY,
            ).pack(anchor="w", pady=(spacing.XS, spacing.SM))

        ctk.CTkButton(self.body, text="Configure", width=100, command=self._render_editable).pack(anchor="w")

    # -- editable view -------------------------------------------------

    def _render_editable(self):
        self._clear_body()

        self.prompt_box = ctk.CTkTextbox(self.body, height=280, font=fonts.mono(size=11))
        self.prompt_box.pack(fill="both", expand=True)

        latest = self.store.get_latest(STRATEGY_NAME)
        if latest:
            self.prompt_box.insert("1.0", latest.text)
            version_text = f"Currently active: version {latest.version} (saved {latest.created_at})"
        else:
            version_text = "No prompt saved yet - the server will seed a default on first run."
        self.version_label = ctk.CTkLabel(self.body, text=version_text, font=fonts.caption(), text_color=colors.TEXT_SECONDARY)
        self.version_label.pack(anchor="w", pady=(spacing.XS, spacing.SM))

        button_row = ctk.CTkFrame(self.body, fg_color="transparent")
        button_row.pack(anchor="w")
        ctk.CTkButton(button_row, text="Save as New Version", command=self._on_save_prompt, width=160).pack(side="left", padx=(0, spacing.SM))
        ctk.CTkButton(button_row, text="View Version History", command=self._on_view_history, width=160).pack(side="left", padx=(0, spacing.SM))
        ctk.CTkButton(
            button_row, text="Done", command=self._render_read_only, width=100,
            fg_color=colors.SURFACE_ALT, hover_color=colors.SURFACE_ALT,
        ).pack(side="left")

    def _on_save_prompt(self):
        text = self.prompt_box.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Empty Prompt", "Prompt text cannot be empty.")
            return
        record = self.store.save_prompt(STRATEGY_NAME, text, notes="edited via Strategies tab")
        self.version_label.configure(text=f"Currently active: version {record.version} (saved {record.created_at})")
        self.status_callback(f"Saved prompt version {record.version}")

    def _on_view_history(self):
        versions = self.store.list_versions(STRATEGY_NAME)
        if not versions:
            messagebox.showinfo("Version History", "No saved versions yet.")
            return

        history_window = ctk.CTkToplevel(self.body)
        history_window.title("Prompt Version History")
        history_window.geometry("500x400")

        listbox_frame = ctk.CTkScrollableFrame(history_window)
        listbox_frame.pack(fill="both", expand=True, padx=spacing.SM, pady=spacing.SM)

        for v in reversed(versions):
            row = ctk.CTkFrame(listbox_frame, fg_color="transparent")
            row.pack(fill="x", pady=spacing.XS)
            ctk.CTkLabel(
                row, text=f"v{v.version} - {v.created_at}\n{v.notes or ''}", justify="left", anchor="w",
            ).pack(side="left", padx=spacing.SM, pady=spacing.SM, fill="x", expand=True)

            def make_restore(version_num):
                def restore():
                    record = self.store.get_version(STRATEGY_NAME, version_num)
                    if record:
                        self.prompt_box.delete("1.0", "end")
                        self.prompt_box.insert("1.0", record.text)
                        history_window.destroy()
                        self.status_callback(f"Loaded prompt v{version_num} into editor (not saved yet)")
                return restore

            ctk.CTkButton(row, text="Load into editor", width=120, command=make_restore(v.version)).pack(side="right", padx=spacing.SM)
