"""
Controls Tab for AegisVision AI Trading Server GUI

Merges the former Configuration + Server Control tabs into one page:
left column = configuration (server/LLM/trading/advanced settings + save/
load/reset/export), right column = server status/control/statistics,
bottom strip = recent trading signals flowing left-to-right. This mirrors
the "grounded" layout used across the app -- section() headings + hairline
dividers instead of nested bordered cards, cards reserved for the signal
chips and stat tiles.
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox, filedialog
import logging
import os
import sys
import requests
import threading
import time
from datetime import datetime
from threading import Thread

from gui.theme import colors, fonts, spacing, icons
from gui.theme.layout import section, divider, card

LEFT_LABEL_WIDTH = 170
RIGHT_LABEL_WIDTH = 150

logger = logging.getLogger(__name__)

# Same sys.path bootstrap as server_tab.py used, so this (GUI-process) module
# can read the audit log the (separate, Flask-process) server writes to --
# both read/write the same on-disk file, no IPC needed.
_GUI_SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _GUI_SERVER_ROOT not in sys.path:
    sys.path.insert(0, _GUI_SERVER_ROOT)
_SERVER_DIR = os.path.join(_GUI_SERVER_ROOT, "server")
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)

from app_paths import get_app_root
from audit.audit_log import JsonlAuditLogger

# get_app_root(), not _GUI_SERVER_ROOT: must match trading_server.py's frozen-safe path.
AUDIT_LOG_PATH = os.path.join(get_app_root(), "storage_data", "audit_log.jsonl")

MAX_SIGNAL_CHIPS = 20


class ControlsTab:
    """Merged configuration + server control + recent signals tab"""

    def __init__(self, parent_frame, config_manager, server_manager, status_callback):
        self.parent = parent_frame
        self.config_manager = config_manager
        self.server_manager = server_manager
        self.status_callback = status_callback

        # Configuration variables (mirrors the old ConfigTab.config_vars pattern)
        self.config_vars = {}
        self.llm_status_label = None

        # Server control UI element references
        self.status_label = None
        self.server_info_label = None
        self.start_btn = None
        self.stop_btn = None
        self.restart_btn = None
        self.stat_values = {}

        # Recent signals
        self.signals_strip = None
        self._signal_records = []  # newest first

        # Monitoring
        self.monitoring_active = False
        self.monitor_thread = None
        self.audit_store = JsonlAuditLogger(AUDIT_LOG_PATH)
        self._audit_records_seen = 0

        self.create_ui()
        self.load_current_config()
        self.start_monitoring()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def create_ui(self):
        root = ctk.CTkFrame(self.parent, fg_color="transparent")
        root.pack(fill="both", expand=True)
        root.grid_columnconfigure(0, weight=3)
        root.grid_columnconfigure(1, weight=0)
        root.grid_columnconfigure(2, weight=2)
        root.grid_rowconfigure(0, weight=1)
        root.grid_rowconfigure(1, weight=0)

        # grid_columnconfigure's weight only distributes *leftover* space
        # beyond each column's content-driven minimum -- with a plain (non-
        # scrolling) left column, its form fields demand enough width that
        # the 3:2 weight ratio barely mattered and the right column got
        # squeezed toward its own bare minimum. Enforcing minsize directly,
        # recomputed on every resize, keeps the intended 3:2 split honest.
        def _enforce_column_ratio(event=None):
            total_w = root.winfo_width()
            if total_w > 50:
                usable = total_w - spacing.DIVIDER_THICKNESS - 2 * spacing.MD
                root.grid_columnconfigure(0, minsize=int(usable * 3 / 5))
                root.grid_columnconfigure(2, minsize=int(usable * 2 / 5))

        root.bind("<Configure>", _enforce_column_ratio)
        root.after(50, _enforce_column_ratio)

        left_col = ctk.CTkFrame(root, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="nsew", padx=(0, spacing.MD))

        divider(root, vertical=True).grid(row=0, column=1, sticky="ns")

        right_col = ctk.CTkFrame(root, fg_color="transparent")
        right_col.grid(row=0, column=2, sticky="nsew", padx=(spacing.MD, 0))

        bottom_strip = ctk.CTkFrame(root, fg_color="transparent")
        bottom_strip.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(spacing.MD, 0))

        self.create_left_column(left_col)
        self.create_right_column(right_col)
        self.create_signals_strip(bottom_strip)

    def _section_with_status(self, parent, title: str):
        """Same visual shape as theme.layout.section() (heading + hairline
        divider + transparent content frame), but with a status badge label
        packed to the right of the title -- used for "LLM Configuration
        (Not Configured)" which updates in place once a key is verified."""
        outer = ctk.CTkFrame(parent, fg_color="transparent")
        outer.pack(fill="x", pady=(0, spacing.LG))

        heading_row = ctk.CTkFrame(outer, fg_color="transparent")
        heading_row.pack(fill="x", pady=(0, spacing.XS))
        ctk.CTkLabel(heading_row, text=title, font=fonts.section(), text_color=colors.TEXT_PRIMARY).pack(side="left")
        status_label = ctk.CTkLabel(heading_row, text="", font=fonts.caption())
        status_label.pack(side="left", padx=(spacing.XS, 0))

        divider(outer).pack(fill="x", pady=(0, spacing.SM))

        content = ctk.CTkFrame(outer, fg_color="transparent")
        content.pack(fill="both", expand=True)
        return content, status_label

    def _update_llm_status(self, configured: bool):
        if not self.llm_status_label:
            return
        if configured:
            self.llm_status_label.configure(text="(Configured)", text_color=colors.SUCCESS)
        else:
            self.llm_status_label.configure(text="(Not Configured)", text_color=colors.TEXT_SECONDARY)

    # ------------------------------------------------------------------
    # Left column: configuration
    # ------------------------------------------------------------------

    def create_left_column(self, parent):
        self.create_server_settings(parent)
        self.create_llm_configuration(parent)
        self.create_trading_parameters(parent)
        self.create_config_management(parent)

    def create_server_settings(self, parent):
        content = section(parent, "Server Settings")

        self.config_vars["host"] = ctk.StringVar(value="localhost")
        ctk.CTkLabel(content, text="Host:", width=LEFT_LABEL_WIDTH, anchor="w").grid(row=0, column=0, pady=spacing.XS, sticky="w")
        ctk.CTkEntry(content, textvariable=self.config_vars["host"], width=150).grid(row=0, column=1, padx=(0, spacing.LG), pady=spacing.XS, sticky="w")

        self.config_vars["port"] = ctk.StringVar(value="8080")
        ctk.CTkLabel(content, text="Port:", width=RIGHT_LABEL_WIDTH, anchor="w").grid(row=0, column=2, pady=spacing.XS, sticky="w")
        ctk.CTkEntry(content, textvariable=self.config_vars["port"], width=100).grid(row=0, column=3, padx=(0, spacing.LG), pady=spacing.XS, sticky="w")

        ctk.CTkButton(content, text="Test Connection", command=self.test_connection, width=130).grid(row=0, column=4, pady=spacing.XS, sticky="w")

    def create_llm_configuration(self, parent):
        content, self.llm_status_label = self._section_with_status(parent, "AI Configuration")

        self.config_vars["llm_provider"] = ctk.StringVar(value="gemini")
        ctk.CTkLabel(content, text="Provider:", width=LEFT_LABEL_WIDTH, anchor="w").grid(row=0, column=0, pady=spacing.XS, sticky="w")
        ctk.CTkOptionMenu(
            content, variable=self.config_vars["llm_provider"],
            values=["openai", "anthropic", "gemini"],
            command=self.on_provider_change, width=140,
        ).grid(row=0, column=1, padx=(0, spacing.LG), pady=spacing.XS, sticky="w")

        self.config_vars["model"] = ctk.StringVar(value="gemini-2.5-flash")
        ctk.CTkLabel(content, text="Model:", width=RIGHT_LABEL_WIDTH, anchor="w").grid(row=0, column=2, pady=spacing.XS, sticky="w")
        self.model_menu = ctk.CTkOptionMenu(
            content, variable=self.config_vars["model"],
            values=self.get_models_for_provider("gemini"), width=200,
        )
        self.model_menu.grid(row=0, column=3, pady=spacing.XS, sticky="w")

        self.config_vars["api_key"] = ctk.StringVar()
        ctk.CTkLabel(content, text="API Key:", width=LEFT_LABEL_WIDTH, anchor="w").grid(row=1, column=0, pady=spacing.XS, sticky="w")
        ctk.CTkEntry(
            content, textvariable=self.config_vars["api_key"], show="*",
            width=290, placeholder_text="Enter your API key...",
        ).grid(row=1, column=1, columnspan=2, padx=(0, spacing.LG), pady=spacing.XS, sticky="w")
        ctk.CTkButton(content, text="Test API", command=self.test_api_connection, width=100).grid(row=1, column=3, pady=spacing.XS, sticky="w")

        self.config_vars["temperature"] = ctk.StringVar(value="0.3")
        ctk.CTkLabel(content, text="Temperature:", width=LEFT_LABEL_WIDTH, anchor="w").grid(row=2, column=0, pady=spacing.XS, sticky="w")
        ctk.CTkEntry(content, textvariable=self.config_vars["temperature"], width=80).grid(row=2, column=1, padx=(0, spacing.LG), pady=spacing.XS, sticky="w")

        self.config_vars["max_tokens"] = ctk.StringVar(value="4000")
        ctk.CTkLabel(content, text="Max Tokens:", width=RIGHT_LABEL_WIDTH, anchor="w").grid(row=2, column=2, pady=spacing.XS, sticky="w")
        ctk.CTkEntry(content, textvariable=self.config_vars["max_tokens"], width=80).grid(row=2, column=3, pady=spacing.XS, sticky="w")

    def create_trading_parameters(self, parent):
        content = section(parent, "Trading Parameters")

        self.config_vars["min_confidence"] = ctk.StringVar(value="70")
        ctk.CTkLabel(content, text="Min Confidence (%):", width=LEFT_LABEL_WIDTH, anchor="w").grid(row=0, column=0, pady=spacing.XS, sticky="w")
        ctk.CTkEntry(content, textvariable=self.config_vars["min_confidence"], width=80).grid(row=0, column=1, padx=(0, spacing.LG), pady=spacing.XS, sticky="w")

        self.config_vars["min_risk_reward"] = ctk.StringVar(value="1.5")
        ctk.CTkLabel(content, text="Min Risk:Reward:", width=RIGHT_LABEL_WIDTH, anchor="w").grid(row=0, column=2, pady=spacing.XS, sticky="w")
        ctk.CTkEntry(content, textvariable=self.config_vars["min_risk_reward"], width=80).grid(row=0, column=3, pady=spacing.XS, sticky="w")

        self.config_vars["max_spread"] = ctk.StringVar(value="2.0")
        ctk.CTkLabel(content, text="Max Spread (pips):", width=LEFT_LABEL_WIDTH, anchor="w").grid(row=1, column=0, pady=spacing.XS, sticky="w")
        ctk.CTkEntry(content, textvariable=self.config_vars["max_spread"], width=80).grid(row=1, column=1, padx=(0, spacing.LG), pady=spacing.XS, sticky="w")

        self.config_vars["max_trades"] = ctk.StringVar(value="3")
        ctk.CTkLabel(content, text="Max Trades:", width=RIGHT_LABEL_WIDTH, anchor="w").grid(row=1, column=2, pady=spacing.XS, sticky="w")
        ctk.CTkEntry(content, textvariable=self.config_vars["max_trades"], width=80).grid(row=1, column=3, pady=spacing.XS, sticky="w")

    def create_config_management(self, parent):
        content = section(parent, "Configuration Management", pady=(0, spacing.LG))
        buttons = ctk.CTkFrame(content, fg_color="transparent")
        buttons.pack(fill="x")

        ctk.CTkButton(buttons, text="Save Configuration", command=self.save_configuration, width=140).pack(side="left", padx=(0, spacing.SM))
        ctk.CTkButton(buttons, text="Load Configuration", command=self.load_configuration, width=140).pack(side="left", padx=(0, spacing.SM))
        ctk.CTkButton(buttons, text="Reset to Defaults", command=self.reset_configuration, width=140).pack(side="left", padx=(0, spacing.SM))
        ctk.CTkButton(buttons, text="Export Config File", command=self.export_configuration, width=140).pack(side="left")

    # ------------------------------------------------------------------
    # Right column: status / control / statistics
    # ------------------------------------------------------------------

    def create_right_column(self, parent):
        self.create_status_section(parent)
        self.create_control_section(parent)
        self.create_statistics_section(parent)

    def create_status_section(self, parent):
        content = section(parent, "Server Status")

        self.status_label = ctk.CTkLabel(
            content, text="● STOPPED - Server not running",
            font=ctk.CTkFont(size=16, weight="bold"), text_color=colors.ERROR,
        )
        self.status_label.pack(anchor="w")

        self.server_info_label = ctk.CTkLabel(
            content, text="Configure settings and click 'Start Server' to begin",
            font=fonts.caption(), text_color=colors.TEXT_SECONDARY,
        )
        self.server_info_label.pack(anchor="w", pady=(spacing.XS, 0))

    def create_control_section(self, parent):
        content = section(parent, "Server Control")
        row1 = ctk.CTkFrame(content, fg_color="transparent")
        row1.pack(fill="x")
        row2 = ctk.CTkFrame(content, fg_color="transparent")
        row2.pack(fill="x", pady=(spacing.SM, 0))

        # Fixed dark stroke on all four buttons -- matches the icon color,
        # applied for both normal and disabled states, so text and icon
        # never mismatch when a button is temporarily disabled.
        btn_kwargs = dict(text_color=colors.TEXT_ON_ACCENT, text_color_disabled=colors.TEXT_ON_ACCENT)

        self.start_btn = ctk.CTkButton(
            row1, text="Start Server", command=self.start_server,
            image=icons.play_icon(), compound="left",
            height=36, corner_radius=spacing.RADIUS_PILL, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=colors.SUCCESS, hover_color=colors.SUCCESS, **btn_kwargs,
        )
        self.start_btn.pack(side="left", expand=True, fill="x", padx=(0, spacing.XS))

        self.stop_btn = ctk.CTkButton(
            row1, text="Stop Server", command=self.stop_server,
            image=icons.stop_icon(), compound="left",
            height=36, corner_radius=spacing.RADIUS_PILL, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=colors.ERROR, hover_color=colors.ERROR, state="disabled", **btn_kwargs,
        )
        self.stop_btn.pack(side="left", expand=True, fill="x", padx=(spacing.XS, 0))

        self.restart_btn = ctk.CTkButton(
            row2, text="Restart", command=self.restart_server,
            image=icons.restart_icon(), compound="left",
            height=36, corner_radius=spacing.RADIUS_PILL, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=colors.WARNING, hover_color=colors.WARNING, state="disabled", **btn_kwargs,
        )
        self.restart_btn.pack(side="left", expand=True, fill="x", padx=(0, spacing.XS))

        ctk.CTkButton(
            row2, text="Health Check", command=self.health_check,
            image=icons.health_icon(), compound="left",
            height=36, corner_radius=spacing.RADIUS_PILL, font=ctk.CTkFont(size=13, weight="bold"),
            **btn_kwargs,
        ).pack(side="left", expand=True, fill="x", padx=(spacing.XS, 0))

    def create_statistics_section(self, parent):
        content = section(parent, "Server Statistics", pady=(0, spacing.LG))
        grid = ctk.CTkFrame(content, fg_color="transparent")
        grid.pack(fill="x")
        grid.grid_columnconfigure((0, 1), weight=1)

        tiles = [
            ("connections", "Active Connections", "0", 0, 0),
            ("uptime", "Server Uptime", "Not running", 0, 1),
            ("requests", "Total Requests Today", "0", 1, 0),
            ("last_request", "Last Request", "None", 1, 1),
        ]
        for key, label, initial, r, c in tiles:
            tile = card(grid, padding=spacing.SM)
            tile.grid(row=r, column=c, sticky="ew", padx=spacing.XS, pady=spacing.XS)
            ctk.CTkLabel(tile, text=label, font=fonts.caption(), text_color=colors.TEXT_SECONDARY, anchor="w").pack(fill="x", padx=spacing.SM, pady=(spacing.SM, 0))
            value_label = ctk.CTkLabel(tile, text=initial, font=ctk.CTkFont(size=13, weight="bold"), anchor="w")
            value_label.pack(fill="x", padx=spacing.SM, pady=(0, spacing.SM))
            self.stat_values[key] = value_label

    # ------------------------------------------------------------------
    # Bottom strip: recent trading signals
    # ------------------------------------------------------------------

    def create_signals_strip(self, parent):
        content = section(parent, "Recent Trading Signals", pady=(0, 0))
        self.signals_strip = ctk.CTkScrollableFrame(
            content, orientation="horizontal", height=110, fg_color="transparent",
        )
        self.signals_strip.pack(fill="x")
        self._rebuild_signal_chips()

    def _rebuild_signal_chips(self):
        for child in self.signals_strip.winfo_children():
            child.destroy()

        if not self._signal_records:
            ctk.CTkLabel(
                self.signals_strip,
                text="No trading signals yet. Start the server to begin receiving signals.",
                font=fonts.caption(), text_color=colors.TEXT_SECONDARY,
            ).pack(side="left", padx=spacing.SM, pady=spacing.SM)
            return

        for record in self._signal_records:
            self._build_signal_chip(self.signals_strip, record).pack(side="left", padx=(0, spacing.SM), pady=spacing.SM)

    def _build_signal_chip(self, parent, record: dict) -> ctk.CTkFrame:
        chip = card(parent, padding=spacing.SM)
        chip.configure(width=180, height=90)
        chip.pack_propagate(False)

        action = record.get("action", "WAIT")
        chip_color = {"BUY": colors.SIGNAL_BUY, "SELL": colors.SIGNAL_SELL}.get(action, colors.SIGNAL_WAIT)
        icon = {"BUY": "▲", "SELL": "▼"}.get(action, "■")

        ctk.CTkLabel(
            chip, text=f"{icon} {action} {record.get('symbol', '')}",
            font=ctk.CTkFont(size=12, weight="bold"), text_color=chip_color, anchor="w",
        ).pack(fill="x", padx=spacing.SM, pady=(spacing.SM, 0))

        confidence = record.get("confidence", 0)
        try:
            confidence_text = f"{float(confidence):.0f}%"
        except (TypeError, ValueError):
            confidence_text = "--"
        ctk.CTkLabel(
            chip, text=f"{record.get('timestamp', '')}  ·  {confidence_text}",
            font=fonts.caption(), text_color=colors.TEXT_SECONDARY, anchor="w",
        ).pack(fill="x", padx=spacing.SM)

        reasoning = record.get("reasoning", "")
        if len(reasoning) > 70:
            reasoning = reasoning[:70] + "..."
        ctk.CTkLabel(
            chip, text=reasoning, font=fonts.caption(), text_color=colors.TEXT_PRIMARY,
            anchor="w", justify="left", wraplength=160,
        ).pack(fill="x", padx=spacing.SM, pady=(0, spacing.SM))

        return chip

    # ------------------------------------------------------------------
    # LLM provider / model helpers
    # ------------------------------------------------------------------

    def get_models_for_provider(self, provider: str) -> list:
        models = {
            "openai": ["gpt-4", "gpt-4-turbo", "gpt-3.5-turbo"],
            "anthropic": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
            "gemini": [
                "gemini-2.5-flash",
                "gemini-2.5-flash-lite",
                "gemini-2.0-flash-exp",
                "gemini-1.5-flash-latest",
                "gemini-1.5-pro-latest",
                "gemini-1.5-flash",
                "gemini-1.5-pro",
            ],
        }
        return models.get(provider, [])

    def on_provider_change(self, provider: str):
        models = self.get_models_for_provider(provider)
        self.model_menu.configure(values=models)
        if models:
            self.config_vars["model"].set(models[0])

    # ------------------------------------------------------------------
    # Connection / API tests
    # ------------------------------------------------------------------

    def test_connection(self):
        def test():
            try:
                host = self.config_vars["host"].get()
                port = self.config_vars["port"].get()
                if not host or not port:
                    messagebox.showerror("Error", "Please enter host and port")
                    return
                url = f"http://{host}:{port}/health"
                response = requests.get(url, timeout=5)
                if response.status_code == 200:
                    messagebox.showinfo("Success", "Connection test successful!")
                    self.status_callback("Server connection test successful")
                else:
                    messagebox.showerror("Error", f"Server returned status {response.status_code}")
            except requests.exceptions.ConnectionError:
                messagebox.showwarning("Warning", "Server not responding (may not be started yet)")
            except Exception as e:
                messagebox.showerror("Error", f"Connection test failed: {e}")

        Thread(target=test, daemon=True).start()

    def test_api_connection(self):
        def test():
            try:
                provider = self.config_vars["llm_provider"].get()
                api_key = self.config_vars["api_key"].get()
                if not api_key:
                    messagebox.showerror("Error", "Please enter API key")
                    return

                if provider == "openai":
                    headers = {"Authorization": f"Bearer {api_key}"}
                    response = requests.get("https://api.openai.com/v1/models", headers=headers, timeout=10)
                elif provider == "anthropic":
                    headers = {"x-api-key": api_key, "anthropic-version": "2023-06-01"}
                    response = requests.get("https://api.anthropic.com/v1/models", headers=headers, timeout=10)
                elif provider == "gemini":
                    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
                    response = requests.get(url, timeout=10)
                else:
                    messagebox.showerror("Error", f"Unknown provider: {provider}")
                    return

                if response.status_code == 200:
                    messagebox.showinfo("Success", f"{provider.title()} API connection successful!")
                    self.status_callback(f"{provider.title()} API test successful")
                    self._update_llm_status(True)
                else:
                    messagebox.showerror("Error", f"API test failed: {response.status_code}")
                    self._update_llm_status(False)
            except Exception as e:
                messagebox.showerror("Error", f"API test failed: {e}")

        Thread(target=test, daemon=True).start()

    # ------------------------------------------------------------------
    # Config save/load/reset/export
    # ------------------------------------------------------------------

    def _apply_config_to_widgets(self, config_data: dict):
        for var_name, var in self.config_vars.items():
            if var_name in config_data:
                var.set(config_data[var_name])
        self._update_llm_status(bool(config_data.get("api_key")))

    def save_configuration(self):
        try:
            config_data = {var: value.get() for var, value in self.config_vars.items()}
            self.config_manager.save_config(config_data)
            messagebox.showinfo("Success", "Configuration saved successfully!")
            self.status_callback("Configuration saved")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save configuration: {e}")

    def load_configuration(self):
        try:
            config_data = self.config_manager.get_flat_config()
            self._apply_config_to_widgets(config_data)
            messagebox.showinfo("Success", "Configuration loaded successfully!")
            self.status_callback("Configuration loaded")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load configuration: {e}")

    def load_current_config(self):
        try:
            config_data = self.config_manager.get_flat_config()
            self._apply_config_to_widgets(config_data)
        except Exception as e:
            logger.warning(f"Could not load existing configuration: {e}")

    def reset_configuration(self):
        if messagebox.askyesno("Confirm Reset", "Reset all settings to defaults?"):
            defaults = {
                "host": "localhost",
                "port": "8080",
                "llm_provider": "gemini",
                "model": "gemini-2.5-flash",
                "api_key": "",
                "temperature": "0.3",
                "max_tokens": "4000",
                "min_confidence": "70",
                "min_risk_reward": "1.5",
                "max_spread": "2.0",
                "max_trades": "3",
            }
            for var_name, default_value in defaults.items():
                if var_name in self.config_vars:
                    self.config_vars[var_name].set(default_value)
            self.status_callback("Configuration reset to defaults")

    def export_configuration(self):
        try:
            file_path = filedialog.asksaveasfilename(
                title="Export Configuration",
                defaultextension=".json",
                filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            )
            if file_path:
                config_data = {var: value.get() for var, value in self.config_vars.items()}
                self.config_manager.export_config(config_data, file_path)
                messagebox.showinfo("Success", f"Configuration exported to {file_path}")
                self.status_callback(f"Configuration exported to {os.path.basename(file_path)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export configuration: {e}")

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    def start_server(self):
        try:
            self.start_btn.configure(state="disabled")
            self.stop_btn.configure(state="normal")
            self.restart_btn.configure(state="normal")

            self.status_label.configure(text="● STARTING - Initializing server...", text_color=colors.WARNING)
            self.status_callback("Starting server...", "starting")

            def start():
                try:
                    success = self.server_manager.start_server()
                    if success:
                        self.update_server_status("running")
                        self.status_callback("Server started successfully", "running")
                    else:
                        self.update_server_status("error")
                        self.status_callback("Failed to start server", "error")
                        messagebox.showerror("Error", "Failed to start server. Check configuration and logs.")
                except Exception as e:
                    self.update_server_status("error")
                    self.status_callback(f"Server start error: {e}", "error")
                    messagebox.showerror("Error", f"Server start failed: {e}")

            threading.Thread(target=start, daemon=True).start()
        except Exception as e:
            logger.error(f"Error starting server: {e}")
            messagebox.showerror("Error", f"Failed to start server: {e}")
            self.update_server_status("error")

    def stop_server(self):
        try:
            self.status_label.configure(text="● STOPPING - Shutting down server...", text_color=colors.WARNING)
            self.status_callback("Stopping server...", "stopping")

            def stop():
                try:
                    self.server_manager.stop_server()
                    self.update_server_status("stopped")
                    self.status_callback("Server stopped", "stopped")
                except Exception as e:
                    logger.error(f"Error stopping server: {e}")
                    self.update_server_status("error")
                    self.status_callback(f"Server stop error: {e}", "error")

            threading.Thread(target=stop, daemon=True).start()
        except Exception as e:
            logger.error(f"Error stopping server: {e}")
            messagebox.showerror("Error", f"Failed to stop server: {e}")

    def restart_server(self):
        try:
            self.status_label.configure(text="● RESTARTING - Please wait...", text_color=colors.WARNING)
            self.status_callback("Restarting server...", "restarting")

            def restart():
                try:
                    self.server_manager.restart_server()
                    self.update_server_status("running")
                    self.status_callback("Server restarted successfully", "running")
                except Exception as e:
                    logger.error(f"Error restarting server: {e}")
                    self.update_server_status("error")
                    self.status_callback(f"Server restart error: {e}", "error")
                    messagebox.showerror("Error", f"Failed to restart server: {e}")

            threading.Thread(target=restart, daemon=True).start()
        except Exception as e:
            logger.error(f"Error restarting server: {e}")
            messagebox.showerror("Error", f"Failed to restart server: {e}")

    def health_check(self):
        def check():
            try:
                health_info = self.server_manager.health_check()
                if health_info:
                    status = health_info.get("status", "unknown")
                    if status == "healthy":
                        messagebox.showinfo("Health Check", "Server is healthy and responding normally")
                    else:
                        messagebox.showwarning("Health Check", f"Server status: {status}")
                else:
                    messagebox.showerror("Health Check", "Server is not responding")
            except Exception as e:
                messagebox.showerror("Health Check", f"Health check failed: {e}")

        threading.Thread(target=check, daemon=True).start()

    def update_server_status(self, status: str):
        try:
            if status == "running":
                self.status_label.configure(text="● RUNNING - Server active and accepting requests", text_color=colors.SUCCESS)
                config = self.server_manager.config_manager.get_current_config()
                server_cfg = config.get("server", {})
                host = server_cfg.get("host", "localhost")
                port = server_cfg.get("port", "8080")
                self.server_info_label.configure(text=f"Server running on http://{host}:{port}")
                self.start_btn.configure(state="disabled")
                self.stop_btn.configure(state="normal")
                self.restart_btn.configure(state="normal")
            elif status == "stopped":
                self.status_label.configure(text="● STOPPED - Server not running", text_color=colors.ERROR)
                self.server_info_label.configure(text="Configure settings and click 'Start Server' to begin")
                self.start_btn.configure(state="normal")
                self.stop_btn.configure(state="disabled")
                self.restart_btn.configure(state="disabled")
            elif status == "error":
                self.status_label.configure(text="● ERROR - Server encountered an error", text_color=colors.ERROR)
                self.server_info_label.configure(text="Check configuration and logs for error details")
                self.start_btn.configure(state="normal")
                self.stop_btn.configure(state="disabled")
                self.restart_btn.configure(state="disabled")
        except Exception as e:
            logger.error(f"Error updating server status: {e}")

    # ------------------------------------------------------------------
    # Monitoring / statistics / signals
    # ------------------------------------------------------------------

    def start_monitoring(self):
        self.monitoring_active = True

        def monitor():
            while self.monitoring_active:
                try:
                    if self.server_manager.is_running():
                        stats = self.server_manager.get_server_stats()
                        self.update_statistics(stats)
                    self.poll_audit_log()
                    time.sleep(2)
                except Exception as e:
                    logger.error(f"Monitoring error: {e}")
                    time.sleep(5)

        self.monitor_thread = threading.Thread(target=monitor, daemon=True)
        self.monitor_thread.start()

    def stop_monitoring(self):
        self.monitoring_active = False

    def update_statistics(self, stats: dict):
        try:
            if "connections" in self.stat_values:
                self.stat_values["connections"].configure(text=str(stats.get("active_connections", 0)))
            if "requests" in self.stat_values:
                self.stat_values["requests"].configure(text=str(stats.get("total_requests", 0)))
            if "last_request" in self.stat_values:
                self.stat_values["last_request"].configure(text=stats.get("last_request_time") or "None")
            if "uptime" in self.stat_values:
                self.stat_values["uptime"].configure(text=stats.get("uptime", "Not running"))
        except Exception as e:
            logger.error(f"Error updating statistics: {e}")

    def poll_audit_log(self):
        """Tail the audit log for new Agent 3 decisions and surface them here.
        The Flask server (a separate process) writes one record per decision;
        we just read whatever is new since the last poll."""
        try:
            records = self.audit_store.read_all()
            new_records = records[self._audit_records_seen:]
            if not new_records:
                return

            for record in new_records:
                reasoning = record.llm_reasoning
                if record.guardrail_vetoed:
                    reasoning = f"{reasoning} [VETOED: {record.guardrail_veto_reason}]"
                self.add_signal({
                    "action": record.final_action,
                    "symbol": record.symbol,
                    "confidence": record.llm_confidence,
                    "reasoning": reasoning,
                    "timestamp": datetime.now().strftime("%H:%M:%S"),
                })

            self._audit_records_seen = len(records)
        except Exception as e:
            logger.error(f"Error polling audit log: {e}")

    def add_signal(self, record: dict):
        try:
            self._signal_records.insert(0, record)
            if len(self._signal_records) > MAX_SIGNAL_CHIPS:
                self._signal_records = self._signal_records[:MAX_SIGNAL_CHIPS]
            self._rebuild_signal_chips()
        except Exception as e:
            logger.error(f"Error adding signal to display: {e}")

    def clear_signals(self):
        self._signal_records = []
        self._rebuild_signal_chips()

    def __del__(self):
        self.stop_monitoring()
