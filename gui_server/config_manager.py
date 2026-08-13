"""
Configuration Manager for AegisVision AI Trading Server
Handles configuration saving, loading, and encryption of sensitive data
"""

import json
import os
import logging
from typing import Dict, Any, Optional
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import getpass

logger = logging.getLogger(__name__)

class ConfigManager:
    """Manages configuration for the trading server"""
    
    def __init__(self):
        self.config_dir = self._get_config_directory()
        self.config_file = os.path.join(self.config_dir, "trading_config.json")
        self.encrypted_file = os.path.join(self.config_dir, "secure_config.dat")
        
        # Ensure config directory exists
        os.makedirs(self.config_dir, exist_ok=True)
        
        # Current configuration cache
        self._current_config = {}
        self._encryption_key = None
        
        # Load existing configuration
        self.load_config()
    
    def _get_config_directory(self) -> str:
        """Get configuration directory path"""
        if os.name == 'nt':  # Windows
            config_dir = os.path.join(os.getenv('APPDATA', ''), 'AegisVision_AI')
        else:  # Linux/Mac
            config_dir = os.path.join(os.path.expanduser('~'), '.orb_ai_trading')
        
        return config_dir
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration"""
        return {
            "server": {
                "host": "127.0.0.1",
                "port": "8080",
                "debug": False
            },
            "llm": {
                "provider": "gemini",
                "model": "gemini-2.5-flash",
                "api_key": "",
                "temperature": "0.3",
                "max_tokens": "4000"
            },
            "trading": {
                "min_confidence": "70",
                "min_risk_reward": "1.5",
                "max_spread": "2.0",
                "max_trades": "3",
                "max_daily_drawdown_percent": "5.0"
            },
            "ui": {
                "theme": "dark"
            }
        }

    def _generate_encryption_key(self, password: str = None) -> bytes:
        """Generate encryption key from password"""
        if password is None:
            # Use a default password (not secure, but better than plain text)
            password = "AegisVision_AI_Default_Key_2024"
        
        password_bytes = password.encode()
        salt = b'orb_ai_salt_2024'  # In production, use random salt
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000
        )
        key = base64.urlsafe_b64encode(kdf.derive(password_bytes))
        return key
    
    def _get_encryption_key(self) -> bytes:
        """Get or generate encryption key"""
        if self._encryption_key is None:
            self._encryption_key = self._generate_encryption_key()
        return self._encryption_key
    
    def save_config(self, config_data: Dict[str, Any]) -> bool:
        """Save configuration with encrypted sensitive data"""
        try:
            # Structure the configuration
            structured_config = self._structure_config(config_data)
            
            # TEMPORARY: Save API key directly to JSON file (no encryption)
            # This bypasses the encryption issue for testing
            logger.info("TEMP: Saving API key directly to config file (no encryption)")
            
            # Save configuration directly
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(structured_config, f, indent=2, ensure_ascii=False)
            
            # Update current config cache
            self._current_config = structured_config
            
            logger.info(f"Configuration saved to {self.config_file}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            return False
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration with decrypted sensitive data"""
        try:
            # Start with defaults
            config = self._get_default_config()
            
            # Load from JSON file if exists
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                
                # Merge with defaults
                config = self._merge_configs(config, saved_config)
            
            # TEMPORARY: Skip encryption and load API key directly from saved config
            # This bypasses the encryption issue for testing
            logger.info("TEMP: Using API key directly from config file (no encryption)")
            
            # Update current config cache
            self._current_config = config
            
            return config
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
            # Return defaults on error
            self._current_config = self._get_default_config()
            return self._current_config
    
    def _structure_config(self, flat_config: Dict[str, str]) -> Dict[str, Any]:
        """Convert flat configuration to structured format.

        max_daily_drawdown_percent isn't present in flat_config when saved
        from the Controls form (it's not a GUI field), so it falls back to
        whatever is currently saved rather than resetting to the hardcoded
        default on every Controls save.
        """
        current_trading = self._current_config.get("trading", {}) if self._current_config else {}
        structured = {
            "server": {
                "host": flat_config.get("host", "localhost"),
                "port": flat_config.get("port", "8080"),
                "debug": False
            },
            "llm": {
                "provider": flat_config.get("llm_provider", "gemini"),
                "model": flat_config.get("model", "gemini-2.0-flash-exp"),
                "api_key": flat_config.get("api_key", ""),
                "temperature": float(flat_config.get("temperature", "0.3")),
                "max_tokens": int(flat_config.get("max_tokens", "1000"))
            },
            "trading": {
                "min_confidence": float(flat_config.get("min_confidence", "70")),
                "min_risk_reward": float(flat_config.get("min_risk_reward", "1.5")),
                "max_spread": float(flat_config.get("max_spread", "2.0")),
                "max_trades": int(flat_config.get("max_trades", "3")),
                "max_daily_drawdown_percent": float(flat_config.get(
                    "max_daily_drawdown_percent", current_trading.get("max_daily_drawdown_percent", "5.0")
                ))
            }
        }
        
        return structured
    
    def _merge_configs(self, default: Dict, saved: Dict) -> Dict:
        """Merge saved config with defaults"""
        result = default.copy()
        
        for key, value in saved.items():
            if key in result:
                if isinstance(value, dict) and isinstance(result[key], dict):
                    result[key] = self._merge_configs(result[key], value)
                else:
                    result[key] = value
            else:
                result[key] = value
        
        return result
    
    def _save_encrypted_data(self, data: Dict[str, Any]):
        """Save encrypted sensitive data"""
        try:
            key = self._get_encryption_key()
            fernet = Fernet(key)
            
            # Convert to JSON and encrypt
            json_data = json.dumps(data)
            encrypted_data = fernet.encrypt(json_data.encode())
            
            # Save to file
            with open(self.encrypted_file, 'wb') as f:
                f.write(encrypted_data)
                
        except Exception as e:
            logger.error(f"Failed to save encrypted data: {e}")
    
    def _load_encrypted_data(self) -> Optional[Dict[str, Any]]:
        """Load and decrypt sensitive data"""
        try:
            if not os.path.exists(self.encrypted_file):
                logger.info("No encrypted file found")
                return None
            
            key = self._get_encryption_key()
            fernet = Fernet(key)
            
            # Load and decrypt
            with open(self.encrypted_file, 'rb') as f:
                encrypted_data = f.read()
            
            logger.info(f"Loaded {len(encrypted_data)} bytes of encrypted data")
            
            decrypted_data = fernet.decrypt(encrypted_data)
            result = json.loads(decrypted_data.decode())
            
            # Debug: Check what we decrypted (safely)
            if "api_key" in result:
                api_key = result["api_key"]
                logger.info(f"Decrypted API key length: {len(api_key)}")
                logger.info(f"Decrypted API key preview: {api_key[:10]}...{api_key[-5:] if len(api_key) > 15 else '***'}")
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to load encrypted data: {e}")
            return None
    
    def get_current_config(self) -> Dict[str, Any]:
        """Get current configuration"""
        if not self._current_config:
            self.load_config()
        return self._current_config.copy()
    
    def get_flat_config(self) -> Dict[str, str]:
        """Get configuration in flat format for GUI"""
        config = self.get_current_config()
        
        # Debug: Check what API key we have in the structured config
        api_key = config["llm"]["api_key"]
        # logger.info(f"get_flat_config - API key in structured config: '{api_key}' (length: {len(api_key)})")
        
        flat = {
            "host": str(config["server"]["host"]),
            "port": str(config["server"]["port"]),
            "llm_provider": config["llm"]["provider"],
            "model": config["llm"]["model"],
            "api_key": config["llm"]["api_key"],
            "temperature": str(config["llm"]["temperature"]),
            "max_tokens": str(config["llm"]["max_tokens"]),
            "min_confidence": str(config["trading"]["min_confidence"]),
            "min_risk_reward": str(config["trading"]["min_risk_reward"]),
            "max_spread": str(config["trading"]["max_spread"]),
            "max_trades": str(config["trading"]["max_trades"]),
            "max_daily_drawdown_percent": str(config["trading"].get("max_daily_drawdown_percent", "5.0"))
        }

        return flat

    def get_theme(self) -> str:
        """Get persisted UI appearance mode ('dark' or 'light')"""
        config = self.get_current_config()
        return config.get("ui", {}).get("theme", "dark")

    def set_theme(self, mode: str) -> bool:
        """Persist UI appearance mode ('dark' or 'light')"""
        try:
            config = self.get_current_config()
            config.setdefault("ui", {})["theme"] = mode
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            self._current_config = config
            return True
        except Exception as e:
            logger.error(f"Failed to save theme preference: {e}")
            return False

    def export_config(self, config_data: Dict[str, str], file_path: str):
        """Export configuration to file"""
        try:
            structured_config = self._structure_config(config_data)
            
            # Remove sensitive data for export
            export_config = structured_config.copy()
            if "api_key" in export_config["llm"]:
                export_config["llm"]["api_key"] = "[REDACTED]"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(export_config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Configuration exported to {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to export configuration: {e}")
            raise
    
    def import_config(self, file_path: str) -> Dict[str, str]:
        """Import configuration from file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                imported_config = json.load(f)
            
            # Convert to flat format
            flat_config = {}
            
            if "server" in imported_config:
                server = imported_config["server"]
                flat_config["host"] = str(server.get("host", "localhost"))
                flat_config["port"] = str(server.get("port", "8080"))
            
            if "llm" in imported_config:
                llm = imported_config["llm"]
                flat_config["llm_provider"] = llm.get("provider", "gemini")
                flat_config["model"] = llm.get("model", "gemini-2.0-flash-exp")
                flat_config["api_key"] = ""  # Don't import API key for security
                flat_config["temperature"] = str(llm.get("temperature", "0.3"))
                flat_config["max_tokens"] = str(llm.get("max_tokens", "1000"))
            
            if "trading" in imported_config:
                trading = imported_config["trading"]
                flat_config["min_confidence"] = str(trading.get("min_confidence", "70"))
                flat_config["min_risk_reward"] = str(trading.get("min_risk_reward", "1.5"))
                flat_config["max_spread"] = str(trading.get("max_spread", "2.0"))
                flat_config["max_trades"] = str(trading.get("max_trades", "3"))
                flat_config["max_daily_drawdown_percent"] = str(trading.get("max_daily_drawdown_percent", "5.0"))
            
            logger.info(f"Configuration imported from {file_path}")
            return flat_config
            
        except Exception as e:
            logger.error(f"Failed to import configuration: {e}")
            raise
    
    def reset_to_defaults(self) -> Dict[str, str]:
        """Reset configuration to defaults"""
        try:
            default_config = self._get_default_config()
            self._current_config = default_config
            
            # Convert to flat format
            return self.get_flat_config()
            
        except Exception as e:
            logger.error(f"Failed to reset configuration: {e}")
            raise
    
    def validate_api_key(self, provider: str, api_key: str) -> bool:
        """Validate API key format"""
        try:
            if not api_key or len(api_key) < 10:
                return False
            
            # Basic format validation
            if provider == "openai" and not api_key.startswith("sk-"):
                return False
            elif provider == "anthropic" and not api_key.startswith("sk-ant-"):
                return False
            # Gemini keys can vary in format, so we just check length
            
            return True
            
        except Exception as e:
            logger.error(f"API key validation error: {e}")
            return False
    
    def get_config_file_path(self) -> str:
        """Get configuration file path"""
        return self.config_file
    
    def backup_config(self) -> str:
        """Create backup of current configuration"""
        try:
            import shutil
            from datetime import datetime
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = os.path.join(self.config_dir, f"trading_config_backup_{timestamp}.json")
            
            if os.path.exists(self.config_file):
                shutil.copy2(self.config_file, backup_file)
                logger.info(f"Configuration backed up to {backup_file}")
                return backup_file
            else:
                logger.warning("No configuration file to backup")
                return ""
                
        except Exception as e:
            logger.error(f"Failed to backup configuration: {e}")
            return ""