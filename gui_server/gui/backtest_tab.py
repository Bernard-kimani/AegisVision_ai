"""
Backtest Tab - runs the offline replay harness (backtest/extract_triggers.py,
backtest/replay_harness.py) as subprocesses and displays the before/after
(raw vs AI-filtered) performance comparison.

Runs as a subprocess rather than in-process: the replay harness makes real,
throttled (10-15s apart) Gemini calls over potentially hundreds of events, and
must not block the GUI's Tk mainloop or the live trading server if it happens
to be running at the same time.

Layout: left column = the two control forms (Extract / Run -- naturally
narrow), right column = the live replay log (wants vertical room), bottom
full-width row = the results comparison table (inherently a wide 3-column
table, kept full width).
"""

import json
import logging
import os
import subprocess
import sys
import threading
from tkinter import messagebox

import customtkinter as ctk

from gui.theme import colors, fonts, spacing
from gui.theme.layout import section

logger = logging.getLogger(__name__)

_GUI_SERVER_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_ROOT = os.path.dirname(_GUI_SERVER_ROOT)
_BACKTEST_DIR = os.path.join(_REPO_ROOT, "backtest")


class BacktestTab:
    def __init__(self, parent_frame, config_manager, status_callback):
        self.parent = parent_frame
        self.status_callback = status_callback
        self._running_process = None

        root = ctk.CTkFrame(self.parent, fg_color="transparent")
        root.pack(fill="both", expand=True)
        root.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(1, weight=2)
        root.grid_rowconfigure(0, weight=0)
        root.grid_rowconfigure(1, weight=1)

        left_col = ctk.CTkFrame(root, fg_color="transparent")
        left_col.grid(row=0, column=0, sticky="new", padx=(0, spacing.MD))

        right_col = ctk.CTkFrame(root, fg_color="transparent")
        right_col.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(spacing.MD, 0))

        bottom = ctk.CTkFrame(root, fg_color="transparent")
        bottom.grid(row=1, column=0, sticky="new", pady=(spacing.MD, 0))

        self._create_extract_section(left_col)
        self._create_run_section(left_col)
        self._create_log_section(right_col)
        self._create_results_section(bottom)

    # --- Section 1: extract trigger events ---

    def _create_extract_section(self, parent):
        content = section(parent, "1. Extract Historical Trigger Events")

        ctk.CTkLabel(content, text="Start Date (YYYY-MM-DD):").grid(row=0, column=0, padx=(0, spacing.SM), pady=spacing.XS, sticky="w")
        self.start_date_var = ctk.StringVar(value="2018-01-05")
        ctk.CTkEntry(content, textvariable=self.start_date_var, width=130).grid(row=0, column=1, pady=spacing.XS, sticky="w")

        ctk.CTkLabel(content, text="End Date (YYYY-MM-DD):").grid(row=1, column=0, padx=(0, spacing.SM), pady=spacing.XS, sticky="w")
        self.end_date_var = ctk.StringVar(value="2018-01-15")
        ctk.CTkEntry(content, textvariable=self.end_date_var, width=130).grid(row=1, column=1, pady=spacing.XS, sticky="w")

        ctk.CTkLabel(content, text="Interval (min):").grid(row=2, column=0, padx=(0, spacing.SM), pady=spacing.XS, sticky="w")
        self.interval_var = ctk.StringVar(value="60")
        ctk.CTkEntry(content, textvariable=self.interval_var, width=130).grid(row=2, column=1, pady=spacing.XS, sticky="w")

        ctk.CTkLabel(content, text="Max Events:").grid(row=3, column=0, padx=(0, spacing.SM), pady=spacing.XS, sticky="w")
        self.extract_max_events_var = ctk.StringVar(value="50")
        ctk.CTkEntry(content, textvariable=self.extract_max_events_var, width=130).grid(row=3, column=1, pady=spacing.XS, sticky="w")

        ctk.CTkButton(content, text="Extract Events", command=self.on_extract_events, width=160).grid(row=4, column=0, columnspan=2, pady=(spacing.SM, spacing.XS), sticky="w")

        self.extract_status_label = ctk.CTkLabel(content, text="No events extracted yet.", font=fonts.caption(), text_color=colors.TEXT_SECONDARY)
        self.extract_status_label.grid(row=5, column=0, columnspan=2, sticky="w")

    # --- Section 2: run replay ---

    def _create_run_section(self, parent):
        content = section(parent, "2. Run Backtest Replay (real, throttled AI calls)", pady=(0, spacing.LG))

        ctk.CTkLabel(content, text="Throttle (sec/call):").grid(row=0, column=0, padx=(0, spacing.SM), pady=spacing.XS, sticky="w")
        self.throttle_var = ctk.StringVar(value="12")
        ctk.CTkEntry(content, textvariable=self.throttle_var, width=100).grid(row=0, column=1, pady=spacing.XS, sticky="w")

        ctk.CTkLabel(content, text="Min Confidence:").grid(row=1, column=0, padx=(0, spacing.SM), pady=spacing.XS, sticky="w")
        self.bt_min_confidence_var = ctk.StringVar(value="60")
        ctk.CTkEntry(content, textvariable=self.bt_min_confidence_var, width=100).grid(row=1, column=1, pady=spacing.XS, sticky="w")

        ctk.CTkLabel(content, text="Min Risk:Reward:").grid(row=2, column=0, padx=(0, spacing.SM), pady=spacing.XS, sticky="w")
        self.bt_min_rr_var = ctk.StringVar(value="1.2")
        ctk.CTkEntry(content, textvariable=self.bt_min_rr_var, width=100).grid(row=2, column=1, pady=spacing.XS, sticky="w")

        self.run_btn = ctk.CTkButton(
            content, text="Run Backtest", command=self.on_run_backtest, width=160,
            fg_color=colors.SUCCESS, hover_color=colors.SUCCESS,
        )
        self.run_btn.grid(row=3, column=0, columnspan=2, pady=(spacing.SM, spacing.XS), sticky="w")

        self.progress_bar = ctk.CTkProgressBar(content, width=220)
        self.progress_bar.set(0)
        self.progress_bar.grid(row=4, column=0, columnspan=2, pady=spacing.XS, sticky="w")

        self.progress_label = ctk.CTkLabel(content, text="Not started", font=fonts.caption(), text_color=colors.TEXT_SECONDARY)
        self.progress_label.grid(row=5, column=0, columnspan=2, sticky="w")

    # --- Section 3: live log ---

    def _create_log_section(self, parent):
        content = section(parent, "Replay Log")

        self.log_text = ctk.CTkTextbox(content, font=fonts.mono(size=11))
        self.log_text.pack(fill="both", expand=True)

    # --- Section 4: results ---

    def _create_results_section(self, parent):
        content = section(parent, "3. Results: Raw vs. AI-Filtered", pady=(0, 0))

        self.results_frame = ctk.CTkFrame(content, fg_color="transparent")
        self.results_frame.pack(fill="x")

        self.results_placeholder = ctk.CTkLabel(self.results_frame, text="Run a backtest to see results here.", text_color=colors.TEXT_SECONDARY)
        self.results_placeholder.pack(anchor="w", pady=spacing.SM)

    # --- Actions ---

    def _append_log(self, text: str):
        self.log_text.insert("end", text if text.endswith("\n") else text + "\n")
        self.log_text.see("end")

    def on_extract_events(self):
        self.extract_status_label.configure(text="Extracting... (loading historical CSV, may take ~30-60s)")
        self._append_log("Starting trigger extraction...")

        def run():
            script = os.path.join(_BACKTEST_DIR, "extract_triggers.py")
            args = [
                sys.executable, script,
                "--start-date", self.start_date_var.get(),
                "--end-date", self.end_date_var.get(),
                "--interval-minutes", self.interval_var.get(),
                "--max-events", self.extract_max_events_var.get(),
            ]
            try:
                result = subprocess.run(args, capture_output=True, text=True, cwd=_BACKTEST_DIR, timeout=300)
                for line in (result.stdout + result.stderr).splitlines():
                    self._append_log(line)
                if result.returncode == 0:
                    self.extract_status_label.configure(text="Events extracted - see log above.")
                    self.status_callback("Trigger events extracted")
                else:
                    self.extract_status_label.configure(text="Extraction failed - see log.")
            except Exception as e:
                self._append_log(f"Extraction error: {e}")
                self.extract_status_label.configure(text="Extraction failed - see log.")

        threading.Thread(target=run, daemon=True).start()

    def on_run_backtest(self):
        if self._running_process is not None:
            messagebox.showwarning("Already Running", "A backtest is already in progress.")
            return

        events_path = os.path.join(_BACKTEST_DIR, "trigger_events.json")
        if not os.path.exists(events_path):
            messagebox.showwarning("No Events", "Extract trigger events first (step 1).")
            return

        self.run_btn.configure(state="disabled", text="Running...")
        self.progress_bar.set(0)
        self.progress_label.configure(text="Starting...")
        self._append_log("Starting backtest replay...")

        def run():
            script = os.path.join(_BACKTEST_DIR, "replay_harness.py")
            args = [
                sys.executable, script,
                "--throttle-seconds", self.throttle_var.get(),
                "--min-confidence", self.bt_min_confidence_var.get(),
                "--min-risk-reward", self.bt_min_rr_var.get(),
            ]
            try:
                self._running_process = subprocess.Popen(
                    args, cwd=_BACKTEST_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                )
                for line in self._running_process.stdout:
                    line = line.rstrip()
                    self._append_log(line)
                    self._update_progress_from_line(line)

                self._running_process.wait()
                returncode = self._running_process.returncode
                self._running_process = None

                if returncode == 0:
                    self.progress_label.configure(text="Complete")
                    self.progress_bar.set(1.0)
                    self.status_callback("Backtest complete")
                    self._load_and_display_report()
                else:
                    self.progress_label.configure(text="Failed - see log")
                    self.status_callback("Backtest failed")
            except Exception as e:
                self._append_log(f"Backtest error: {e}")
                self.progress_label.configure(text="Error - see log")
                self._running_process = None
            finally:
                self.run_btn.configure(state="normal", text="Run Backtest")

        threading.Thread(target=run, daemon=True).start()

    def _update_progress_from_line(self, line: str):
        # Lines look like: "[3/50] 2018-01-07T04:00:00 verdict=ACCEPT conf=85 guardrail=BUY"
        try:
            if line.startswith("[") and "/" in line.split("]")[0]:
                fraction = line[1:line.index("]")]
                current, total = fraction.split("/")
                current, total = int(current), int(total)
                self.progress_bar.set(current / total if total else 0)
                self.progress_label.configure(text=f"{current}/{total} events")
        except Exception:
            pass  # not a progress line, ignore

    def _load_and_display_report(self):
        report_path = os.path.join(_BACKTEST_DIR, "backtest_report.json")
        if not os.path.exists(report_path):
            return
        try:
            with open(report_path) as f:
                report = json.load(f)
        except Exception as e:
            self._append_log(f"Failed to load report: {e}")
            return

        for widget in self.results_frame.winfo_children():
            widget.destroy()

        raw = report.get("raw", {})
        ai = report.get("ai_filtered", {})

        headers = ["Metric", "Raw (every trigger)", "AI-Filtered"]
        rows = [
            ("Total Trades", raw.get("total_trades", 0), ai.get("total_trades", 0)),
            ("Win Rate", f"{raw.get('win_rate', 0):.1%}", f"{ai.get('win_rate', 0):.1%}"),
            ("Profit Factor", f"{raw.get('profit_factor', 0):.2f}", f"{ai.get('profit_factor', 0):.2f}"),
            ("Total P&L (price units)", f"{raw.get('total_pnl', 0):.2f}", f"{ai.get('total_pnl', 0):.2f}"),
            ("Max Drawdown", f"{raw.get('max_drawdown', 0):.2f}", f"{ai.get('max_drawdown', 0):.2f}"),
            ("Expectancy/Trade", f"{raw.get('expectancy', 0):.3f}", f"{ai.get('expectancy', 0):.3f}"),
        ]

        for col, header in enumerate(headers):
            ctk.CTkLabel(self.results_frame, text=header, font=ctk.CTkFont(weight="bold")).grid(row=0, column=col, padx=spacing.MD, pady=(0, spacing.XS), sticky="w")

        for r, (label, raw_val, ai_val) in enumerate(rows, start=1):
            ctk.CTkLabel(self.results_frame, text=label).grid(row=r, column=0, padx=spacing.MD, pady=spacing.XS // 2, sticky="w")
            ctk.CTkLabel(self.results_frame, text=str(raw_val)).grid(row=r, column=1, padx=spacing.MD, pady=spacing.XS // 2, sticky="w")
            ctk.CTkLabel(self.results_frame, text=str(ai_val)).grid(row=r, column=2, padx=spacing.MD, pady=spacing.XS // 2, sticky="w")

        skipped = report.get("events_skipped", 0)
        total = report.get("events_total", 0)
        note = ctk.CTkLabel(
            self.results_frame,
            text=f"({skipped}/{total} events skipped - insufficient warm-up data)",
            font=fonts.caption(), text_color=colors.TEXT_SECONDARY,
        )
        note.grid(row=len(rows) + 1, column=0, columnspan=3, padx=spacing.MD, pady=(spacing.XS, spacing.SM), sticky="w")
