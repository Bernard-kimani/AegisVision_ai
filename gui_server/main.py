"""
AegisVision AI Trading Server - GUI Application
Main entry point for the GUI-based trading server executable
"""

import os
import sys
import logging
from pathlib import Path

# Add server directory to Python path for imports
if getattr(sys, 'frozen', False):
    # Running as compiled EXE
    application_path = os.path.dirname(sys.executable)
else:
    # Running as Python script (development)
    application_path = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, os.path.join(application_path, 'server'))

try:
    import customtkinter as ctk
except ImportError as e:
    print(f"CustomTkinter not installed: {e}")
    print("Please install: pip install customtkinter")
    sys.exit(1)

try:
    from gui.main_window import TradingServerGUI
except ImportError as e:
    print(f"GUI import error: {e}")
    print("Check that all required files are in place.")
    sys.exit(1)

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

def main():
    """Main application entry point"""
    setup_logging()
    logger = logging.getLogger(__name__)
    
    try:
        # Appearance mode + the AegisVision custom theme are applied inside
        # TradingServerGUI.setup_application() so theme loading lives in one place.
        logger.info("Starting AegisVision AI Trading Server GUI...")
        
        # Create and run the GUI application
        app = TradingServerGUI()
        app.run()
        
    except Exception as e:
        logger.error(f"Application error: {e}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Show error dialog if GUI fails
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("AegisVision Trading Server Error", f"Failed to start application:\n{e}")
        except:
            print(f"Critical error: {e}")
        
        sys.exit(1)

if __name__ == "__main__":
    main()