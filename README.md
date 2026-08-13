# AegisVision AI

A multi-agent LLM trading system for MT5: an Expert Advisor feeds live multi-timeframe
market data to a Python backend, which runs it through a vision-based strategy-compliance
filter (Gemini) and a deterministic risk guardrail before sending a trade decision back
to MT5. Includes a desktop GUI (CustomTkinter) and an offline backtest replay harness.

Forked from an earlier prototype (`orb_ai_strategy`), restructured into a clearer
4-agent pipeline:

```
MT5 EA (Agent 0)  --candles+indicators-->  Ingestor (Agent 1)
                                                 |
                                    text summary + chart image
                                                 v
                                   Vision Compliance Filter (Agent 2)
                                        [Gemini, 2-shot templates]
                                                 |
                                          ACCEPT/REJECT verdict
                                                 v
                                     Risk & Audit Guardrail (Agent 3)
                                   [hard vetoes, immutable audit log]
                                                 |
                                          final BUY/SELL/WAIT
                                                 v
                                          MT5 EA executes/manages
```

## Project layout

- `ea/AegisVision_EA.mq5` - the MT5 Expert Advisor. Sends 1min/5min/1hour candle data,
  executes trades, manages open positions. The actual entry-trigger strategy is a
  placeholder (`ShouldEvaluateSetup()`) - swap its body for your real strategy logic;
  everything downstream already works.
- `gui_server/` - the desktop app: CustomTkinter GUI + embedded Flask backend.
  - `gui/` - GUI tabs (Configuration, Server Control, Templates, Backtest, Logs).
  - `server/agents/` - the three Python agents (`ingestor.py`, `vision_compliance.py`, `guardrail.py`).
  - `server/llm/` - pluggable LLM provider interface (Gemini wired up; OpenAI/Anthropic stubbed).
  - `storage/` - local-file storage interfaces (prompts, template images) designed to be
    swapped for a Supabase-backed implementation later without touching the agents.
  - `templates_store/` - your uploaded 2-shot reference chart images (via the Templates tab).
  - `storage_data/` - audit log (JSONL, one record per trade decision), saved prompt versions,
    daily-drawdown state. Not committed to git - this is your personal trading history.
- `backtest/` - offline replay harness: extracts historical trigger events from the seed
  CSVs and replays them through the *real* pipeline (real Gemini calls, throttled) to
  compare a naive "take every trigger" baseline against the AI-filtered result.
- `data_seed/` - historical XAUUSD M1/M5 CSVs (2018-era) to seed backtests. Not committed to
  git (XAUUSD_M1.csv alone is ~196MB, over GitHub's 100MB push limit) - re-export these from
  your broker/data vendor into `data_seed/` before running `backtest/`.
- `tests/` - unit tests for the sliding window and guardrail logic (no network/API key needed).

## Setup

1. **Python environment**
   ```
   python -m venv venv
   venv\Scripts\pip install -r gui_server\requirements.txt
   ```

2. **API key** - copy `.env.example` to `.env` and fill in your Gemini key:
   ```
   GEMINI_API_KEY=your-key-here
   ```
   `.env` is gitignored - never commit it.

3. **Run the desktop app**
   ```
   venv\Scripts\python gui_server\main.py
   ```
   Go to the **Configuration** tab, confirm host/port/provider, then **Server Control** ->
   Start Server.

4. **MT5 setup**
   - Open MetaEditor, compile `ea/AegisVision_EA.mq5`, attach it to a chart (demo account
     recommended while testing).
   - **Required one-time step per machine**: in MT5, Tools -> Options -> Expert Advisors ->
     check "Allow WebRequest for listed URL" and add `http://127.0.0.1:8080` (or whatever
     host:port you configured). Without this, `WebRequest` silently fails - the EA can't
     self-configure this.
   - Leave `EnableTrading = false` until you've confirmed signals look sane in the GUI's
     Server Control / Logs tabs, then flip it on.

5. **Templates** (optional but recommended) - go to the **Templates** tab and upload your
   "gold standard" reference charts (ideal bullish setup, ideal bearish setup, a fail/trap
   setup to avoid) with captions. Without these, Agent 2 still works (text + live chart
   only) but is less calibrated to your specific strategy.

## Backtesting

```
venv\Scripts\python backtest\extract_triggers.py --start-date 2018-02-01 --end-date 2018-03-01 --interval-minutes 60 --max-events 100
venv\Scripts\python backtest\replay_harness.py --throttle-seconds 12
```
Or use the **Backtest** tab in the GUI, which runs the same scripts and shows the
before/after metrics table. Each event makes a real (throttled) Gemini call, so a few
hundred events will take a while - this is intentional, not a bug, to respect API rate
limits.

## Known gaps / next steps

- **Trigger strategy**: `ShouldEvaluateSetup()` in the EA is a time-interval placeholder.
  Replace it with your real setup-detection logic when ready.
- **Trade management**: Agent 2 currently only filters *new* setups; it doesn't review
  open positions (the old prototype's `position_suggestions` field is always sent empty,
  which the EA handles as a safe no-op - existing trades are simply left alone).
- **Dual-model fallback**: only Gemini is wired up. `server/llm/openai_provider.py` and
  `anthropic_provider.py` are stubbed against the same `LLMProvider` interface for later.
- **Supabase migration**: `storage/prompt_store.py` and `storage/template_image_store.py`
  are local-file implementations behind an interface designed for this; a Supabase-backed
  implementation (and eventually a web dashboard) is a contained addition, not a rewrite.
- **PyInstaller packaging**: `gui_server/aegisvision_server.spec` / `build_exe.bat` are
  updated and ready but not yet run end-to-end into a distributable .exe.
