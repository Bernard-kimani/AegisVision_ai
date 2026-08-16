# AegisVision AI

A multimodal multi-agent trading system for MetaTrader 5: a deterministic Expert
Advisor detects a mechanical setup, a vision-language model judges whether that
specific setup actually looks like a high-probability trade, and a fully
deterministic risk engine cross-validates both before anything reaches a broker.
Domain: financial services / algorithmic execution on XAU/USD (gold), built as
a reusable framework, not a one-off script tied to this one strategy.

**Live demo**: [PUT_NETLIFY_URL_HERE](PUT_NETLIFY_URL_HERE) — a UI-only preview
of the desktop app (Controls, Strategies, Backtest, Logs). It runs against a
mock API with simulated data, not a live MT5 feed or real Gemini calls, so you
can click through the full interface with zero setup. The real pipeline runs
locally against your own MT5 terminal and API key - see Setup below.

## Problem Statement & Domain Bottleneck

Rule-based Expert Advisors have a filtering paradox: tighten the entry rules
enough to cut the clear losers, and you also cut a meaningful share of the
winners, because "does this setup actually look right" is a judgment call a
human trader makes by eye — reading candle structure, headroom, and multi-timeframe
context together — not a call that reduces cleanly to a handful of `if`
statements. Loosen the rules back up and the strategy is back to trading every
mechanical trigger, most of which are marginal. A backtest over several months
of a mechanical strategy easily produces 800-1,000+ raw trigger events; the
realistic trading calendar underneath that (about 20-22 trading days/month) means
most of those events are close in time and quality to each other. The
edge isn't in finding more triggers — it's in identifying which subset of triggers
the setup was clean enough on to actually take.

AegisVision AI's answer: keep the mechanical trigger deterministic and auditable
(no LLM decides *when* a setup exists), and let a multimodal LLM act purely as
a **filter** — the trained eye that decides whether *this instance* of the
setup is one you'd take if you were sitting at the chart. A separate,
non-LLM risk engine then cross-checks the LLM's own read against the EA's real
numbers before any trade executes. This is the trade-selection problem applied
to real-time execution, not another generic chat-with-your-portfolio assistant.

## Multi-Agent Architecture Topology (4 Specialized Agents)

AegisVision AI runs a 4-agent pipeline spanning MT5 and a Python backend,
exceeding the standard dual-agent (retrieve + generate) pattern. Only one
of the four agents makes an LLM call — the other three are deterministic,
auditable, and independently testable:

```text
MT5 EA (Agent 0)  --candles + indicators + open-trade context-->  Ingestor (Agent 1)
   deterministic                                                    deterministic
   mechanical trigger                                       text summary + chart image
   + trade execution                                                    |
                                                                          v
                                                     Vision & Compliance Filter (Agent 2)
                                                        [Gemini 2.5 Flash, multimodal]
                                                          the only LLM call in the loop
                                                                          |
                                                              ACCEPT/REJECT + confidence
                                                              + its own independent SL/TP
                                                                          v
                                                          Risk & Audit Guardrail (Agent 3)
                                                        deterministic, hard vetoes,
                                                        immutable audit log
                                                                          |
                                                                final BUY/SELL/WAIT
                                                                          v
                                                             MT5 EA executes/manages
```

| Agent | Role | LLM? | What it owns |
|---|---|---|---|
| **Agent 0 — Mechanical Trigger & Execution** (`ea/AegisVision_EA.mq5`) | Detects the setup on-chart using whatever mechanical trigger this deployment is configured with — for this case, a moving-average pullback confirmed by candle structure and a momentum-slope gate — computes its own fixed-ratio stop-loss/take-profit, executes/manages orders | No | Trigger detection, order execution, its own per-EA-magic-number trade-count cap, spread/session gating |
| **Agent 1 — Ingestor / Preprocessor** (`gui_server/server/agents/ingestor.py`) | Keeps a continuously-updated, multi-timeframe view of the market and distills it into what Agent 2 needs: a curated market-summary text block, a rendered chart image, and deterministic structural context (headroom to the nearest swing liquidity, multi-timeframe bias) | No | Freshness and feature curation — plain arithmetic, zero model calls |
| **Agent 2 — Vision & Strategy Compliance Filter** (`gui_server/server/agents/vision_compliance.py`) | Judges each candidate setup against this deployment's actual trading criteria — encoded as a versioned strategy prompt — with the live chart and reference images as visual grounding for that same criteria; returns ACCEPT/REJECT with a confidence score, reasoning, and its **own independently-derived** stop-loss/take-profit | **Yes — the sole LLM call** | Discretionary trade judgment, grounded in both the written strategy and what the chart actually shows |
| **Agent 3 — Risk & Audit Guardrail** (`gui_server/server/agents/guardrail.py`) | Deterministic veto chain: confidence threshold, risk:reward cross-check, spread, high-impact news blackout, persisted daily-drawdown limit. Writes one immutable audit record per decision, vetoed or not | No | The only place Agent 0's real numbers and Agent 2's independent numbers are ever compared |

The loop closes back where it started: Agent 3's output is the only instruction
Agent 0 ever receives back, and it's Agent 0 — the same EA that raised the
candidate in the first place — that actually executes and manages the trade.
Nothing downstream ever touches an order directly; MT5 only ever acts on its
own EA's command, so detection and execution stay in the hands of the one
component that's actually on the chart.

## The Ingestor: Always-Current Context, Not a Raw Data Dump

Agent 1 has no opinion on the trade. Its entire job is making sure Agent 2 never
has to reason from stale or noisy data, and it does two things continuously,
well before any trigger fires:

- **Sliding-window freshness** — rolling buffers across three timeframes
  (1-minute, 5-minute, 1-hour) are kept live in memory, updated candle-by-candle
  as data streams in from the EA. By the time a trigger fires, Agent 2 isn't
  waiting on a fetch — the latest closed candle on every timeframe is already
  sitting there.
- **Curated, not raw, market context** — rather than handing the model a wall
  of OHLC numbers, Agent 1 reads across a set of technical indicators (moving
  averages, RSI, multi-timeframe swing structure, higher-timeframe bias) and
  writes out only what actually bears on *this* trigger: headroom to the
  nearest swing liquidity, which side of the higher-timeframe trend price sits
  on, whether the shorter-term structure agrees or disagrees with it. That's
  the difference between "here's a spreadsheet, figure it out" and "here's
  what actually matters about this moment" — and it's what lets the one
  expensive model call downstream be spent on judgment, not arithmetic.

Nothing here calls a model — it's the deterministic groundwork that makes the
LLM call worth making.

## Multimodal Vision & Technical Setup Filter

Agent 2 never decides *whether* a setup exists — Agent 0 already did, deterministically.
What Agent 2 decides is whether *this instance* of the setup is worth taking — and that
judgment is driven primarily by words, not pixels. The strategy itself — what actually
counts as a valid setup for this deployment — is encoded as a versioned, user-editable
text prompt (`storage/prompt_store.py`): a trading checklist a human analyst would
recognize, not a vague vibe. The images exist to *complement* that checklist, not replace
it — they let the model confirm the criteria the prompt describes actually hold on this
specific chart, the same way a trader learns a rule set once and then checks each new
chart against it by eye. Three inputs are sent to the model as multimodal content in one call:

- **The strategy prompt** — the actual compliance criteria for this deployment
  (structure, headroom, alignment, position-stacking judgment), edited from the GUI,
  every revision saved rather than overwritten so prompt iteration itself is auditable.
- **Image A / B** — user-uploaded reference charts: an annotated "ideal" continuation
  setup for the fired direction, and an annotated "fail/trap" setup to avoid. Two-shot
  visual grounding for the written criteria, not zero-shot guessing.
- **Image C + deterministic metrics** — the live chart at the moment the trigger fired,
  alongside the calculated MA-slope value, headroom to the nearest swing high/low,
  higher-timeframe bias, and any currently open positions — computed by Agent 1, not
  guessed by the model.

On ACCEPT, Agent 2 proposes its own stop-loss/take-profit purely from what it sees on
the chart — with **zero visibility into Agent 0's own SL/TP numbers** — so that Agent 3's
downstream comparison of the two is a genuine independent cross-check, not a rubber stamp
of a number it was already shown. It fails closed: any parse error or LLM/network failure
returns REJECT at 0 confidence, never a silent ACCEPT.

## Guardrail & Deterministic Risk Management Engine

Agent 3 is the one place in the system Agent 0's real numbers and Agent 2's
independent numbers ever meet, and it can override the LLM regardless of how
confident it was. Checks run in a fixed order, first failure wins:

1. **Confidence threshold** — reject low-conviction ACCEPTs outright.
2. **Risk:Reward cross-validation** — Agent 0's real stop-loss (the risk leg,
   what will actually be traded) against Agent 2's own independently-proposed
   take-profit (the reward leg, its independent read of how much room the move
   has). If the LLM's own target doesn't clear the EA's real risk by the
   configured minimum R:R, the trade is vetoed here — even on a confident
   ACCEPT. Missing data on either side fails closed, not open.
3. **Spread** — vetoes on abnormally wide spread at signal time.
4. **News blackout** — hard-blocks trading inside a configurable window around
   high-impact calendar events, independent of how confident Agent 2 was.
5. **Daily drawdown** — a limit that must survive a server restart mid-day, so
   it's persisted to disk (`storage_data/`) keyed by trading day, not held only
   in memory.

Every evaluation — vetoed or not — writes one immutable JSONL audit record
(entry price, both agents' SL/TP, the computed R:R, the veto reason if any,
final action) via `audit/audit_log.py`. This is deliberately compliance-shaped:
a full, append-only decision trail is exactly what a risk desk or auditor would
ask a real trading system to produce.

## Reusable by Design — Bring Your Own Strategy

Nothing about Agent 1-3 is hardcoded to gold, or to this deployment's specific
pullback strategy. The
**Strategies** tab is the reusability surface: define a new strategy, upload
your own "ideal setup" and "fail/trap" reference charts with captions, and
edit Agent 2's prompt directly from the GUI — each edit is versioned, not
overwritten. Swap in a different mechanical trigger on the EA side (the trigger
function is a small, isolated, well-documented state machine) and the rest of
the pipeline — ingestion, vision filtering, risk cross-validation, backtesting,
audit logging — works unchanged. The LLM provider layer is behind the same
`LLMProvider` interface (`server/llm/`) with Gemini wired up today and
OpenAI/Anthropic already stubbed against the identical interface, so swapping
model vendors doesn't touch the agent logic at all. The same pattern generalizes
past trading: any workflow that needs "a deterministic system flags a candidate,
a vision-capable model judges whether this specific instance is good, a
deterministic engine has final veto power" — document triage, industrial
inspection, physical-security review — is the same 4-agent shape with a
different Agent 0/1 and reference-image set.

## Solving the "Can't Backtest AI Signals" Problem

MT5's Strategy Tester blocks `WebRequest` entirely during backtesting — an EA
cannot call out to an LLM inside MT5's own backtester, which is normally a dead
end for any AI-in-the-loop strategy. `backtest/` is a standalone offline replay
harness that sidesteps this by running the pipeline outside MT5 entirely:

1. **`extract_triggers.py`** scans historical market data with a Python port
   of the EA's actual mechanical trigger (`backtest/trigger_detector.py`,
   mirroring `CheckStrategyTrigger()` line-for-line) — so replay runs over the
   *exact* setup logic the EA fires on live, not an approximation or a fixed
   time-sample. The port is strategy-agnostic by construction: it walks
   whatever trigger this deployment's EA is configured with, so a different
   strategy on the EA side needs a matching (but equally small) port, not a
   rewrite of the harness around it.
2. **`replay_harness.py`** replays each historical event through the real
   `Ingestor` / `VisionComplianceFilter` / `RiskGuardrail` classes — the same
   Python objects the live server runs, with real (throttled) Gemini calls —
   and simulates both a "take every raw trigger" baseline and the AI-filtered
   result against the same price data.
3. The **Backtest** tab renders a before/after table: win rate, profit factor,
   expectancy per trade, max drawdown, and total P&L, raw vs. AI-filtered,
   side by side.

Because the throttle is configurable, this is also how strategy/prompt changes
get validated cheaply before ever going live — run a few hundred historical
events, read the before/after delta, tune the prompt or the risk thresholds,
repeat, all without touching a demo account.

## Project layout

- `ea/AegisVision_EA.mq5` - the MT5 Expert Advisor (Agent 0). Sends 1min/5min/1hour
  candle data, executes trades, manages open positions, gates its own trade count
  and spread. The mechanical trigger (`CheckStrategyTrigger()`) is a real, working
  strategy chosen for this deployment — swap its body for a different strategy and
  everything downstream keeps working unchanged.
- `gui_server/` - the desktop app: a React frontend packaged with pywebview + embedded Flask backend.
  - `frontend/` - the React/TypeScript/Tailwind UI (Controls, Strategies, Backtest, Logs tabs).
  - `webview_api.py` - the GUI-facing control surface exposed to the frontend as `window.pywebview.api.*`.
  - `server/agents/` - the three Python agents (`ingestor.py`, `vision_compliance.py`, `guardrail.py`).
  - `server/llm/` - pluggable LLM provider interface (Gemini wired up; OpenAI/Anthropic stubbed).
  - `storage/` - local-file storage interfaces (prompts, template images) designed to be
    swapped for a Supabase-backed implementation later without touching the agents.
  - `templates_store/` - legacy global reference chart images, from before the Strategies tab
    (per-strategy templates now live under `strategies_store/{id}/templates/`).
  - `storage_data/` - audit log (JSONL, one record per trade decision), saved prompt versions,
    daily-drawdown state. Not committed to git - this is your personal trading history.
- `backtest/` - offline replay harness: extracts historical trigger events from the seed
  CSVs using the EA's real mechanical trigger logic, and replays them through the *real*
  pipeline (real Gemini calls, throttled) to compare a naive "take every trigger" baseline
  against the AI-filtered result.
- `data_seed/` - historical XAUUSD M1/M5 CSVs (2018-era) to seed backtests. Not committed to
  git (XAUUSD_M1.csv alone is ~196MB, over GitHub's 100MB push limit) - re-export these from
  your broker/data vendor into `data_seed/` before running `backtest/`.
- `tests/` - unit tests for the sliding window and guardrail logic (no network/API key needed).

## Setup

1. **Python environment**

   ```bat
   python -m venv venv
   venv\Scripts\pip install -r gui_server\requirements.txt
   ```

2. **Frontend build** (one-time, and again after pulling frontend changes)

   ```bat
   cd gui_server\frontend
   npm install
   npm run build
   cd ..\..
   ```

   For UI development with hot-reload instead: `npm run dev` in `gui_server/frontend`, then
   run the app with the `AEGISVISION_DEV=1` env var set (step 4) so it points at the Vite
   dev server instead of the built `frontend/dist`.

3. **API key** - copy `.env.example` to `.env` and fill in your Gemini key:

   ```bash
   GEMINI_API_KEY=your-key-here
   ```

   `.env` is gitignored - never commit it.

4. **Run the desktop app**

   ```bat
   venv\Scripts\python gui_server\main.py
   ```

   Go to the **Controls** tab, confirm host/port/provider, then **Start Server**.

5. **MT5 setup**
   - Open MetaEditor, compile `ea/AegisVision_EA.mq5`, attach it to a chart (demo account
     recommended while testing).
   - **Required one-time step per machine**: in MT5, Tools -> Options -> Expert Advisors ->
     check "Allow WebRequest for listed URL" and add `http://127.0.0.1:8080` (or whatever
     host:port you configured). Without this, `WebRequest` silently fails - the EA can't
     self-configure this.
   - Leave `EnableTrading = false` until you've confirmed signals look sane in the GUI's
     Controls / Logs tabs, then flip it on.

6. **Strategies** (optional but recommended) - go to the **Strategies** tab, create a
   strategy, and upload your "gold standard" reference charts (ideal bullish setup, ideal
   bearish setup, a fail/trap setup to avoid) with captions, plus tune the Agent 2 prompt.
   Without these, Agent 2 still works (text + live chart only) but is less calibrated to
   your specific strategy.

## Backtesting

```bat
venv\Scripts\python backtest\extract_triggers.py --start-date 2018-02-01 --end-date 2018-03-01 --max-events 100
venv\Scripts\python backtest\replay_harness.py --throttle-seconds 12
```

Or use the **Backtest** tab in the GUI, which runs the same scripts and shows the
before/after metrics table. Each event makes a real (throttled) Gemini call, so a few
hundred events will take a while - this is intentional, not a bug, to respect API rate
limits.
