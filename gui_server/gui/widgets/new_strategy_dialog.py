"""
NewStrategyDialog - modal Name/Category prompt for creating a new strategy.
Category defaults to Name if left blank (per product spec).
"""

from typing import List, NamedTuple, Optional

import customtkinter as ctk

from gui.theme import colors, fonts, spacing


class NewStrategyResult(NamedTuple):
    name: str
    category: str


class NewStrategyDialog(ctk.CTkToplevel):
    def __init__(self, parent, existing_names: List[str]):
        super().__init__(parent)
        self.title("New Strategy")
        self.result: Optional[NewStrategyResult] = None
        self._existing_names_lower = {n.lower() for n in existing_names}

        self.geometry("360x240")
        self.resizable(False, False)

        content = ctk.CTkFrame(self, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=spacing.LG, pady=spacing.LG)

        ctk.CTkLabel(content, text="Name:", anchor="w", font=fonts.body()).pack(fill="x")
        self.name_var = ctk.StringVar()
        self.name_entry = ctk.CTkEntry(content, textvariable=self.name_var)
        self.name_entry.pack(fill="x", pady=(spacing.XS, spacing.SM))

        ctk.CTkLabel(content, text="Category (optional):", anchor="w", font=fonts.body()).pack(fill="x")
        self.category_var = ctk.StringVar()
        ctk.CTkEntry(content, textvariable=self.category_var).pack(fill="x", pady=(spacing.XS, spacing.SM))

        self.error_label = ctk.CTkLabel(content, text="", text_color=colors.ERROR, font=fonts.caption())
        self.error_label.pack(fill="x", pady=(0, spacing.SM))

        button_row = ctk.CTkFrame(content, fg_color="transparent")
        button_row.pack(fill="x")
        ctk.CTkButton(button_row, text="OK", command=self._on_ok, width=110).pack(side="left", padx=(0, spacing.SM))
        ctk.CTkButton(
            button_row, text="Cancel", command=self._on_cancel, width=110,
            fg_color=colors.SURFACE_ALT, hover_color=colors.SURFACE_ALT,
        ).pack(side="left")

        self.bind("<Return>", lambda e: self._on_ok())
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.transient(parent)
        self.grab_set()
        self.name_entry.focus_set()

    def _on_ok(self):
        name = self.name_var.get().strip()
        category = self.category_var.get().strip()

        if not name:
            self.error_label.configure(text="Name is required.")
            return
        if name.lower() in self._existing_names_lower:
            self.error_label.configure(text=f"A strategy named '{name}' already exists.")
            return

        self.result = NewStrategyResult(name=name, category=category or name)
        self.grab_release()
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.grab_release()
        self.destroy()
