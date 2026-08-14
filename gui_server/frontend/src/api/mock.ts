import type { PywebviewApi } from './pywebview'
import type { FlatConfig, PromptVersion, SignalRecord, StrategySummary, TemplateRecord } from './types'

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
let mockSignals: SignalRecord[] = []
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

  async list_strategies() { await delay(); return [mockStrategy] },
  async create_strategy(name, category) { await delay(); return { id: `mock-${Date.now()}`, name, category: category || name } },
  async get_active_strategy() { await delay(); return mockStrategy },
  async set_active_strategy() { await delay(); return true },
  async get_strategy_templates() { await delay(); return emptyTemplates() },
  async get_template_sources() { await delay(); return [] },
  async save_template_source(_sid, slot) {
    await delay(300)
    return { slot, filename: `${slot}/composite.png`, caption: '', updated_at: new Date().toISOString(), image: null }
  },
  async remove_template_source() { await delay(); return null },
  async update_template_caption(_sid, slot, caption) {
    await delay()
    return { slot, filename: `${slot}/composite.png`, caption, updated_at: new Date().toISOString(), image: null }
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
