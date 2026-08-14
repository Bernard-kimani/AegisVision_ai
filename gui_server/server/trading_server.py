"""
AegisVision Trading Server - Flask orchestrator.

Thin by design: this module wires together the three agents and exposes them
over HTTP for the MT5 EA. It does not contain vision-compliance or risk logic
itself - see agents/ingestor.py, agents/vision_compliance.py, agents/guardrail.py.

    /analyze  ->  Ingestor.ingest_*()  ->  VisionComplianceFilter.evaluate()  ->  RiskGuardrail.evaluate()  ->  EA-compatible JSON
"""

import json
import logging
import os
import sys
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from flask import Flask, current_app, jsonify, request
from flask_cors import CORS

# Add current directory (gui_server/server) to path so sibling top-level
# packages (data, utils, agents, llm, audit) resolve, and add the parent
# (gui_server/) so the storage package resolves too.
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)
sys.path.insert(0, os.path.dirname(current_dir))

from data.models import CandleData, TechnicalIndicators
from data.preprocessor import DataPreprocessor
from data.sliding_window import SlidingWindowManager
from news_fetcher import news_fetcher

from agents.ingestor import Ingestor
from agents.vision_compliance import VisionComplianceFilter
from agents.guardrail import GuardrailContext, RiskGuardrail
from audit.audit_log import JsonlAuditLogger
from llm import create_provider
from storage.active_strategy_store import ActiveStrategyPromptStore, ActiveStrategyTemplateStore
from settings import get_settings
from app_paths import get_app_root

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# get_app_root(), not __file__-derived paths: this resolves to the .exe's own
# directory when frozen (PyInstaller), not its ephemeral temp extraction
# folder - otherwise audit logs/prompts/templates would vanish between runs
# of a packaged build.
STORAGE_DATA_DIR = os.path.join(get_app_root(), "storage_data")

# Latest EA heartbeat snapshot (liveness + open-position P&L), overwritten in
# place on every /heartbeat call - not an audit trail, just current state, so
# a single mutable file (unlike the append-only audit_log.jsonl) is correct.
HEARTBEAT_STATE_PATH = os.path.join(STORAGE_DATA_DIR, "heartbeat_state.json")
_heartbeat_lock = threading.Lock()


def default_config() -> Dict[str, Any]:
    return {
        "server": {"host": "localhost", "port": 8080},
        "llm": {
            "provider": "gemini",
            "model": "gemini-2.5-flash",
            "api_key": "",
            "max_tokens": 1000,
            "temperature": 0.3,
        },
        "trading": {
            "min_confidence": 70,
            "min_risk_reward": 1.5,
            "max_spread": 2.0,
            "max_trades": 3,
            "max_daily_drawdown_percent": 5.0,
        },
    }


def resolve_api_key(config: Dict[str, Any]) -> str:
    """.env (settings.py) wins if set - it's the intended secret-storage path.
    Falls back to the GUI-configured JSON value so the app still works for
    someone who only ever used the Configuration tab."""
    settings = get_settings()
    provider = config["llm"]["provider"].lower()
    env_key = {
        "gemini": settings.gemini_api_key,
        "openai": settings.openai_api_key,
        "anthropic": settings.anthropic_api_key,
    }.get(provider, "")
    return env_key or config["llm"].get("api_key", "")


def create_app(config: Optional[Dict[str, Any]] = None) -> Flask:
    app = Flask(__name__)
    CORS(app)

    cfg = default_config()
    if config:
        for section in ("server", "llm", "trading"):
            if section in config:
                cfg[section].update(config[section])

    api_key = resolve_api_key(cfg)
    llm_provider = create_provider(cfg["llm"]["provider"], api_key, cfg["llm"]["model"])

    window_manager = SlidingWindowManager()
    preprocessor = DataPreprocessor(window_manager)
    ingestor = Ingestor(window_manager, preprocessor)

    # Resolve fresh per call to whichever strategy is active (see
    # active_strategy.py) -- falls back to the legacy global paths above
    # when no strategy has been created/selected yet, so this is a no-op
    # for existing installs. Switching strategies from the GUI dropdown
    # takes effect on the next /analyze call, no server restart needed.
    prompt_store = ActiveStrategyPromptStore()
    template_store = ActiveStrategyTemplateStore()
    audit_store = JsonlAuditLogger(os.path.join(STORAGE_DATA_DIR, "audit_log.jsonl"))

    vision_compliance = VisionComplianceFilter(
        llm_provider=llm_provider,
        template_store=template_store,
        prompt_store=prompt_store,
        max_tokens=cfg["llm"]["max_tokens"],
        temperature=cfg["llm"]["temperature"],
    )

    guardrail = RiskGuardrail(
        audit_store=audit_store,
        drawdown_state_path=os.path.join(STORAGE_DATA_DIR, "drawdown_state.json"),
        min_confidence_threshold=float(cfg["trading"]["min_confidence"]),
        min_risk_reward=float(cfg["trading"]["min_risk_reward"]),
        max_spread=float(cfg["trading"]["max_spread"]),
        max_daily_drawdown_percent=float(cfg["trading"]["max_daily_drawdown_percent"]),
        max_simultaneous_trades=int(cfg["trading"]["max_trades"]),
        news_fetcher=news_fetcher,
    )

    app.config_snapshot = cfg
    app.ingestor = ingestor
    app.vision_compliance = vision_compliance
    app.guardrail = guardrail
    app.audit_store = audit_store
    app.template_store = template_store
    app.prompt_store = prompt_store

    logger.info(f"AegisVision server initialized - provider={cfg['llm']['provider']} model={cfg['llm']['model']}")

    @app.route('/health', methods=['GET'])
    def health_check():
        return jsonify({
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "llm_provider": cfg["llm"]["provider"],
            "model": cfg["llm"]["model"],
            "active_connections": len(window_manager.get_all_connections()),
        })

    @app.route('/heartbeat', methods=['POST'])
    def heartbeat():
        # Lightweight liveness + open-position P&L ping, sent by the EA every
        # few seconds independent of whether a trade setup has actually
        # fired - no LLM call, no sliding-window/guardrail involvement. This
        # is what lets the GUI show "EA connected" and live floating P&L even
        # during the long stretches between real /analyze evaluations.
        try:
            data = request.get_json(force=True, silent=True) or {}
            snapshot = {
                "symbol": data.get("symbol", ""),
                "open_trades": data.get("open_trades", []),
                "last_seen": datetime.now().isoformat(),
            }
            with _heartbeat_lock:
                with open(HEARTBEAT_STATE_PATH, 'w', encoding='utf-8') as f:
                    json.dump(snapshot, f)
            return jsonify({"status": "ok"})
        except Exception as e:
            logger.error(f"Heartbeat error: {e}")
            return jsonify({"status": "error"}), 400

    @app.route('/analyze', methods=['POST'])
    def analyze_endpoint():
        try:
            data = _parse_request_json(request.get_data(as_text=True))
            if data is None:
                return jsonify(_wait_response("Invalid JSON data")), 400

            symbol = data.get('symbol', 'XAUUSD')
            ing: Ingestor = current_app.ingestor
            vc: VisionComplianceFilter = current_app.vision_compliance
            gr: RiskGuardrail = current_app.guardrail

            # request_type drives everything: "bulk_load" seeds the sliding windows
            # on connect; "candle_close" is the routine once-a-minute keep-alive
            # that only ingests (no LLM call - this is what keeps the constant
            # per-timeframe updates cheap); "signal" is the only path that runs
            # the full Agent 2/3 pipeline, since it's the only event carrying an
            # actual EA-detected trigger. Falls back to key-sniffing for older
            # callers that don't set request_type.
            request_type = data.get('request_type')
            if request_type is None:
                request_type = 'bulk_load' if ('candles_5min' in data and 'candles_1hour' in data) else 'signal'

            if request_type == 'bulk_load':
                ingest_result = _handle_bulk_load(data, symbol, ing)
                if not ingest_result["success"]:
                    return jsonify(_wait_response("Invalid candle data format", ingest_result["status"])), 400
                return jsonify(_wait_response("Bulk data loaded", ingest_result["status"]))

            ingest_result = _handle_single_candle(data, symbol, ing)
            if not ingest_result["success"]:
                return jsonify(_wait_response("Invalid candle data format", ingest_result["status"])), 400

            if request_type == 'candle_close':
                # Routine sliding-window keep-alive - never invokes the LLM.
                return jsonify(_wait_response("Candle ingested", ingest_result["status"]))

            if not ing.is_ready(symbol):
                status = ingest_result["status"]
                reasoning = (
                    f"Collecting data for analysis. Current: "
                    f"{status.get('candles_1min_count', 0)} 1min / "
                    f"{status.get('candles_5min_count', 0)} 5min / "
                    f"{status.get('candles_1hour_count', 0)} 1hour candles"
                )
                return jsonify(_wait_response(reasoning, status))

            trigger_direction = str(data.get('trigger_direction', '')).upper()
            if trigger_direction not in ('BUY', 'SELL'):
                return jsonify(_wait_response(f"Signal event missing a valid trigger_direction: {trigger_direction!r}"))

            signal = _run_pipeline(symbol, data, trigger_direction, ing, vc, gr)
            return jsonify(signal)

        except Exception as e:
            logger.error(f"Unexpected error in /analyze: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return jsonify(_wait_response(f"Server error: {e}")), 500

    return app


# --- Request parsing / ingestion helpers ---

def _parse_request_json(raw_data: str) -> Optional[Dict[str, Any]]:
    """MT5's WebRequest occasionally double-encodes/escapes JSON - this mirrors
    the cleanup logic proven out in the original implementation."""
    import json as json_module

    try:
        cleaned = raw_data.strip()
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1]
        cleaned = cleaned.replace('\\"', '"').replace('\\n', '\n').replace('\\r', '\r').replace('\\/', '/')

        brace_count = 0
        json_end = -1
        for i, char in enumerate(cleaned):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_end = i + 1
                    break
        if 0 < json_end < len(cleaned):
            cleaned = cleaned[:json_end]

        return json_module.loads(cleaned)
    except json_module.JSONDecodeError as e:
        logger.error(f"JSON parsing error: {e}")
        return None


def parse_candle_data(candle_dict: Dict, timeframe: str, symbol: str) -> Optional[CandleData]:
    try:
        timestamp_str = candle_dict.get('time') or candle_dict.get('timestamp', '')
        if timestamp_str:
            try:
                if '.' in timestamp_str and len(timestamp_str.split('.')) == 3:
                    timestamp = datetime.strptime(timestamp_str, "%Y.%m.%d %H:%M:%S")
                else:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except ValueError:
                timestamp = datetime.now()
        else:
            timestamp = datetime.now()

        tech_indicators = TechnicalIndicators(
            rsi=float(candle_dict['rsi']) if candle_dict.get('rsi') else None,
            macd=float(candle_dict['macd']) if candle_dict.get('macd') else None,
            macd_signal=float(candle_dict['macd_signal']) if candle_dict.get('macd_signal') else None,
            macd_histogram=float(candle_dict['macd_histogram']) if candle_dict.get('macd_histogram') else None,
            bb_upper=float(candle_dict['bb_upper']) if candle_dict.get('bb_upper') else None,
            bb_middle=float(candle_dict['bb_middle']) if candle_dict.get('bb_middle') else None,
            bb_lower=float(candle_dict['bb_lower']) if candle_dict.get('bb_lower') else None,
            ma_5=float(candle_dict['ma_5']) if candle_dict.get('ma_5') else None,
            ma_20=float(candle_dict['ma_20']) if candle_dict.get('ma_20') else None,
            ma_50=float(candle_dict['ma_50']) if candle_dict.get('ma_50') else None,
            obv=float(candle_dict['obv']) if candle_dict.get('obv') else None,
            atr=float(candle_dict['atr']) if candle_dict.get('atr') else None,
            adx=float(candle_dict['adx']) if candle_dict.get('adx') else None,
        )

        return CandleData(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=timestamp,
            open_price=float(candle_dict.get('open_price', candle_dict.get('open', 0))),
            high_price=float(candle_dict.get('high_price', candle_dict.get('high', 0))),
            low_price=float(candle_dict.get('low_price', candle_dict.get('low', 0))),
            close_price=float(candle_dict.get('close_price', candle_dict.get('close', 0))),
            volume=int(candle_dict.get('volume', 0)),
            spread=float(candle_dict.get('spread', 0)),
            technical_indicators=tech_indicators,
        )
    except Exception as e:
        logger.error(f"Error parsing candle data: {e}")
        return None


def _handle_bulk_load(data: Dict, symbol: str, ingestor: Ingestor) -> Dict[str, Any]:
    candles_1min = [c for c in (parse_candle_data(d, "M1", symbol) for d in data.get('candles_1min', [])) if c]
    candles_5min = [c for c in (parse_candle_data(d, "M5", symbol) for d in data.get('candles_5min', [])) if c]
    candles_1hour = [c for c in (parse_candle_data(d, "H1", symbol) for d in data.get('candles_1hour', [])) if c]

    result = ingestor.ingest_bulk(symbol, candles_1min, candles_5min, candles_1hour)
    return {"success": result["success"], "status": result["status"]}


def _handle_single_candle(data: Dict, symbol: str, ingestor: Ingestor) -> Dict[str, Any]:
    candle_dicts = data.get('candles')
    if candle_dicts is None:
        candle_dicts = [data] if 'timeframe' in data else []

    candles_with_tf: List[Tuple[CandleData, str]] = []
    for candle_dict in candle_dicts:
        timeframe = candle_dict.get('timeframe', 'M5')
        candle = parse_candle_data(candle_dict, timeframe, symbol)
        if candle:
            candles_with_tf.append((candle, timeframe))

    if not candles_with_tf:
        return {"success": False, "status": ingestor.get_window_status(symbol)}

    result = ingestor.ingest_single(symbol, candles_with_tf)
    return {"success": result["success"], "status": result["status"]}


def _run_pipeline(
    symbol: str,
    request_data: Dict,
    trigger_direction: str,
    ingestor: Ingestor,
    vision_compliance: VisionComplianceFilter,
    guardrail: RiskGuardrail,
) -> Dict[str, Any]:
    pipeline_t0 = time.perf_counter()
    open_trades = request_data.get('open_trades', [])

    payload = ingestor.build_dynamic_payload(symbol, open_trades=open_trades, chart_timeframe="M1")
    if payload is None:
        return _wait_response("Could not generate market summary")

    # Direction and SL/TP/headroom/R:R/higher-tf-bias are all deterministic -
    # computed by Agent 0 (the EA's trigger) and Agent 1 (this call), never by
    # the LLM. Agent 2 only judges whether the visual setup justifies acting
    # on them.
    trigger_metrics = ingestor.compute_trigger_metrics(symbol, trigger_direction)

    llm_t0 = time.perf_counter()
    verdict = vision_compliance.evaluate(
        payload.market_summary_text,
        payload.chart_image_b64,
        direction=trigger_direction,
        calculated_slope=request_data.get('trigger_slope_points'),
        headroom_pips=trigger_metrics.headroom_pips if trigger_metrics else None,
        risk_reward_ratio=trigger_metrics.risk_reward if trigger_metrics else None,
        higher_timeframe_bias=trigger_metrics.higher_timeframe_bias if trigger_metrics else None,
    )
    llm_ms = (time.perf_counter() - llm_t0) * 1000

    current_price = _latest_close_price(ingestor, symbol)

    ctx = GuardrailContext(
        symbol=symbol,
        market_snapshot_summary=payload.market_summary_text[:4000],
        llm_verdict=verdict.verdict,
        llm_confidence=verdict.confidence,
        llm_reasoning=verdict.reasoning,
        proposed_direction=trigger_direction if trigger_metrics else None,
        proposed_stop_loss=trigger_metrics.stop_loss if trigger_metrics else None,
        proposed_take_profit=trigger_metrics.take_profit if trigger_metrics else None,
        current_price=current_price,
        spread=float(request_data.get('spread', 0.0) or 0.0),
        open_trades_count=len(open_trades),
        account_equity=request_data.get('account_equity'),
    )
    result = guardrail.evaluate(ctx)

    reasoning = verdict.reasoning
    if result.vetoed:
        reasoning = f"{reasoning} [GUARDRAIL VETO: {result.veto_reason}]"

    total_ms = (time.perf_counter() - pipeline_t0) * 1000
    logger.info(f"timing symbol={symbol} llm_ms={llm_ms:.0f} total_ms={total_ms:.0f}")

    # Trade management (position_suggestions) is not yet implemented as its own
    # concern - Agent 2 filters NEW setups, it doesn't review existing positions.
    # An empty list is safe: the EA's ProcessPositionSuggestions() is a no-op on
    # an empty array, so open trades are simply left alone rather than mismanaged.
    return {
        "action": result.action,
        "confidence": verdict.confidence,
        "reasoning": reasoning,
        "stop_loss": result.stop_loss,
        "take_profit": result.take_profit,
        "timestamp": datetime.now().isoformat(),
        "trade_management": {
            "existing_trades": f"{len(open_trades)} open" if open_trades else "None",
            "position_suggestions": [],
        },
    }


def _latest_close_price(ingestor: Ingestor, symbol: str) -> Optional[float]:
    window_data = ingestor.window_manager.get_window_data(ingestor.window_key_for(symbol))
    if window_data and window_data.candles_1min:
        return window_data.candles_1min[-1].close_price
    if window_data and window_data.candles_5min:
        return window_data.candles_5min[-1].close_price
    return None


def _wait_response(reasoning: str, window_status: Optional[Dict] = None) -> Dict[str, Any]:
    resp = {
        "action": "WAIT",
        "confidence": 0,
        "reasoning": reasoning,
        "timestamp": datetime.now().isoformat(),
    }
    if window_status is not None:
        resp["window_status"] = window_status
    return resp


if __name__ == "__main__":
    app = create_app()
    app.run(host="localhost", port=8080, debug=True)
