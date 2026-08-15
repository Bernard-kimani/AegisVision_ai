"""
AegisVision AI Trading Server - desktop shell entry point.

Launches the React frontend (gui_server/frontend) inside a pywebview
window. GUI-facing operations (config, server start/stop, strategies,
backtest, logs) are exposed to it via WebViewApi's js_api bridge - see
webview_api.py. The live trading Flask server (server/trading_server.py,
/health + /analyze for the MT5 EA) is unaffected: ServerManager still spawns
it in its own process exactly as before, just now triggered from the React
Controls page instead of a CustomTkinter button.
"""

import os
import sys
import logging

# Add server directory to Python path for imports
if getattr(sys, 'frozen', False):
    # Running as compiled EXE
    application_path = os.path.dirname(sys.executable)
else:
    # Running as Python script (development)
    application_path = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, os.path.join(application_path, 'server'))

try:
    import webview
except ImportError as e:
    print(f"pywebview not installed: {e}")
    print("Please install: pip install pywebview")
    sys.exit(1)

from config_manager import ConfigManager
from server_manager import ServerManager
from webview_api import WebViewApi


def setup_logging():
    """Set up logging configuration"""
    logs_dir = os.path.join(application_path, 'logs')
    os.makedirs(logs_dir, exist_ok=True)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(logs_dir, 'orb_trading_server.log')),
            logging.StreamHandler(sys.stdout)
        ]
    )

    # Silence noisy libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)


def frontend_url() -> str:
    """Dev mode (not frozen, AEGISVISION_DEV set): point at the Vite dev
    server for HMR while iterating on the UI. Otherwise: the built static
    frontend. In a frozen build, PyInstaller's bundled `datas` (read-only
    resources, incl. frontend/dist - see aegisvision_server.spec) are
    unpacked to sys._MEIPASS, NOT to the .exe's own directory - unlike
    application_path (used for persistent data: config/logs/storage_data),
    which deliberately stays next to the .exe so it survives between runs.
    Conflating the two here would 404 on every frozen launch."""
    if not getattr(sys, "frozen", False) and os.environ.get("AEGISVISION_DEV"):
        return "http://localhost:5173"
    bundle_dir = getattr(sys, "_MEIPASS", application_path) if getattr(sys, "frozen", False) else application_path
    return os.path.join(bundle_dir, "frontend", "dist", "index.html")


def main():
    """Main application entry point"""
    setup_logging()
    logger = logging.getLogger(__name__)

    try:
        logger.info("Starting AegisVision AI Trading Server...")

        if sys.platform == "win32":
            # Without this, Windows treats the process as a generic
            # "python.exe" host and shows the interpreter's own icon on the
            # taskbar button instead of the window's icon (set below via
            # webview.start(icon=...)) - this must run before that window is
            # created to take effect. Harmless no-op on non-Windows/if it fails.
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("AegisVisionAI.TradingServer")
            except Exception:
                pass

        config_manager = ConfigManager()
        server_manager = ServerManager(config_manager)
        api = WebViewApi(config_manager, server_manager)

        icon_path = os.path.join(application_path, 'assets', 'icon.ico')

        window = webview.create_window(
            "AegisVision AI Trading Server",
            url=frontend_url(),
            js_api=api,
            width=1200,
            height=800,
            min_size=(900, 600),
        )

        def on_closing():
            # Mirrors the old TradingServerGUI.on_closing(): don't leave the
            # Flask subprocess orphaned if the window closes while it's running.
            if server_manager.is_running():
                server_manager.stop_server()

        window.events.closing += on_closing

        webview.start(icon=icon_path if os.path.exists(icon_path) else None)

    except Exception as e:
        logger.error(f"Application error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")

        # Show error dialog if the webview window itself failed to launch
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("AegisVision Trading Server Error", f"Failed to start application:\n{e}")
        except Exception:
            print(f"Critical error: {e}")

        sys.exit(1)


if __name__ == "__main__":
    main()
