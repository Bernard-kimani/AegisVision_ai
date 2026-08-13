"""
Main GUI Window for AegisVision AI Trading Server
Provides tabbed interface for configuration, server control, and monitoring
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
import threading
import logging
import os
import sys

from gui.controls_tab import ControlsTab
from gui.logs_tab import LogsTab
from gui.strategies_tab import StrategiesTab
from gui.backtest_tab import BacktestTab
from gui.theme import colors, fonts, spacing, icons, section, divider
from server_manager import ServerManager
from config_manager import ConfigManager

logger = logging.getLogger(__name__)

DRAWER_WIDTH = 300
THEME_MODES = ["Dark", "Light", "System"]

class TradingServerGUI:
    """Main GUI application window"""
    
    def __init__(self):
        self.root = None
        self.server_manager = None
        self.config_manager = None
        self.tabs = {}
        
        # Application info
        self.app_title = "AegisVision AI Trading Server"
        self.app_version = "v1.0"
        
        self.setup_application()
    
    def setup_application(self):
        """Initialize the main application window"""
        try:
            # Managers are constructed before any Tk widget exists so the
            # persisted theme preference is available for set_appearance_mode()
            self.config_manager = ConfigManager()
            self.server_manager = ServerManager(self.config_manager)

            # Apply the AegisVision custom theme before any widget is created
            theme_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "theme", "aegisvision_theme.json")
            ctk.set_appearance_mode(self.config_manager.get_theme())
            if os.path.exists(theme_path):
                ctk.set_default_color_theme(theme_path)
            else:
                logger.warning(f"Theme file not found at {theme_path}, falling back to default theme")

            # Create main window
            self.root = ctk.CTk()
            self.root.title(f"{self.app_title} {self.app_version}")
            self.root.geometry("1000x700")
            self.root.minsize(800, 600)

            self.set_window_icon()

            # Create GUI components
            self.create_header()
            self.create_main_content()
            self.create_status_bar()
            self.create_settings_drawer()

            # Bind window close event
            self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

            logger.info("GUI application initialized successfully")

        except Exception as e:
            logger.error(f"Failed to setup application: {e}")
            raise

    def set_window_icon(self):
        """Set the taskbar/title-bar icon, with a cross-platform fallback.

        assets/icon.ico is Windows-only (iconbitmap requires that format);
        assets/icon.png is the fallback used everywhere else via iconphoto().
        Both are swappable placeholders -- see assets/generate_placeholder_icon.py.
        """
        ico_path = self.get_asset_path("icon.ico")
        png_path = self.get_asset_path("icon.png")

        if sys.platform == "win32" and os.path.exists(ico_path):
            try:
                self.root.iconbitmap(ico_path)
                return
            except Exception as e:
                logger.warning(f"Could not set .ico window icon: {e}")

        if os.path.exists(png_path):
            try:
                # Keep a live reference -- Tk garbage-collects a PhotoImage
                # with no Python-side reference, silently dropping the icon.
                self._icon_photo = tk.PhotoImage(file=png_path)
                self.root.iconphoto(True, self._icon_photo)
            except Exception as e:
                logger.warning(f"Could not set window icon: {e}")
    
    def create_header(self):
        """Create application header -- flat, on the ground, no card border"""
        header_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        header_frame.pack(fill="x", padx=spacing.LG, pady=(spacing.SM, spacing.XS))

        # Title label
        title_label = ctk.CTkLabel(
            header_frame,
            text=f"{self.app_title} {self.app_version}",
            font=fonts.heading(),
        )
        title_label.pack(side="left")

        # Description label
        desc_label = ctk.CTkLabel(
            header_frame,
            text="Professional AI-Based Trading Signal Server",
            font=fonts.caption(),
            text_color=colors.TEXT_SECONDARY,
        )
        desc_label.pack(side="left", padx=(spacing.MD, 0))

        # Profile / settings, far right -- opens the settings drawer.
        # NOTE: text=" " (not "") is deliberate -- customtkinter's CTkButton
        # only creates its internal _text_label when text is non-empty
        # (ctk_button.py line 222), and the root window's global click-to-
        # focus handler unconditionally calls _text_label.focus_set() on
        # every click anywhere in the window. With text="", that crashes
        # with AttributeError on every single click, silently (inside a Tk
        # callback), which is exactly why the button appeared to do nothing.
        self.profile_btn = ctk.CTkButton(
            header_frame, text=" ", image=icons.profile_icon(),
            width=36, height=36, corner_radius=spacing.RADIUS_PILL,
            fg_color="transparent", hover_color=colors.SURFACE_ALT,
            command=self.toggle_settings_drawer,
        )
        self.profile_btn.pack(side="right")

    def on_theme_change(self, mode: str):
        """Switch appearance mode live and persist the choice"""
        try:
            ctk.set_appearance_mode(mode.lower())
            self.config_manager.set_theme(mode.lower())
        except Exception as e:
            logger.error(f"Error switching theme: {e}")

    # ------------------------------------------------------------------
    # Settings drawer -- profile icon opens a sideways panel; theme choice
    # is the first setting, with room to grow (profile info, etc. later).
    # ------------------------------------------------------------------

    def create_settings_drawer(self):
        self.drawer_open = False
        # SURFACE sits very close to GROUND by design (see tokens.py), so
        # without an explicit edge the opened drawer was nearly invisible --
        # a visible divider-colored border is what actually makes it read as
        # a distinct panel instead of "the click did nothing".
        self.drawer_frame = ctk.CTkFrame(
            self.root, fg_color=colors.SURFACE, corner_radius=0,
            border_width=2, border_color=colors.DIVIDER,
            width=DRAWER_WIDTH, height=self.root.winfo_height() or 700,
        )

        inner = ctk.CTkFrame(self.drawer_frame, fg_color="transparent")
        inner.pack(fill="both", expand=True, padx=spacing.MD, pady=spacing.MD)

        top_row = ctk.CTkFrame(inner, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, spacing.SM))
        ctk.CTkLabel(top_row, text="Settings", font=fonts.section()).pack(side="left")
        ctk.CTkButton(
            top_row, text=" ", image=icons.close_icon(), width=28, height=28,
            fg_color="transparent", hover_color=colors.SURFACE_ALT,
            command=self.toggle_settings_drawer,
        ).pack(side="right")

        divider(inner).pack(fill="x", pady=(0, spacing.SM))

        appearance_content = section(inner, "Appearance")
        self.theme_toggle = ctk.CTkSegmentedButton(
            appearance_content, values=THEME_MODES, command=self.on_theme_change,
        )
        current_mode = self.config_manager.get_theme().capitalize()
        self.theme_toggle.set(current_mode if current_mode in THEME_MODES else "Dark")
        self.theme_toggle.pack(fill="x")

    def toggle_settings_drawer(self):
        logger.info(f"Profile button clicked -- toggling settings drawer (currently open={self.drawer_open})")
        self._animate_drawer(opening=not self.drawer_open)
        self.drawer_open = not self.drawer_open
        logger.info(f"Settings drawer is now open={self.drawer_open}")

    def _animate_drawer(self, opening: bool, steps: int = 10, interval_ms: int = 12):
        # NOTE: CTk widgets reject width/height passed to place() -- they
        # must be set via configure()/the constructor. Passing them to
        # place() raises ValueError, which Tkinter silently swallows inside
        # an after()-scheduled callback (prints to a console the user never
        # sees) -- that silent failure is what made the drawer look like it
        # "did nothing" when clicked.
        self.root.update_idletasks()
        root_w = self.root.winfo_width()
        root_h = self.root.winfo_height()
        self.drawer_frame.configure(height=root_h)
        start_x = (root_w - DRAWER_WIDTH) if not opening else root_w
        target_x = root_w if not opening else (root_w - DRAWER_WIDTH)

        if opening:
            self.drawer_frame.place(x=start_x, y=0)
            self.drawer_frame.lift()

        def step(i=0):
            if i > steps:
                if not opening:
                    self.drawer_frame.place_forget()
                return
            t = i / steps
            x = int(start_x + (target_x - start_x) * t)
            self.drawer_frame.place(x=x, y=0)
            self.root.after(interval_ms, lambda: step(i + 1))

        step()

    def create_main_content(self):
        """Create main tabbed interface"""
        # Create tabview -- pushed close under the header (no top pady) per
        # the "push the tabs higher" request.
        self.tabview = ctk.CTkTabview(self.root, command=self._on_tab_changed)
        self.tabview.pack(fill="both", expand=True, padx=spacing.LG, pady=(0, spacing.SM))

        # Add tabs
        controls_tab = self.tabview.add("Controls")
        strategies_tab = self.tabview.add("Strategies")
        backtest_tab = self.tabview.add("Backtest")
        logs_tab = self.tabview.add("Logs & Monitoring")

        # Initialize tab content
        self.tabs["controls"] = ControlsTab(controls_tab, self.config_manager, self.server_manager, self.update_status)
        self.tabs["strategies"] = StrategiesTab(strategies_tab, self.config_manager, self.update_status)
        self.tabs["backtest"] = BacktestTab(backtest_tab, self.config_manager, self.update_status)
        self.tabs["logs"] = LogsTab(logs_tab, self.server_manager)

        # Set default tab
        self.tabview.set("Controls")
        self._space_out_tabs()
        self._on_tab_changed()

    def _space_out_tabs(self, gap: int = 6):
        """Add a visible gap between tab segments -- CTkTabview's internal
        segmented button grids them flush with no spacing option, so this
        reaches into its private _buttons_dict (a well-known workaround;
        wrapped in try/except in case a future customtkinter version renames
        these internals)."""
        try:
            buttons = list(self.tabview._segmented_button._buttons_dict.values())
            last = len(buttons) - 1
            for i, btn in enumerate(buttons):
                btn.grid_configure(padx=(0 if i == 0 else gap, 0 if i == last else 0))
        except Exception as e:
            logger.warning(f"Could not space out tabs (customtkinter internals changed?): {e}")

    def _on_tab_changed(self):
        """Bold the selected tab's label, normal-weight the rest -- CTkTabview
        has no built-in per-state font, so this restyles the segmented
        button's own button widgets directly (same internals as above)."""
        try:
            current = self.tabview.get()
            for name, btn in self.tabview._segmented_button._buttons_dict.items():
                btn.configure(font=ctk.CTkFont(size=13, weight="bold" if name == current else "normal"))
        except Exception as e:
            logger.warning(f"Could not restyle selected tab (customtkinter internals changed?): {e}")

    def create_status_bar(self):
        """Create bottom status bar -- flat, thin divider, no card border"""
        divider(self.root).pack(fill="x", padx=spacing.LG)

        self.status_frame = ctk.CTkFrame(self.root, fg_color="transparent")
        self.status_frame.pack(fill="x", padx=spacing.LG, pady=(spacing.XS, spacing.SM))

        # Status label
        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="Ready - Configure your settings and start the server",
            font=fonts.caption(),
            text_color=colors.TEXT_SECONDARY,
        )
        self.status_label.pack(side="left")

        # Server status indicator
        self.status_indicator = ctk.CTkLabel(
            self.status_frame,
            text="● STOPPED",
            text_color=colors.ERROR,
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        self.status_indicator.pack(side="right")

    def update_status(self, message: str, server_status: str = None):
        """Update status bar message and server status"""
        try:
            if self.status_label:
                self.status_label.configure(text=message)

            if server_status and self.status_indicator:
                if server_status.lower() == "running":
                    self.status_indicator.configure(text="● RUNNING", text_color=colors.SUCCESS)
                elif server_status.lower() == "stopped":
                    self.status_indicator.configure(text="● STOPPED", text_color=colors.ERROR)
                elif server_status.lower() == "error":
                    self.status_indicator.configure(text="● ERROR", text_color=colors.WARNING)

        except Exception as e:
            logger.error(f"Error updating status: {e}")
    
    def get_asset_path(self, filename: str) -> str:
        """Get path to asset file"""
        if getattr(sys, 'frozen', False):
            # Running as compiled EXE
            base_path = os.path.dirname(sys.executable)
        else:
            # Running as Python script
            base_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
        return os.path.join(base_path, "assets", filename)
    
    def on_closing(self):
        """Handle application closing"""
        try:
            # Stop server if running
            if self.server_manager and self.server_manager.is_running():
                logger.info("Stopping server before closing application...")
                self.server_manager.stop_server()
            
            # Close application
            logger.info("Closing AegisVision AI Trading Server GUI")
            self.root.quit()
            self.root.destroy()
            
        except Exception as e:
            logger.error(f"Error during application shutdown: {e}")
            # Force close if error
            self.root.quit()
    
    def run(self):
        """Start the GUI application"""
        try:
            logger.info("Starting GUI main loop...")
            self.root.mainloop()
        except Exception as e:
            logger.error(f"Error in GUI main loop: {e}")
            raise