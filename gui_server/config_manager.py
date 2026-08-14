"""
Configuration Manager for AegisVision AI Trading Server
Handles configuration saving, loading, and encryption of sensitive data
"""

import base64
import json
import os
import logging
from typing import Dict, Any

import win32crypt

logger = logging.getLogger(__name__)

# DPAPI's optional "entropy" argument -- an extra pepper mixed into the
# encryption, not a secret by itself, but means a blob encrypted with this
# entropy can't be decrypted by some other unrelated CryptProtectData call
# that happens to run under the same Windows account.
_DPAPI_ENTROPY = b"AegisVision_AI_config"


def _dpapi_encrypt(plaintext: str) -> str:
    """Encrypts a secret with Windows DPAPI, bound to the current Windows
    user account - only decryptable on this machine, by this user, which is
    exactly the guarantee a locally-stored API key needs. No password/key
    management on our side: the OS derives and protects the actual key.
    Returns a base64 string safe to embed in the JSON config file."""
    blob = win32crypt.CryptProtectData(plaintext.encode("utf-8"), "AegisVision AI secret", _DPAPI_ENTROPY, None, None, 0)
    return base64.b64encode(blob).decode("ascii")


def _dpapi_decrypt(encoded_blob: str) -> str:
    blob = base64.b64decode(encoded_blob)
    _, plaintext = win32crypt.CryptUnprotectData(blob, _DPAPI_ENTROPY, None, None, 0)
    return plaintext.decode("utf-8")


class ConfigManager:
    """Manages configuration for the trading server"""

    def __init__(self):
        self.config_dir = self._get_config_directory()
        self.config_file = os.path.join(self.config_dir, "trading_config.json")

        # Ensure config directory exists
        os.makedirs(self.config_dir, exist_ok=True)

        # Current configuration cache
        self._current_config = {}

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

    def save_config(self, config_data: Dict[str, Any]) -> bool:
        """Save configuration. The API key never touches disk in plaintext -
        it's encrypted with Windows DPAPI first (see _dpapi_encrypt)."""
        try:
            structured_config = self._structure_config(config_data)
            api_key = structured_config["llm"].pop("api_key", "")

            # _structure_config only knows about server/llm/trading -- carry
            # forward any other top-level sections (currently just `ui`) so
            # saving from the Controls form doesn't silently wipe them.
            structured_config["ui"] = (self._current_config or {}).get("ui", {"theme": "dark"})

            on_disk = json.loads(json.dumps(structured_config))  # deep copy
            on_disk["llm"]["api_key_encrypted"] = _dpapi_encrypt(api_key) if api_key else ""

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(on_disk, f, indent=2, ensure_ascii=False)

            # In-memory cache keeps the plaintext key so the rest of the app
            # (LLM calls, the GUI form) isn't calling DPAPI on every read.
            structured_config["llm"]["api_key"] = api_key
            self._current_config = structured_config

            logger.info(f"Configuration saved to {self.config_file}")
            return True

        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            return False

    def load_config(self) -> Dict[str, Any]:
        """Load configuration, decrypting the API key if it's stored
        DPAPI-encrypted. Falls back to a legacy plaintext `api_key` field
        for configs saved before encryption was added - that key still
        works immediately, and gets encrypted the next time Save runs."""
        try:
            config = self._get_default_config()

            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    saved_config = json.load(f)
                config = self._merge_configs(config, saved_config)

            llm = config.setdefault("llm", {})
            encrypted = llm.pop("api_key_encrypted", None)
            if encrypted:
                try:
                    llm["api_key"] = _dpapi_decrypt(encrypted)
                except Exception as e:
                    logger.error(
                        f"Failed to decrypt stored API key - it was likely saved under a "
                        f"different Windows account or on a different machine: {e}"
                    )
                    llm["api_key"] = ""
            elif llm.get("api_key"):
                logger.info("Loaded a plaintext API key saved before encryption support was added - "
                            "it will be encrypted automatically the next time configuration is saved.")

            self._current_config = config
            return config

        except Exception as e:
            logger.error(f"Failed to load configuration: {e}")
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