"""
Server Manager for AegisVision AI Trading Server
Handles Flask server lifecycle, monitoring, and status management
"""

import logging
import threading
import time
import sys
import os
import requests
from datetime import datetime, timedelta
from typing import Dict, Optional, Any
import subprocess
import signal
import multiprocessing

logger = logging.getLogger(__name__)

def run_flask_server_process(config: Dict):
    """
    Run Flask server in a separate process.
    Must be a top-level function for multiprocessing pickle compatibility on Windows.
    """
    try:
        # Import and initialize the Flask app
        # We need to set the path so it can find the server module
        current_dir = os.path.dirname(os.path.abspath(__file__))
        if current_dir not in sys.path:
            sys.path.insert(0, current_dir)
        
        # Configure logging for the child process
        # We need to re-configure logging because we are in a new process
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler(os.path.join(current_dir, 'logs', 'orb_trading_server.log')),
                logging.StreamHandler(sys.stdout)
            ]
        )
        
        # Silence noisy libraries in the child process too
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        logging.getLogger("werkzeug").setLevel(logging.WARNING)

        from server.trading_server import create_app
        
        child_logger = logging.getLogger("server_process")
        
        # Debug: Log configuration (safely)
        child_logger.info(f"Server config - LLM Provider: {config.get('llm', {}).get('provider', 'None')}")
        child_logger.info(f"Server config - LLM Model: {config.get('llm', {}).get('model', 'None')}")
        api_key = config.get('llm', {}).get('api_key', '')
        if api_key:
            child_logger.info(f"Server config - API Key: {api_key[:10]}...{api_key[-5:] if len(api_key) > 15 else '***'}")
        else:
            child_logger.warning("Server config - API Key: EMPTY!")
        
        # Create Flask app with configuration
        flask_app = create_app(config)
        
        # Get server settings from nested config
        host = config["server"]["host"]
        port = int(config["server"]["port"])
        debug = config["server"]["debug"]
        
        child_logger.info(f"Starting Flask server process on {host}:{port}")
        
        # Run Flask app
        # threaded=True is default, processes=1 is default
        flask_app.run(
            host=host,
            port=port,
            debug=debug,
            use_reloader=False,  # Disable reloader in production
            threaded=True
        )
        
    except Exception as e:
        print(f"CRITICAL: Flask server process failed: {e}")
        import traceback
        traceback.print_exc()

class ServerManager:
    """Manages the Flask trading server lifecycle using multiprocess"""
    
    def __init__(self, config_manager):
        self.config_manager = config_manager
        self.server_process: Optional[multiprocessing.Process] = None
        self.is_server_running = False
        self.start_time = None
        
        # Statistics tracking
        self.stats = {
            "total_requests": 0,
            "last_request_time": None,
            "active_connections": 0,
            "uptime": "Not running",
            "llm_provider": "Not configured",
            "llm_model": ""
        }
        
    def start_server(self) -> bool:
        """Start the Flask trading server in a separate process"""
        try:
            if self.is_running():
                logger.warning("Server is already running")
                return False
            
            # Get current configuration in flat format for validation
            config = self.config_manager.get_flat_config()
            
            # Validate configuration
            if not self.validate_config(config):
                logger.error("Invalid configuration - cannot start server")
                return False
            
            # Get nested config for the server
            nested_config = self.config_manager.get_current_config()
            
            # Start server in separate PROCESS (not thread) for reliable termination
            self.server_process = multiprocessing.Process(
                target=run_flask_server_process, 
                args=(nested_config,), 
                daemon=True
            )
            self.server_process.start()
            
            # Wait for server to become responsive
            logger.info("Waiting for server to initialize...")
            start_timeout = 30  # seconds (increased to allow for slow initialization)
            
            for i in range(start_timeout * 2):  # Check every 0.5 seconds
                # Check if process died immediately
                if not self.server_process.is_alive():
                    logger.error("Server process died immediately!")
                    self.server_process = None
                    return False
                
                # Try to hit health endpoint
                if self.is_server_responsive():
                    logger.info(f"Server started successfully (pid={self.server_process.pid})")
                    self.is_server_running = True
                    self.start_time = datetime.now()
                    return True
                
                time.sleep(0.5)
            
            logger.error("Server failed to start within timeout (process is alive but not responsive)")
            # Cleanup hanging process
            self.stop_server()
            return False
            
        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def stop_server(self) -> bool:
        """Stop the Flask trading server"""
        try:
            if not self.server_process:
                logger.warning("Server process is not set")
                self.is_server_running = False
                return True
            
            if self.server_process.is_alive():
                logger.info(f"Terminating server process (pid={self.server_process.pid})...")
                self.server_process.terminate()
                
                # Wait for it to die
                self.server_process.join(timeout=3)
                
                # Force kill if still alive
                if self.server_process.is_alive():
                    logger.warning("Server process did not terminate gracefully, force killing...")
                    self.server_process.kill()
                    self.server_process.join()
            
            # Reset state
            self.server_process = None
            self.is_server_running = False
            self.start_time = None
            
            logger.info("Server stopped successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to stop server: {e}")
            return False
    
    def restart_server(self) -> bool:
        """Restart the Flask trading server"""
        try:
            logger.info("Restarting server...")
            if self.is_running():
                self.stop_server()
                time.sleep(1)  # Brief pause
            
            return self.start_server()
            
        except Exception as e:
            logger.error(f"Failed to restart server: {e}")
            return False

    def validate_config(self, config: Dict) -> bool:
        """Validate server configuration"""
        try:
            # Never log the raw config - it carries the plaintext API key,
            # and this log file is user-readable (and tail-able/exportable
            # from the GUI's own Logs tab).
            safe_config = {**config, "api_key": "***" if config.get("api_key") else "(empty)"}
            logger.info(f"Validating config: {safe_config}")
            
            # Check required fields
            required_fields = ["host", "port", "llm_provider", "api_key"]
            for field in required_fields:
                if not config.get(field):
                    logger.error(f"Missing required configuration: {field}")
                    logger.error(f"Available config keys: {list(config.keys())}")
                    return False
            
            # Validate port
            try:
                port = int(config["port"])
                if port < 1 or port > 65535:
                    logger.error("Port must be between 1 and 65535")
                    return False
            except ValueError:
                logger.error("Port must be a valid number")
                return False
            
            # Validate LLM provider
            valid_providers = ["openai", "anthropic", "gemini"]
            if config["llm_provider"] not in valid_providers:
                logger.error(f"Invalid LLM provider: {config['llm_provider']}")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Configuration validation error: {e}")
            return False
    
    def is_running(self) -> bool:
        """Check if server process is running"""
        if self.server_process and self.server_process.is_alive():
            return True
        self.is_server_running = False
        return False
        
    def is_server_responsive(self) -> bool:
        """Check if server is responding to HTTP requests"""
        try:
            config = self.config_manager.get_flat_config()
            host = config.get("host", "127.0.0.1")
            port = config.get("port", "8080")
            
            url = f"http://{host}:{port}/health"
            response = requests.get(url, timeout=1)  # Short timeout for quick checks
            
            return response.status_code == 200
        except:
            return False
    
    def health_check(self) -> Optional[Dict]:
        """Perform server health check"""
        try:
            if not self.is_running():
                return None
            
            config = self.config_manager.get_flat_config()
            host = config.get("host", "127.0.0.1")
            port = config.get("port", "8080")
            
            url = f"http://{host}:{port}/health"
            response = requests.get(url, timeout=2)
            
            if response.status_code == 200:
                return response.json()
            else:
                return {"status": "error", "code": response.status_code}
                
        except requests.exceptions.ConnectionError:
            # Server is running but connection failed (maybe starting up?)
            return {"status": "connection_error"}
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return {"status": "error", "message": str(e)}
    
    def get_server_stats(self) -> Dict:
        """Get server statistics"""
        try:
            # Update uptime
            if self.is_running() and self.start_time:
                uptime_delta = datetime.now() - self.start_time
                hours, remainder = divmod(uptime_delta.total_seconds(), 3600)
                minutes, seconds = divmod(remainder, 60)
                self.stats["uptime"] = f"{int(hours):02d}:{int(minutes):02d}:{int(seconds):02d}"
            else:
                self.stats["uptime"] = "Not running"
            
            # Update LLM provider info
            config = self.config_manager.get_flat_config()
            self.stats["llm_provider"] = config.get("llm_provider", "Not configured")
            model = config.get("model", "")
            
            # Auto-update old model names for display
            if model == "gemini-1.5-flash":
                model = "gemini-1.5-flash-latest"
            elif model == "gemini-2.0-flash-exp":
                model = "gemini-2.0-flash-exp"
            
            self.stats["llm_model"] = model
            
            # Try to get real-time stats from server
            if self.is_running():
                try:
                    health_info = self.health_check()
                    if health_info and health_info.get("status") == "healthy":
                        # Extract additional stats if available
                        self.stats["active_connections"] = health_info.get("active_connections", 0)
                except Exception as e:
                    pass
            
            return self.stats.copy()
            
        except Exception as e:
            logger.error(f"Error getting server stats: {e}")
            return self.stats.copy()
    
    def get_log_file_path(self) -> Optional[str]:
        """Get path to server log file"""
        try:
            # Default log file location
            logs_dir = os.path.join(os.path.dirname(__file__), 'logs')
            log_file = os.path.join(logs_dir, 'orb_trading_server.log')
            
            if os.path.exists(log_file):
                return log_file
            else:
                # Try alternative locations
                alt_paths = [
                    os.path.join(os.getcwd(), 'logs', 'orb_trading_server.log'),
                    os.path.join(os.path.expanduser('~'), '.orb_trading', 'logs', 'server.log')
                ]
                
                for path in alt_paths:
                    if os.path.exists(path):
                        return path
                
                return log_file  # Return default even if doesn't exist
                
        except Exception as e:
            logger.error(f"Error getting log file path: {e}")
            return None
    
    def get_server_url(self) -> str:
        """Get server URL"""
        config = self.config_manager.get_flat_config()
        host = config.get("host", "127.0.0.1")
        port = config.get("port", "8080")
        return f"http://{host}:{port}"
    
    def export_server_config(self, file_path: str):
        """Export server configuration"""
        try:
            config = self.config_manager.get_current_config()
            
            # Remove sensitive information for export
            export_config = config.copy()
            if "api_key" in export_config:
                export_config["api_key"] = "*" * 20  # Mask API key
            
            import json
            with open(file_path, 'w') as f:
                json.dump(export_config, f, indent=2)
                
            logger.info(f"Server configuration exported to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to export server config: {e}")
            return False
    
    def __del__(self):
        """Cleanup when manager is destroyed"""
        try:
            if self.is_running():
                self.stop_server()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")