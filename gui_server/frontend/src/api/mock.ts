import type { PywebviewApi } from './pywebview'
import type { FlatConfig, PromptVersion, SignalRecord, StrategySummary, TemplateRecord, TemplateSourceImage } from './types'

// Dev-mode stand-in for window.pywebview.api, used when the app is opened in
// a plain browser tab (`npm run dev`) instead of the actual pywebview
// window -- lets the UI be iterated on with instant HMR without launching
// the desktop shell on every change. Swapped in automatically by
// api/client.ts when window.pywebview never appears.

const delay = (ms = 150) => new Promise((r) => setTimeout(r, ms))

let mockConfig: FlatConfig = {
  host: '127.0.0.1',
  port: '8080',
  llm_provider: 'gemini',
  model: 'gemini-2.5-flash',
  api_key: '',
  temperature: '0.3',
  max_tokens: '4000',
  min_confidence: '70',
  min_risk_reward: '1.5',
  max_spread: '2.0',
  max_trades: '3',
  max_daily_drawdown_percent: '5.0',
}

let mockTheme = 'dark'
let mockServerRunning = false
let mockSignals: SignalRecord[] = [
  {
    action: 'BUY', symbol: 'XAUUSD', confidence: 78, timestamp: new Date(Date.now() - 6 * 60_000).toISOString(),
    reasoning: 'Price rejected the 20 EMA with a strong bullish body, matches the pullback continuation template. Higher-timeframe bias is aligned bullish.',
    entry_price: 2415.2, stop_loss: 2412.0, take_profit: 2421.8,
  },
  {
    action: 'WAIT', symbol: 'XAUUSD', confidence: 42, timestamp: new Date(Date.now() - 19 * 60_000).toISOString(),
    reasoning: 'Touch and confirmation candle present, but the setup does not resemble the reference template closely enough - body is too small relative to the prior range.',
    entry_price: null, stop_loss: null, take_profit: null,
  },
  {
    action: 'SELL', symbol: 'XAUUSD', confidence: 81, timestamp: new Date(Date.now() - 52 * 60_000).toISOString(),
    reasoning: 'Clean rejection from above the EMA with a strong bearish confirmation candle and sufficient downward slope. [VETOED: spread 3.2 exceeds max 2.0]',
    entry_price: 2409.6, stop_loss: 2412.4, take_profit: 2402.1,
  },
]
let mockHeartbeatSeenAt: number | null = Date.now()
const mockOpenTrade = {
  ticket: 900123456, type: 'BUY' as const, open_price: 2415.2, volume: 0.1,
  stop_loss: 2412.0, take_profit: 2421.8, open_time: new Date(Date.now() - 6 * 60_000).toISOString(),
}
const mockLogLines: string[] = [
  '2026-08-14 14:02:45,102 - Engine.Core - INFO - Initializing AegisVision AI Engine. Neural pathways established.',
  '2026-08-14 14:02:46,001 - Market.Feed - INFO - Connecting to primary data stream...',
  '2026-08-14 14:02:47,332 - Market.Latency - WARNING - Ping response degraded. Average latency 145ms (threshold 100ms).',
  '2026-08-14 14:03:12,899 - Strategy.Exec - ERROR - Order rejection on XAUUSD. Reason: INSUFFICIENT_MARGIN.',
  '2026-08-14 14:03:15,550 - System.Health - INFO - CPU 14% | RAM 4.3GB/16GB',
]
let mockLogClearOffset = 0

const mockStrategy: StrategySummary = { id: 'mock-strategy-1', name: 'Demo Strategy', category: 'Demo Strategy' }
let mockPrompt: PromptVersion | null = {
  strategy_name: 'vision_compliance_default',
  version: 1,
  text: 'You are Agent 2, a vision-compliance filter...',
  created_at: new Date().toISOString(),
  notes: '',
}

function emptyTemplates(): Record<string, TemplateRecord | null> {
  return { bullish_ideal: null, bearish_ideal: null, fail_trap: null }
}

// Real compositing only exists in the Python backend, so this can't produce
// an actual stitched JPEG -- it just echoes the most recently saved crop
// back as the "composite" so the UI (thumbnail update, enlarge, etc.) has
// something real to react to instead of a permanent null image. To see the
// real stitching pipeline, run the app via pywebview (AEGISVISION_DEV=1
// venv\Scripts\python gui_server\main.py) pointed at this Vite dev server,
// not a plain browser tab -- a browser tab has no Python backend to call.
const mockTemplates: Record<string, TemplateRecord | null> = emptyTemplates()
const mockSources: Record<string, TemplateSourceImage[]> = { bullish_ideal: [], bearish_ideal: [], fail_trap: [] }

export const mockApi: PywebviewApi = {
  async get_config() { await delay(); return { ...mockConfig } },
  async save_config(cfg) { await delay(); mockConfig = { ...cfg }; return true },
  async reset_config() { await delay(); return { ...mockConfig } },
  async get_theme() { await delay(50); return mockTheme },
  async set_theme(mode) { await delay(50); mockTheme = mode; return true },
  async export_config() { await delay(); return null },
  async import_config() { await delay(); return null },
  async test_connection() { await delay(400); return { success: false, message: 'Server not responding (mock dev mode)' } },
  async test_api_key() { await delay(400); return { success: true, message: 'Mock API key accepted' } },

  async start_server() { await delay(500); mockServerRunning = true; return true },
  async stop_server() { await delay(300); mockServerRunning = false; return true },
  async restart_server() { await delay(500); mockServerRunning = true; return true },
  async get_server_status() { await delay(50); return { is_running: mockServerRunning, url: `http://${mockConfig.host}:${mockConfig.port}` } },
  async get_server_stats() {
    await delay(50)
    return {
      total_requests: mockServerRunning ? 12 : 0,
      last_request_time: mockServerRunning ? new Date().toLocaleTimeString() : null,
      active_connections: mockServerRunning ? 1 : 0,
      uptime: mockServerRunning ? '00:04:12' : 'Not running',
      llm_provider: mockConfig.llm_provider,
      llm_model: mockConfig.model,
    }
  },
  async health_check() {
    await delay(200)
    return mockServerRunning ? { status: 'healthy', timestamp: new Date().toISOString(), active_connections: 1 } : null
  },

  async get_recent_signals(since = 0) {
    await delay(50)
    return { records: mockSignals.slice(0, 20), since: since + mockSignals.length }
  },
  async get_trade_telemetry() {
    await delay(50)
    const approved = mockSignals.filter((s) => s.action === 'BUY' || s.action === 'SELL').length
    return {
      total_evaluated: mockSignals.length,
      approved,
      rejected: mockSignals.length - approved,
      guardrail_vetoed: 0,
      approved_today: approved,
      last_decision_time: mockSignals[0]?.timestamp ?? null,
    }
  },
  async get_live_positions() {
    await delay(50)
    if (!mockServerRunning || mockHeartbeatSeenAt === null) {
      return { last_seen: null, seconds_since: null, symbol: '', open_trades: [] }
    }
    // Simulate a heartbeat landing every ~10s, same cadence as the real EA.
    if (Date.now() - mockHeartbeatSeenAt > 10_000) mockHeartbeatSeenAt = Date.now()
    // Small fake price wobble so the P&L visibly moves on each ~2s poll,
    // standing in for the real EA's live tick data.
    const wobble = Math.sin(Date.now() / 4000) * 1.8
    const currentPrice = mockOpenTrade.open_price + wobble
    const profit = wobble * mockOpenTrade.volume * 100
    return {
      last_seen: new Date(mockHeartbeatSeenAt).toISOString(),
      seconds_since: (Date.now() - mockHeartbeatSeenAt) / 1000,
      symbol: 'XAUUSD',
      open_trades: [{
        ...mockOpenTrade,
        current_price: Number(currentPrice.toFixed(2)),
        profit: Number(profit.toFixed(2)),
        swap: -0.4,
      }],
    }
  },

  async list_strategies() { await delay(); return [mockStrategy] },
  async create_strategy(name, category) { await delay(); return { id: `mock-${Date.now()}`, name, category: category || name } },
  async get_active_strategy() { await delay(); return mockStrategy },
  async set_active_strategy() { await delay(); return true },
  async get_strategy_templates() { await delay(); return { ...mockTemplates } },
  async get_template_sources(_sid, slot) { await delay(); return mockSources[slot] ?? [] },
  async save_template_source(_sid, slot, position, imageBase64, cropX, cropY, cropW, cropH, caption) {
    await delay(300)
    const now = new Date().toISOString()
    const list = (mockSources[slot] ?? []).filter((s) => s.position !== position)
    list.push({
      slot, position, filename: `${slot}/sources/${position}.png`,
      crop_x: cropX, crop_y: cropY, crop_w: cropW, crop_h: cropH,
      source_width: 0, source_height: 0, updated_at: now, image: imageBase64,
    })
    mockSources[slot] = list.sort((a, b) => a.position - b.position)
    const record: TemplateRecord = {
      slot, filename: `${slot}/composite.jpg`,
      caption: caption ?? mockTemplates[slot]?.caption ?? '', updated_at: now, image: imageBase64,
    }
    mockTemplates[slot] = record
    return record
  },
  async remove_template_source(_sid, slot, position) {
    await delay()
    mockSources[slot] = (mockSources[slot] ?? []).filter((s) => s.position !== position)
    const remaining = mockSources[slot]
    if (!remaining.length) { mockTemplates[slot] = null; return null }
    const last = remaining[remaining.length - 1]
    const record: TemplateRecord = {
      slot, filename: `${slot}/composite.jpg`,
      caption: mockTemplates[slot]?.caption ?? '', updated_at: new Date().toISOString(), image: last.image,
    }
    mockTemplates[slot] = record
    return record
  },
  async update_template_caption(_sid, slot, caption) {
    await delay()
    const existing = mockTemplates[slot]
    if (!existing) return null
    mockTemplates[slot] = { ...existing, caption, updated_at: new Date().toISOString() }
    return mockTemplates[slot]
  },
  async get_cell_aspect_ratio() { await delay(20); return 1 },
  async get_prompt() { await delay(); return mockPrompt },
  async list_prompt_versions() { await delay(); return mockPrompt ? [mockPrompt] : [] },
  async save_prompt(_sid, text, notes) {
    await delay()
    mockPrompt = { strategy_name: 'vision_compliance_default', version: (mockPrompt?.version ?? 0) + 1, text, created_at: new Date().toISOString(), notes: notes ?? '' }
    return mockPrompt
  },

  async start_extract() { await delay(); return 'mock-job-extract' },
  async start_replay() { await delay(); return { job_id: 'mock-job-replay' } },
  async get_job_output() {
    await delay(300)
    return { lines: ['[mock] backtest streaming not available outside pywebview'], since: 1, done: true, returncode: 0, progress: null }
  },
  async get_backtest_report() { await delay(); return null },

  async tail_log(offset = 0) {
    await delay(300)
    const effective = Math.max(offset, mockLogClearOffset)
    const lines = effective < mockLogLines.length ? mockLogLines.slice(effective) : []
    return { lines, new_offset: mockLogLines.length }
  },
  async get_log_stats() {
    await delay()
    const visible = mockLogLines.slice(mockLogClearOffset)
    const level_counts = { DEBUG: 0, INFO: 0, WARNING: 0, ERROR: 0, CRITICAL: 0 }
    for (const line of visible) for (const level of Object.keys(level_counts)) if (line.includes(`- ${level} -`)) level_counts[level as keyof typeof level_counts]++
    return { total_entries: visible.length, level_counts }
  },
  async clear_log() { await delay(); mockLogClearOffset = mockLogLines.length; return mockLogClearOffset },
  async export_log() { await delay(); return null },
  async open_log_file() { await delay(); return false },
}
