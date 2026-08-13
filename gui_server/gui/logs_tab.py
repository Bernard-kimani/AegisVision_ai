"""
Logs & Monitoring Tab for AegisVision AI Trading Server GUI
Real-time log display with filtering and export functionality
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import logging
import threading
import time
import os
from datetime import datetime
from collections import deque

from gui.theme import colors, fonts, spacing, icons
from gui.theme.layout import divider

logger = logging.getLogger(__name__)

class LogsTab:
    """Logs and monitoring tab.

    Layout is a single wide pane (a log stream is inherently one wide
    content stream, unlike the other tabs) -- a compact filter bar on top,
    the log textbox filling all remaining space, a compact management bar
    on the bottom. No bordered cards; just hairline dividers between the
    three zones.
    """

    def __init__(self, parent_frame, server_manager):
        self.parent = parent_frame
        self.server_manager = server_manager
        
        # Log management
        self.log_buffer = deque(maxlen=1000)  # Keep last 1000 log entries
        self.monitoring_active = False
        self.monitor_thread = None
        self.log_file_path = None
        
        # Filter settings
        self.log_level_filter = "INFO"
        self.search_text = ""
        
        # UI elements
        self.logs_text = None
        self.level_menu = None
        self.search_entry = None
        self.auto_scroll_var = None
        
        self.create_logs_ui()
        self.setup_log_monitoring()
    
    def create_logs_ui(self):
        """Create logs monitoring interface"""

        # Main container -- flat, on the ground
        self.main_frame = ctk.CTkFrame(self.parent, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True)

        self.create_log_controls()
        divider(self.main_frame).pack(fill="x", pady=(0, spacing.SM))

        self.create_log_display()

        divider(self.main_frame).pack(fill="x", pady=(spacing.SM, 0))
        self.create_log_management()

    def create_log_controls(self):
        """Compact top bar: log level, search, clear/refresh, auto-scroll -- one row"""
        filter_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        filter_frame.pack(fill="x", pady=(0, spacing.SM))

        ctk.CTkLabel(filter_frame, text="Log Level:").pack(side="left", padx=(0, spacing.XS))

        self.level_var = ctk.StringVar(value="INFO")
        self.level_menu = ctk.CTkOptionMenu(
            filter_frame,
            variable=self.level_var,
            values=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            command=self.on_filter_change,
            width=110
        )
        self.level_menu.pack(side="left", padx=(0, spacing.LG))

        ctk.CTkLabel(filter_frame, text="Search:").pack(side="left", padx=(0, spacing.XS))

        self.search_var = ctk.StringVar()
        self.search_var.trace("w", self.on_search_change)
        self.search_entry = ctk.CTkEntry(
            filter_frame,
            textvariable=self.search_var,
            placeholder_text="Search in logs...",
            width=200
        )
        self.search_entry.pack(side="left", padx=(0, spacing.LG))

        # Auto-scroll option
        self.auto_scroll_var = ctk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            filter_frame, text="Auto-scroll", variable=self.auto_scroll_var
        ).pack(side="left", padx=(0, spacing.LG))

        ctk.CTkButton(filter_frame, text="Refresh", command=self.refresh_logs, width=90).pack(side="right", padx=(spacing.SM, 0))
        ctk.CTkButton(filter_frame, text="Clear Logs", command=self.clear_logs, width=100).pack(side="right")

    def create_log_display(self):
        """Main log display -- fills all remaining space, no card wrapper"""
        self.logs_text = ctk.CTkTextbox(
            self.main_frame,
            font=fonts.mono(size=11),
            wrap="none"
        )
        self.logs_text.pack(fill="both", expand=True)

        # Configure text tags for different log levels
        self.setup_log_colors()

        # Initial message
        self.logs_text.insert("1.0", "Server logs will appear here when the server is running...")

    def create_log_management(self):
        """Compact bottom bar: export/open/stats + log file info"""
        buttons_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        buttons_frame.pack(fill="x", pady=(spacing.SM, 0))

        ctk.CTkButton(buttons_frame, text="Export Logs", image=icons.download_icon(), compound="left", command=self.export_logs, width=130).pack(side="left", padx=(0, spacing.SM))
        ctk.CTkButton(buttons_frame, text="Open Log File", image=icons.folder_icon(), compound="left", command=self.open_log_file, width=130).pack(side="left", padx=(0, spacing.SM))
        ctk.CTkButton(buttons_frame, text="Log Statistics", image=icons.chart_icon(), compound="left", command=self.show_log_statistics, width=130).pack(side="left")

        self.log_info_label = ctk.CTkLabel(
            buttons_frame,
            text="Log file: Not available",
            font=fonts.caption(), text_color=colors.TEXT_SECONDARY,
        )
        self.log_info_label.pack(side="right")
    
    def setup_log_colors(self):
        """Setup color coding for different log levels"""
        # Note: CustomTkinter TextBox doesn't support text tags like regular tkinter Text
        # This is a limitation we'll work around by formatting the text itself
        pass
    
    def setup_log_monitoring(self):
        """Setup log file monitoring"""
        try:
            # Try to find the log file
            if hasattr(self.server_manager, 'get_log_file_path'):
                self.log_file_path = self.server_manager.get_log_file_path()
            else:
                # Default log file location
                log_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
                self.log_file_path = os.path.join(log_dir, 'orb_trading_server.log')
            
            if self.log_file_path:
                self.log_info_label.configure(text=f"Log file: {os.path.basename(self.log_file_path)}")
                self.start_monitoring()
                
        except Exception as e:
            logger.warning(f"Could not setup log monitoring: {e}")
    
    def start_monitoring(self):
        """Start monitoring the log file"""
        self.monitoring_active = True
        
        def monitor():
            last_size = 0
            while self.monitoring_active:
                try:
                    if os.path.exists(self.log_file_path):
                        current_size = os.path.getsize(self.log_file_path)
                        if current_size > last_size:
                            # New content added to log file
                            self.read_new_logs(last_size)
                            last_size = current_size
                    
                    time.sleep(1)  # Check every second
                    
                except Exception as e:
                    logger.error(f"Log monitoring error: {e}")
                    time.sleep(5)  # Longer delay on error
        
        self.monitor_thread = threading.Thread(target=monitor, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Stop log file monitoring"""
        self.monitoring_active = False
    
    def read_new_logs(self, from_position: int):
        """Read new log entries from file"""
        try:
            with open(self.log_file_path, 'r', encoding='utf-8') as f:
                f.seek(from_position)
                new_content = f.read()
                
                if new_content:
                    lines = new_content.strip().split('\n')
                    for line in lines:
                        if line.strip():
                            self.add_log_entry(line)
                            
        except Exception as e:
            logger.error(f"Error reading new logs: {e}")
    
    def add_log_entry(self, log_line: str):
        """Add a single log entry to display"""
        try:
            # Add to buffer
            self.log_buffer.append(log_line)
            
            # Check if line matches current filters
            if self.should_display_line(log_line):
                # Add to display
                self.logs_text.insert("end", log_line + "\n")
                
                # Auto-scroll if enabled
                if self.auto_scroll_var.get():
                    self.logs_text.see("end")
                    
        except Exception as e:
            logger.error(f"Error adding log entry: {e}")
    
    def should_display_line(self, log_line: str) -> bool:
        """Check if log line should be displayed based on filters"""
        try:
            # Level filter
            current_level = self.level_var.get()
            level_order = {"DEBUG": 0, "INFO": 1, "WARNING": 2, "ERROR": 3, "CRITICAL": 4}
            
            # Extract level from log line (assuming format: timestamp - name - LEVEL - message)
            line_level = None
            for level in level_order:
                if f"- {level} -" in log_line:
                    line_level = level
                    break
            
            if line_level and level_order.get(line_level, 0) < level_order.get(current_level, 1):
                return False
            
            # Search filter
            search_text = self.search_var.get().lower()
            if search_text and search_text not in log_line.lower():
                return False
            
            return True
            
        except Exception:
            return True  # Show line if filtering fails
    
    def on_filter_change(self, value):
        """Handle log level filter change"""
        self.refresh_display()
    
    def on_search_change(self, *args):
        """Handle search text change"""
        self.refresh_display()
    
    def refresh_display(self):
        """Refresh the log display with current filters"""
        try:
            # Clear current display
            self.logs_text.delete("1.0", "end")
            
            # Re-add filtered logs from buffer
            for log_line in self.log_buffer:
                if self.should_display_line(log_line):
                    self.logs_text.insert("end", log_line + "\n")
            
            # Auto-scroll to end
            if self.auto_scroll_var.get():
                self.logs_text.see("end")
                
        except Exception as e:
            logger.error(f"Error refreshing display: {e}")
    
    def clear_logs(self):
        """Clear the log display"""
        try:
            if messagebox.askyesno("Clear Logs", "Clear the log display? This won't delete the log file."):
                self.logs_text.delete("1.0", "end")
                self.log_buffer.clear()
                self.logs_text.insert("1.0", "Logs cleared. New logs will appear here...")
        except Exception as e:
            logger.error(f"Error clearing logs: {e}")
    
    def refresh_logs(self):
        """Refresh logs from file"""
        try:
            if os.path.exists(self.log_file_path):
                self.log_buffer.clear()
                self.logs_text.delete("1.0", "end")
                
                # Read entire log file
                with open(self.log_file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = content.split('\n')
                    
                    # Add last 1000 lines to buffer
                    for line in lines[-1000:]:
                        if line.strip():
                            self.log_buffer.append(line)
                
                # Refresh display with filters
                self.refresh_display()
                
            else:
                self.logs_text.delete("1.0", "end")
                self.logs_text.insert("1.0", "Log file not found. Start the server to generate logs.")
                
        except Exception as e:
            logger.error(f"Error refreshing logs: {e}")
            messagebox.showerror("Error", f"Failed to refresh logs: {e}")
    
    def export_logs(self):
        """Export logs to file"""
        try:
            file_path = filedialog.asksaveasfilename(
                title="Export Logs",
                defaultextension=".txt",
                filetypes=[
                    ("Text files", "*.txt"),
                    ("Log files", "*.log"),
                    ("All files", "*.*")
                ],
                initialname=f"orb_server_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(f"AegisVision AI Trading Server Logs Export\n")
                    f.write(f"Export Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Total Entries: {len(self.log_buffer)}\n")
                    f.write("=" * 60 + "\n\n")
                    
                    for log_entry in self.log_buffer:
                        f.write(log_entry + "\n")
                
                messagebox.showinfo("Success", f"Logs exported to {file_path}")
                
        except Exception as e:
            logger.error(f"Error exporting logs: {e}")
            messagebox.showerror("Error", f"Failed to export logs: {e}")
    
    def open_log_file(self):
        """Open the log file in default text editor"""
        try:
            if os.path.exists(self.log_file_path):
                os.startfile(self.log_file_path)  # Windows
            else:
                messagebox.showwarning("Warning", "Log file not found")
        except Exception as e:
            logger.error(f"Error opening log file: {e}")
            messagebox.showerror("Error", f"Failed to open log file: {e}")
    
    def show_log_statistics(self):
        """Show log statistics window"""
        try:
            # Count log entries by level
            level_counts = {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}
            total_entries = len(self.log_buffer)
            
            for log_entry in self.log_buffer:
                for level in level_counts:
                    if f"- {level} -" in log_entry:
                        level_counts[level] += 1
                        break
            
            # Create statistics message
            stats_message = f"Log Statistics:\n\n"
            stats_message += f"Total Entries: {total_entries}\n\n"
            
            for level, count in level_counts.items():
                percentage = (count / total_entries * 100) if total_entries > 0 else 0
                stats_message += f"{level}: {count} ({percentage:.1f}%)\n"
            
            if os.path.exists(self.log_file_path):
                file_size = os.path.getsize(self.log_file_path)
                stats_message += f"\nLog File Size: {file_size / 1024:.1f} KB"
                
                file_time = os.path.getmtime(self.log_file_path)
                file_time_str = datetime.fromtimestamp(file_time).strftime('%Y-%m-%d %H:%M:%S')
                stats_message += f"\nLast Modified: {file_time_str}"
            
            messagebox.showinfo("Log Statistics", stats_message)
            
        except Exception as e:
            logger.error(f"Error showing log statistics: {e}")
            messagebox.showerror("Error", f"Failed to generate log statistics: {e}")
    
    def __del__(self):
        """Cleanup when tab is destroyed"""
        self.stop_monitoring()