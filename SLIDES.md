# AegisVision AI — Pitch Deck Content (GoAI Boundless Agents / AI+Finance Track)

12 slides. Each block below is one slide: **Title**, then the content to put on
it. Written for both audiences at once — explicit headers/keywords for an
automated first-pass reader, and a real narrative + real numbers for the human
panel behind it. Every number below is pulled from the actual codebase/config,
not invented — swap in your own screenshots/GIFs of the Controls, Strategies,
and Backtest tabs where noted.

## Brand Reference — Match the App's Own Identity

Pulled straight from the app's design tokens (`gui_server/frontend/src/index.css`)
so the deck reads as one product with the software, not a separate design.

**Logo wordmark** — "Aegis" + "Vision" + " AI", set in **Wallpoet** (a
geometric, blocky display face — self-hosted, no fallback needed if you embed
the font file; otherwise falls back to IBM Plex Mono). Coloring is gold /
primary-text / gold:

- "Aegis" — accent gold
- "Vision" — primary text color (near-black on the light theme, cream on dark)
- " AI" — accent gold

**Core palette** (dark theme, the more presentation-friendly of the two):

| Token | Hex | Use |
|---|---|---|
| Ground / background | `#121212` | Slide background |
| Surface | `#1a1a1a` | Cards, panel fills |
| Accent gold | `#c6a75e` | Logo, headings, key numbers, dividers |
| Accent gold (hover/bright) | `#d9bd7a` | Highlights, emphasis on gold elements |
| Primary text | `#f3ede6` | Body copy, the "Vision" of the wordmark |
| Secondary text | `#b9b3a8` | Captions, de-emphasized notes |

**Light theme equivalents**, if you'd rather present on a light deck:
ground `#f3ede6`, surface `#e9e1d4`, accent gold `#c6a75e` (same gold both
themes), primary text `#0f1a14`, secondary text `#55605a`.

**Supporting type system** (for body copy/headings beyond the logo itself):
**Fraunces** (warm display serif) for slide titles, **IBM Plex Sans** for body
text, **IBM Plex Mono** for any numbers/metrics/code — the same pairing the
app uses to separate "judgment" content from "instrument" content.

---

## Slide 1 — Title

**AegisVision AI**
*A Multi-Agent, Multimodal Guardrail System for Algorithmic Trade Execution*

- Track: AI + Finance — Boundless Agents (real-world deployment, not a chatbot)
- 4-agent topology · Multimodal vision (Gemini 2.5 Flash) · MetaTrader 5 · XAU/USD

*Visual: the pipeline diagram from the README, or a screenshot of the Controls
tab with the EA-connected badge live.*

---

## Slide 2 — Problem Statement & Domain Bottleneck

**Rule-based filters cut winners along with losers**

- A mechanical strategy backtest over a few months of data easily produces
  800–1,000+ raw trigger events on a single instrument.
- Tightening the entry rules to remove clear losers by code alone also removes
  a meaningful share of the *good* trades — "does this setup actually look
  right" is a visual, contextual judgment call, not one that reduces cleanly
  to a handful of `if` statements.
- Loosen the rules back up, and you're back to trading every marginal trigger.
- **The real edge isn't finding more setups — it's correctly identifying which
  subset of a strategy's own triggers were clean enough to take.**
- Domain fit: risk alerts, rule matching, workflow assistance — applied to
  live financial execution, not portfolio Q&A.

---

## Slide 3 — The Insight: Separate Signal from Judgment

**Keep detection deterministic. Make judgment the LLM's only job.**

- Don't ask an LLM to decide *when* a setup exists — that stays a deterministic,
  auditable, backtestable state machine.
- Ask it to decide *whether this specific instance* is one a discretionary
  trader would actually take — the "eye test" a human does, at scale, without
  fatigue or fear/greed.
- Then don't trust that judgment blindly either: cross-validate it against a
  second, independent, deterministic read before it ever reaches a broker.
- This 3-part separation (mechanical trigger → visual/contextual filter →
  deterministic risk cross-check) is the system's core design decision.

---

## Slide 4 — Multi-Agent Architecture Topology (4 Specialized Agents)

**AegisVision AI utilizes a 4-Agent Topology exceeding standard dual-agent paradigms.**

| # | Agent | Role | LLM call? |
|---|---|---|---|
| 0 | Mechanical Trigger & Execution (MT5 EA) | Detects the setup, executes/manages orders, gates its own trade count | No |
| 1 | Ingestor / Preprocessor | Builds market-summary text + chart image + structural metrics | No |
| 2 | Vision & Strategy Compliance Filter | Multimodal ACCEPT/REJECT judgment + its own SL/TP read | **Yes — the only one** |
| 3 | Risk & Audit Guardrail | Deterministic veto chain + immutable audit log | No |

- Only 1 of 4 agents ever calls a model — the rest are deterministic,
  independently unit-testable, and fully auditable.
- Full request/response loop: MT5 → Ingestor → Vision Filter → Guardrail → MT5.
- **The loop closes where it started**: Agent 3's verdict is the only thing
  Agent 0 ever hears back, and Agent 0 — the same EA that raised the
  candidate — is what actually executes and manages the trade. Nothing
  downstream ever touches an order directly.

*Visual: the ASCII pipeline diagram from the README, redrawn as a real diagram.*

---

## Slide 5 — Agent 0: The Mechanical Trigger (MT5 EA)

**Deterministic setup detection, zero AI in the hot loop — and swappable per deployment**

- The trigger is a configuration, not a fixed rule baked into the pipeline:
  whatever mechanical setup this EA is built to watch for, it detects it the
  same deterministic way — touch → confirming candle → momentum gate — before
  anything downstream ever gets involved.
- **For this deployment**, the chosen setup is a moving-average pullback
  confirmed by candle structure and a momentum-slope gate. Slope is measured
  as `Slope = (MA_now − MA_(t−n)) / n` over a lookback window, in broker
  points — the same calculation live and in backtests.
- Owns its own trade-count cap and news-blackout window config — the server is
  never even asked once the cap is hit, by design.
- A matching Python port of this exact state machine is what powers the
  backtest replay harness (Slide 9) — same logic path live and offline.

---

## Slide 6 — Agent 1: The Ingestor — Always-Current, Never a Raw Dump

**No opinion on the trade — its job is making sure Agent 2 never reasons from stale or noisy data**

- **Freshness by construction**: rolling sliding-window buffers across three
  timeframes are kept live in memory, updated candle-by-candle as data
  streams in. By the time a trigger fires, the latest closed candle on every
  timeframe is already sitting there — no fetch, no wait.
- **Curation, not a transcript**: rather than handing the model a wall of raw
  OHLC numbers, it reads across a set of technical indicators — moving
  averages, RSI, multi-timeframe swing structure, higher-timeframe bias — and
  writes out only what actually bears on *this* trigger: headroom to the
  nearest liquidity, which side of the higher-timeframe trend price sits on,
  whether shorter-term structure agrees with it.
- That distillation is what lets the one expensive model call downstream be
  spent entirely on judgment — not on re-deriving arithmetic the system
  already knows.
- Also renders the live chart image (with the strategy's indicators drawn on
  it) that Agent 2 sees alongside the text — same underlying data, two forms.

---

## Slide 7 — Multimodal Vision & Technical Setup Filter (Agent 2)

**Model stack: Gemini 2.5 Flash, multimodal, single call per trigger — driven by words, grounded by pixels**

- **The strategy lives in the prompt, not the image.** What actually counts
  as a valid setup for this deployment is a versioned, user-editable text
  checklist — a trading rule set a human analyst would recognize — edited
  from the GUI, every revision saved rather than overwritten.
- **The images are grounding, not the source of truth.** They let the model
  confirm the written criteria actually hold on this specific chart — the
  live chart (Image C) plus two-shot reference images: an "ideal setup"
  (Image A) and a "fail/trap" to avoid (Image B).
- Deterministic metrics from Agent 1 (slope, headroom, higher-timeframe bias,
  open positions) ride alongside the prompt and images in the same call —
  the model reasons over words, numbers, and pixels together, not any one
  alone.
- On ACCEPT, proposes its **own** stop-loss/take-profit purely from the chart
  — with zero visibility into the EA's own numbers, so the downstream
  cross-check in Agent 3 is real, not circular.
- Fails closed: any parse error or API failure returns REJECT at 0 confidence
  — never a silent ACCEPT.

---

## Slide 8 — Guardrail & Deterministic Risk Management Engine (Agent 3)

**The one place the EA's real numbers and the model's independent numbers ever meet**

Fixed-order veto chain, first failure wins:

1. Confidence threshold (default 70%)
2. **Risk:Reward cross-check** — EA's real stop (risk leg) vs. the model's own
   proposed take-profit (reward leg), minimum R:R configurable (default 1.5) —
   missing data on either side fails **closed**, not open
3. Spread ceiling (default 2.0)
4. High-impact news blackout window (configurable minutes, EA-side input)
5. Daily drawdown limit (default 5%), **persisted to disk** — survives a
   server restart mid-trading-day

- Every evaluation — vetoed or not — writes one immutable JSONL audit record:
  both agents' SL/TP, the computed R:R, the veto reason if any, final action.
- This is a real deterministic engine that can override a confident LLM
  ACCEPT — not a formality to hit an agent-count minimum.

---

## Slide 9 — Solving the "Can't Backtest AI Signals" Problem

**MT5's Strategy Tester blocks `WebRequest` entirely — an EA cannot call an LLM inside MT5's own backtester**

- Built a standalone Python replay harness (`backtest/`) that runs the pipeline
  outside MT5, over real historical market data.
- Step 1 extracts real mechanical trigger events using a verified 1:1 port of
  the EA's own trigger logic — not a fixed time-interval sample.
- Step 2 replays each event through the **actual** production classes
  (`Ingestor`, `VisionComplianceFilter`, `RiskGuardrail`) with real, throttled
  Gemini calls.
- Step 3 renders a before/after table: win rate, profit factor, expectancy,
  max drawdown, total P&L — raw "take every trigger" baseline vs. AI-filtered.
- This is also the strategy/prompt-tuning loop: run a few hundred historical
  events, read the delta, tune, repeat — before ever touching a demo account.

---

## Slide 10 — Reusable by Design — Bring Your Own Strategy

**Not hardcoded to gold, or to this deployment's specific pullback strategy**

- The **Strategies** tab is the reusability surface: create a strategy, upload
  your own "ideal" and "fail/trap" reference charts, edit Agent 2's prompt
  directly from the GUI — versioned, never silently overwritten.
- Swap the mechanical trigger on the EA side (an isolated, documented state
  machine) and the rest of the pipeline — ingestion, filtering, risk
  cross-validation, backtesting, audit logging — works unchanged.
- LLM vendor is behind one interface (`LLMProvider`): Gemini live today,
  OpenAI/Anthropic already stubbed against the identical interface.
- The same shape generalizes past trading: **deterministic candidate
  detector → vision-capable judgment filter → deterministic veto engine** is
  applicable anywhere a system needs to flag a candidate, have a model judge
  the specific instance, and keep final say with a rule engine.

---

## Slide 11 — Engineering Rigor: Fail-Closed, Auditable, Cross-Validated

**Built like a risk desk would need it built, not like a demo**

- Fail-closed at every LLM boundary: parse errors and API failures become
  REJECT/veto, never a silent pass-through.
- Immutable, append-only audit trail (JSONL) for every decision, accepted or
  vetoed — full traceability of what was seen, what was decided, and why.
- Daily-drawdown state persists across server restarts — a safety limit that
  can't be reset by an outage.
- Unit-tested guardrail logic (`tests/test_guardrail.py`) runs with zero
  network calls — the deterministic core is verifiable in isolation from the
  model.
- Full desktop GUI (React + pywebview) with live Controls, Strategies,
  Backtest, and Logs tabs — this is a working application, not a script.

---

## Slide 12 — Thank You

**AegisVision AI**
*A Multi-Agent, Multimodal Guardrail System for Algorithmic Trade Execution*

- Deterministic where it can be. A model only where judgment is genuinely needed.
  A veto engine that means it.
- Questions welcome.

---

### Notes for building the actual slides

- Per-request latency (`llm_ms`/`total_ms`) is already measured and logged by
  the live server on every request — it just hasn't been aggregated into one
  benchmark number across many runs yet. Run that aggregation once you have
  real request volume and use the real figure, rather than estimating.
- Any other claim needing a number you don't have yet ($/backtest run, win
  rate) should either be measured for real before presenting it, or phrased
  explicitly as a target/estimate — judges (and an LLM judge parsing for
  concrete numbers) weight a real measured number far higher than a vague
  one, and an invented one is a real credibility risk if anyone checks.
- Keep the explicit headers ("Multi-Agent Architecture Topology", "Guardrail &
  Deterministic Risk Management Engine", etc.) in the actual slide titles —
  they're doing double duty as both the visual title and the automated-parser
  keyword match.
