"""
WebViewApi - the entire GUI-facing control surface, exposed to the React
frontend as window.pywebview.api.<method>() calls (see main.py, which passes
an instance of this class as js_api= to webview.create_window()).

This replaces every direct ConfigManager/ServerManager/store call that used
to happen inline inside CustomTkinter widget callbacks (controls_tab.py,
strategies_tab.py, backtest_tab.py, logs_tab.py). It intentionally does not
duplicate business logic - every method here is a thin wrapper around the
same manager/store classes the CTk app used, so the live trading pipeline
(server/trading_server.py, started via ServerManager) is completely
unaffected by this rewrite.

pywebview's JS-API bridge (not a second HTTP server) is used here on purpose:
this process already holds ConfigManager/ServerManager/the stores in-process,
exactly as the old GUI process did, so there is no need to stand up a second
Flask instance (with CORS, JSON (de)serialization boilerplate, etc.) just to
reach code that is already one Python call away. The existing Flask
subprocess (server/trading_server.py, /health + /analyze) is untouched and
unrelated - it exists for the MT5 EA, not the GUI.
"""

import base64
import json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import uuid
from dataclasses import asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_GUI_SERVER_ROOT = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_GUI_SERVER_ROOT)
_BACKTEST_DIR = os.path.join(_REPO_ROOT, "backtest")
_SERVER_DIR = os.path.join(_GUI_SERVER_ROOT, "server")
if _SERVER_DIR not in sys.path:
    sys.path.insert(0, _SERVER_DIR)
if _GUI_SERVER_ROOT not in sys.path:
    sys.path.insert(0, _GUI_SERVER_ROOT)

from app_paths import get_app_root
import active_strategy
from storage.template_image_store import TEMPLATE_SLOTS, LocalFileTemplateImageStore
from storage.prompt_store import LocalFilePromptStore
from storage import template_compositor
from audit.audit_log import JsonlAuditLogger
# Single source of truth for the Agent-2 prompt key, matching what
# vision_compliance.py's VisionComplianceFilter reads by default - see that
# module's DEFAULT_STRATEGY_NAME. (gui/widgets/prompt_section.py used to
# duplicate this literal; that file is retired along with the rest of gui/.)
from agents.vision_compliance import DEFAULT_STRATEGY_NAME as PROMPT_KEY

AUDIT_LOG_PATH = os.path.join(get_app_root(), "storage_data", "audit_log.jsonl")
HEARTBEAT_STATE_PATH = os.path.join(get_app_root(), "storage_data", "heartbeat_state.json")
LATEST_CHART_PATH = os.path.join(get_app_root(), "storage_data", "latest_chart.png")

MAX_SIGNAL_RECORDS = 50


def _to_data_uri(path: str) -> Optional[str]:
    if not path or not os.path.exists(path):
        return None
    mime_type = "image/jpeg" if path.lower().endswith((".jpg", ".jpeg")) else "image/png"
    with open(path, "rb") as f:
        encoded = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime_type};base64,{encoded}"


def _decode_data_uri_to_temp(image_base64: str) -> str:
    """Write a base64 (optionally data-URI-prefixed) image to a temp PNG
    file and return its path - LocalFileTemplateImageStore's save methods
    need a path on disk, not raw bytes, since they re-open the source with
    PIL for its actual dimensions."""
    if "," in image_base64 and image_base64.strip().startswith("data:"):
        image_base64 = image_base64.split(",", 1)[1]
    raw = base64.b64decode(image_base64)
    fd, path = tempfile.mkstemp(suffix=".png")
    with os.fdopen(fd, "wb") as f:
        f.write(raw)
    return path


class _BacktestJob:
    """Runs one backtest subprocess (extract_triggers.py or replay_harness.py)
    in a background thread, buffering stdout lines so the frontend can poll
    for incremental output instead of blocking on a single long HTTP call -
    these runs take anywhere from ~30s to several minutes."""

    def __init__(self, args: List[str]):
        self.lines: List[str] = []
        self.done = False
        self.returncode: Optional[int] = None
        self.progress: Optional[Dict[str, int]] = None
        self._lock = threading.Lock()
        self._thread = threading.Thread(target=self._run, args=(args,), daemon=True)
        self._thread.start()

    def _run(self, args: List[str]):
        try:
            proc = subprocess.Popen(
                args, cwd=_BACKTEST_DIR, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for line in proc.stdout:
                line = line.rstrip()
                with self._lock:
                    self.lines.append(line)
                    self._update_progress(line)
            proc.wait()
            with self._lock:
                self.returncode = proc.returncode
                self.done = True
        except Exception as e:
            with self._lock:
                self.lines.append(f"Error: {e}")
                self.returncode = -1
                self.done = True

    def _update_progress(self, line: str):
        # Lines look like: "[3/50] 2018-01-07T04:00:00 verdict=ACCEPT ..."
        try:
            if line.startswith("[") and "/" in line.split("]")[0]:
                fraction = line[1:line.index("]")]
                current, total = fraction.split("/")
                self.progress = {"current": int(current), "total": int(total)}
        except Exception:
            pass

    def snapshot(self, since: int = 0) -> Dict[str, Any]:
        with self._lock:
            return {
                "lines": self.lines[since:],
                "since": len(self.lines),
                "done": self.done,
                "returncode": self.returncode,
                "progress": self.progress,
            }


class WebViewApi:
    def __init__(self, config_manager, server_manager):
        self.config_manager = config_manager
        self.server_manager = server_manager
        self.audit_store = JsonlAuditLogger(AUDIT_LOG_PATH)
        self._backtest_jobs: Dict[str, _BacktestJob] = {}

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def get_config(self) -> Dict[str, str]:
        return self.config_manager.get_flat_config()

    def save_config(self, flat_config: Dict[str, str]) -> bool:
        return self.config_manager.save_config(flat_config)

    def reset_config(self) -> Dict[str, str]:
        return self.config_manager.reset_to_defaults()

    def get_theme(self) -> str:
        return self.config_manager.get_theme()

    def set_theme(self, mode: str) -> bool:
        return self.config_manager.set_theme(mode)

    def export_config(self, flat_config: Dict[str, str]) -> Optional[str]:
        import webview
        window = webview.windows[0]
        result = window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename="aegisvision_config.json",
            file_types=("JSON files (*.json)", "All files (*.*)"),
        )
        path = result[0] if result else None
        if not path:
            return None
        self.config_manager.export_config(flat_config, path)
        return path

    def import_config(self) -> Optional[Dict[str, str]]:
        import webview
        window = webview.windows[0]
        result = window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=("JSON files (*.json)", "All files (*.*)"),
        )
        path = result[0] if result else None
        if not path:
            return None
        return self.config_manager.import_config(path)

    def test_connection(self, host: str, port: str) -> Dict[str, Any]:
        if not host or not port:
            return {"success": False, "message": "Please enter host and port"}
        try:
            response = requests.get(f"http://{host}:{port}/health", timeout=5)
            if response.status_code == 200:
                return {"success": True, "message": "Connection test successful!"}
            return {"success": False, "message": f"Server returned status {response.status_code}"}
        except requests.exceptions.ConnectionError:
            return {"success": False, "message": "Server not responding (may not be started yet)"}
        except Exception as e:
            return {"success": False, "message": f"Connection test failed: {e}"}

    def test_api_key(self, provider: str, api_key: str) -> Dict[str, Any]:
        if not api_key:
            return {"success": False, "message": "Please enter an API key"}
        try:
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
                return {"success": False, "message": f"Unknown provider: {provider}"}

            if response.status_code == 200:
                return {"success": True, "message": f"{provider.title()} API connection successful!"}
            return {"success": False, "message": f"API test failed: {response.status_code}"}
        except Exception as e:
            return {"success": False, "message": f"API test failed: {e}"}

    # ------------------------------------------------------------------
    # Server control
    # ------------------------------------------------------------------

    def start_server(self) -> bool:
        return self.server_manager.start_server()

    def stop_server(self) -> bool:
        return self.server_manager.stop_server()

    def restart_server(self) -> bool:
        return self.server_manager.restart_server()

    def get_server_status(self) -> Dict[str, Any]:
        return {"is_running": self.server_manager.is_running(), "url": self.server_manager.get_server_url()}

    def get_server_stats(self) -> Dict[str, Any]:
        return self.server_manager.get_server_stats()

    def health_check(self) -> Optional[Dict[str, Any]]:
        return self.server_manager.health_check()

    # ------------------------------------------------------------------
    # Signals (audit log tail)
    # ------------------------------------------------------------------

    def get_trade_telemetry(self) -> Dict[str, Any]:
        """Aggregate counts over the *entire* audit log (not just the
        capped recent-signals tail) -- every setup Agent 2/3 has ever
        evaluated, split by outcome. This is the EA's real track record,
        not a synthetic stat."""
        records = self.audit_store.read_all()
        total = len(records)
        approved = sum(1 for r in records if r.final_action in ("BUY", "SELL"))
        vetoed = sum(1 for r in records if r.guardrail_vetoed)
        today = datetime.now().date().isoformat()
        approved_today = sum(
            1 for r in records if r.final_action in ("BUY", "SELL") and r.timestamp.startswith(today)
        )
        return {
            "total_evaluated": total,
            "approved": approved,
            "rejected": total - approved,
            "guardrail_vetoed": vetoed,
            "approved_today": approved_today,
            "last_decision_time": records[-1].timestamp if records else None,
        }

    def get_recent_signals(self, since: int = 0) -> Dict[str, Any]:
        records = self.audit_store.read_all()
        new_records = records[since:]
        out = []
        for record in new_records:
            reasoning = record.llm_reasoning
            if record.guardrail_vetoed:
                reasoning = f"{reasoning} [VETOED: {record.guardrail_veto_reason}]"
            out.append({
                "action": record.final_action,
                "symbol": record.symbol,
                "confidence": record.llm_confidence,
                "reasoning": reasoning,
                "timestamp": record.timestamp,
                "entry_price": record.entry_price,
                "stop_loss": record.final_stop_loss,
                "take_profit": record.final_take_profit,
            })
        # newest first, capped - mirrors the old chip strip's MAX_SIGNAL_CHIPS behavior
        out = list(reversed(out))[:MAX_SIGNAL_RECORDS]
        return {"records": out, "since": len(records)}

    def get_live_positions(self) -> Dict[str, Any]:
        """Latest EA heartbeat snapshot: liveness + currently-open positions
        with real-time P&L, as sent to /heartbeat every few seconds -
        independent of (and much more frequent than) actual trade signals."""
        if not os.path.exists(HEARTBEAT_STATE_PATH):
            return {"last_seen": None, "seconds_since": None, "symbol": "", "open_trades": []}
        try:
            with open(HEARTBEAT_STATE_PATH, 'r', encoding='utf-8') as f:
                snapshot = json.load(f)
        except (json.JSONDecodeError, OSError):
            return {"last_seen": None, "seconds_since": None, "symbol": "", "open_trades": []}

        last_seen = snapshot.get("last_seen")
        seconds_since = None
        if last_seen:
            try:
                seconds_since = (datetime.now() - datetime.fromisoformat(last_seen)).total_seconds()
            except ValueError:
                pass

        return {
            "last_seen": last_seen,
            "seconds_since": seconds_since,
            "symbol": snapshot.get("symbol", ""),
            "open_trades": snapshot.get("open_trades", []),
        }

    def get_latest_chart(self) -> Optional[Dict[str, Any]]:
        """The most recently generated M1 chart image - either from a real
        signal or the one-shot test render fired right after the EA's bulk
        historical load completes. Lets the operator eyeball chart
        quality/framing (gridlines, SMA overlay, 6h window) without waiting
        for a live trade setup to occur."""
        if not os.path.exists(LATEST_CHART_PATH):
            return None
        return {
            "image": _to_data_uri(LATEST_CHART_PATH),
            "updated_at": datetime.fromtimestamp(os.path.getmtime(LATEST_CHART_PATH)).isoformat(),
        }

    def save_data_uri(self, data_uri: str, suggested_name: str) -> Optional[str]:
        """Native OS Save dialog for anything the frontend only holds as a
        data URI (chart/template image previews) - a plain <a download> link
        is unreliable inside pywebview's WebView2 shell, unlike this
        file-dialog path already used by export_config/export_log below."""
        import webview
        window = webview.windows[0]
        result = window.create_file_dialog(
            webview.FileDialog.SAVE, save_filename=suggested_name,
            file_types=("PNG files (*.png)", "All files (*.*)"),
        )
        path = result[0] if result else None
        if not path:
            return None
        _, _, encoded = data_uri.partition(",")
        with open(path, "wb") as f:
            f.write(base64.b64decode(encoded))
        return path

    # ------------------------------------------------------------------
    # Strategies
    # ------------------------------------------------------------------

    def _strategy_stores(self, strategy_id: str):
        strategy_dir = active_strategy.get_strategy_dir(strategy_id)
        template_store = LocalFileTemplateImageStore(os.path.join(strategy_dir, "templates"))
        prompt_store = LocalFilePromptStore(os.path.join(strategy_dir, "prompts"))
        return strategy_dir, template_store, prompt_store

    def list_strategies(self) -> List[Dict[str, str]]:
        results = []
        if os.path.isdir(active_strategy.STRATEGIES_STORE_DIR):
            for entry in os.listdir(active_strategy.STRATEGIES_STORE_DIR):
                meta_path = os.path.join(active_strategy.STRATEGIES_STORE_DIR, entry, "strategy_meta.json")
                if os.path.exists(meta_path):
                    try:
                        with open(meta_path, "r", encoding="utf-8") as f:
                            meta = json.load(f)
                        results.append({"id": meta["id"], "name": meta["name"], "category": meta.get("category", "")})
                    except Exception as e:
                        logger.warning(f"Could not read {meta_path}: {e}")
        return sorted(results, key=lambda s: s["name"].lower())

    def create_strategy(self, name: str, category: str = "") -> Dict[str, Any]:
        name = (name or "").strip()
        category = (category or "").strip() or name
        if not name:
            return {"error": "Name is required."}
        existing_lower = {s["name"].lower() for s in self.list_strategies()}
        if name.lower() in existing_lower:
            return {"error": f"A strategy named '{name}' already exists."}

        strategy_id = str(uuid.uuid4())
        strategy_dir = active_strategy.get_strategy_dir(strategy_id)
        os.makedirs(strategy_dir, exist_ok=True)
        now = datetime.now().isoformat()
        meta = {"id": strategy_id, "name": name, "category": category, "created_at": now, "updated_at": now}
        with open(os.path.join(strategy_dir, "strategy_meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        active_strategy.set_active_strategy_id(strategy_id, name)
        return meta

    def get_active_strategy(self) -> Optional[Dict[str, str]]:
        strategy_id = active_strategy.get_active_strategy_id()
        if not strategy_id:
            return None
        for s in self.list_strategies():
            if s["id"] == strategy_id:
                return s
        return None

    def set_active_strategy(self, strategy_id: str) -> bool:
        for s in self.list_strategies():
            if s["id"] == strategy_id:
                active_strategy.set_active_strategy_id(strategy_id, s["name"])
                return True
        return False

    def get_strategy_templates(self, strategy_id: str) -> Dict[str, Any]:
        _, template_store, _ = self._strategy_stores(strategy_id)
        out = {}
        for slot in TEMPLATE_SLOTS:
            record = template_store.get_template(slot)
            if record is None:
                out[slot] = None
                continue
            image_path = os.path.join(template_store.storage_dir, record.filename)
            out[slot] = {**asdict(record), "image": _to_data_uri(image_path)}
        return out

    def get_template_sources(self, strategy_id: str, slot: str) -> List[Dict[str, Any]]:
        _, template_store, _ = self._strategy_stores(strategy_id)
        sources = template_store.get_template_sources(slot)
        out = []
        for s in sources:
            path = os.path.join(template_store.storage_dir, s.filename)
            out.append({**asdict(s), "image": _to_data_uri(path)})
        return out

    def save_template_source(
        self, strategy_id: str, slot: str, position: int, image_base64: str,
        crop_x: float, crop_y: float, crop_w: float, crop_h: float,
        caption: Optional[str] = None,
    ) -> Dict[str, Any]:
        _, template_store, _ = self._strategy_stores(strategy_id)
        temp_path = _decode_data_uri_to_temp(image_base64)
        try:
            record = template_store.save_template_source(
                slot, position, temp_path, (crop_x, crop_y, crop_w, crop_h), caption,
            )
        finally:
            os.remove(temp_path)
        image_path = os.path.join(template_store.storage_dir, record.filename)
        return {**asdict(record), "image": _to_data_uri(image_path)}

    def remove_template_source(self, strategy_id: str, slot: str, position: int) -> Optional[Dict[str, Any]]:
        _, template_store, _ = self._strategy_stores(strategy_id)
        record = template_store.remove_template_source(slot, position)
        if record is None:
            return None
        image_path = os.path.join(template_store.storage_dir, record.filename)
        return {**asdict(record), "image": _to_data_uri(image_path)}

    def update_template_caption(self, strategy_id: str, slot: str, caption: str) -> Optional[Dict[str, Any]]:
        _, template_store, _ = self._strategy_stores(strategy_id)
        record = template_store.update_caption(slot, caption)
        if record is None:
            return None
        image_path = os.path.join(template_store.storage_dir, record.filename)
        return {**asdict(record), "image": _to_data_uri(image_path)}

    def get_cell_aspect_ratio(self, count: int, index: int) -> float:
        return template_compositor.cell_aspect_ratio(count, index)

    def get_prompt(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        _, _, prompt_store = self._strategy_stores(strategy_id)
        latest = prompt_store.get_latest(PROMPT_KEY)
        return asdict(latest) if latest else None

    def list_prompt_versions(self, strategy_id: str) -> List[Dict[str, Any]]:
        _, _, prompt_store = self._strategy_stores(strategy_id)
        return [asdict(v) for v in prompt_store.list_versions(PROMPT_KEY)]

    def save_prompt(self, strategy_id: str, text: str, notes: str = "edited via web UI") -> Dict[str, Any]:
        _, _, prompt_store = self._strategy_stores(strategy_id)
        return asdict(prompt_store.save_prompt(PROMPT_KEY, text, notes))

    # ------------------------------------------------------------------
    # Backtest
    # ------------------------------------------------------------------

    def start_extract(self, start_date: str, end_date: str, interval_minutes: str, max_events: str) -> str:
        script = os.path.join(_BACKTEST_DIR, "extract_triggers.py")
        args = [
            sys.executable, script,
            "--start-date", start_date, "--end-date", end_date,
            "--interval-minutes", str(interval_minutes), "--max-events", str(max_events),
        ]
        job_id = str(uuid.uuid4())
        self._backtest_jobs[job_id] = _BacktestJob(args)
        return job_id

    def start_replay(self, throttle_seconds: str, min_confidence: str, min_risk_reward: str) -> Dict[str, Any]:
        events_path = os.path.join(_BACKTEST_DIR, "trigger_events.json")
        if not os.path.exists(events_path):
            return {"error": "Extract trigger events first (step 1)."}
        script = os.path.join(_BACKTEST_DIR, "replay_harness.py")
        args = [
            sys.executable, script,
            "--throttle-seconds", str(throttle_seconds),
            "--min-confidence", str(min_confidence),
            "--min-risk-reward", str(min_risk_reward),
        ]
        job_id = str(uuid.uuid4())
        self._backtest_jobs[job_id] = _BacktestJob(args)
        return {"job_id": job_id}

    def get_job_output(self, job_id: str, since: int = 0) -> Dict[str, Any]:
        job = self._backtest_jobs.get(job_id)
        if job is None:
            return {"error": "Unknown job_id"}
        return job.snapshot(since)

    def get_backtest_report(self) -> Optional[Dict[str, Any]]:
        report_path = os.path.join(_BACKTEST_DIR, "backtest_report.json")
        if not os.path.exists(report_path):
            return None
        with open(report_path) as f:
            return json.load(f)

    # ------------------------------------------------------------------
    # Logs
    # ------------------------------------------------------------------

    def _log_file_path(self) -> Optional[str]:
        return self.server_manager.get_log_file_path()

    def _clear_marker_path(self) -> Optional[str]:
        path = self._log_file_path()
        return f"{path}.clear_offset" if path else None

    def _clear_offset(self) -> int:
        marker = self._clear_marker_path()
        if not marker or not os.path.exists(marker):
            return 0
        try:
            with open(marker, "r", encoding="utf-8") as f:
                return int(f.read().strip() or 0)
        except (ValueError, OSError):
            return 0

    def clear_log(self) -> int:
        """Marks everything currently in the log file as cleared. The file
        itself is left alone (the running server may hold it open for
        append), so tail_log/get_log_stats instead skip past this offset -
        otherwise a cleared view would reappear on the next poll/session."""
        path = self._log_file_path()
        marker = self._clear_marker_path()
        if not path or not marker:
            return 0
        offset = os.path.getsize(path) if os.path.exists(path) else 0
        with open(marker, "w", encoding="utf-8") as f:
            f.write(str(offset))
        return offset

    def tail_log(self, offset: int = 0) -> Dict[str, Any]:
        path = self._log_file_path()
        if not path or not os.path.exists(path):
            return {"lines": [], "new_offset": 0}
        file_size = os.path.getsize(path)
        effective_offset = max(offset, self._clear_offset())
        if effective_offset > file_size:
            effective_offset = 0  # file was rotated/truncated since last poll
        with open(path, "r", encoding="utf-8") as f:
            f.seek(effective_offset)
            new_content = f.read()
            new_offset = f.tell()
        lines = [line for line in new_content.split("\n") if line.strip()] if new_content else []
        return {"lines": lines, "new_offset": new_offset}

    def get_log_stats(self) -> Dict[str, Any]:
        path = self._log_file_path()
        level_counts = {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}
        total = 0
        if path and os.path.exists(path):
            clear_offset = min(self._clear_offset(), os.path.getsize(path))
            with open(path, "r", encoding="utf-8") as f:
                f.seek(clear_offset)
                lines = [l for l in f.read().split("\n")[-1000:] if l.strip()]
            total = len(lines)
            for line in lines:
                for level in level_counts:
                    if f"- {level} -" in line:
                        level_counts[level] += 1
                        break
        stats = {"total_entries": total, "level_counts": level_counts}
        if path and os.path.exists(path):
            stats["file_size_bytes"] = os.path.getsize(path)
            stats["last_modified"] = datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
        return stats

    def export_log(self) -> Optional[str]:
        path = self._log_file_path()
        if not path or not os.path.exists(path):
            return None
        import webview
        window = webview.windows[0]
        result = window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=f"orb_server_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
            file_types=("Text files (*.txt)", "Log files (*.log)", "All files (*.*)"),
        )
        dest = result[0] if result else None
        if not dest:
            return None
        with open(path, "r", encoding="utf-8") as src, open(dest, "w", encoding="utf-8") as out:
            out.write("AegisVision AI Trading Server Logs Export\n")
            out.write(f"Export Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            out.write("=" * 60 + "\n\n")
            out.write(src.read())
        return dest

    def open_log_file(self) -> bool:
        path = self._log_file_path()
        if not path or not os.path.exists(path):
            return False
        os.startfile(path)  # Windows-only, matches original CTk behavior
        return True
