// Shapes mirror gui_server/webview_api.py's return values 1:1 -- keep in sync
// with that file when the API surface changes.

export interface FlatConfig {
  host: string
  port: string
  llm_provider: 'openai' | 'anthropic' | 'gemini' | string
  model: string
  api_key: string
  temperature: string
  max_tokens: string
  min_confidence: string
  min_risk_reward: string
  max_spread: string
  max_trades: string
  max_daily_drawdown_percent: string
}

export interface TestResult {
  success: boolean
  message: string
}

export interface ServerStatus {
  is_running: boolean
  url: string
}

export interface ServerStats {
  total_requests: number
  last_request_time: string | null
  active_connections: number
  uptime: string
  llm_provider: string
  llm_model: string
}

export interface HealthInfo {
  status: string
  timestamp?: string
  llm_provider?: string
  model?: string
  active_connections?: number
  code?: number
  message?: string
}

export interface SignalRecord {
  action: 'BUY' | 'SELL' | 'WAIT'
  symbol: string
  confidence: number
  reasoning: string
  timestamp: string
}

export interface SignalsResponse {
  records: SignalRecord[]
  since: number
}

export interface StrategySummary {
  id: string
  name: string
  category: string
}

export const TEMPLATE_SLOTS = ['bullish_ideal', 'bearish_ideal', 'fail_trap'] as const
export type TemplateSlot = (typeof TEMPLATE_SLOTS)[number]

export interface TemplateRecord {
  slot: string
  filename: string
  caption: string
  updated_at: string
  image: string | null
}

export interface TemplateSourceImage {
  slot: string
  position: number
  filename: string
  crop_x: number
  crop_y: number
  crop_w: number
  crop_h: number
  source_width: number
  source_height: number
  updated_at: string
  image: string | null
}

export interface PromptVersion {
  strategy_name: string
  version: number
  text: string
  created_at: string
  notes: string
}

export interface JobOutput {
  lines: string[]
  since: number
  done: boolean
  returncode: number | null
  progress: { current: number; total: number } | null
  error?: string
}

export interface BacktestReport {
  raw: Record<string, number>
  ai_filtered: Record<string, number>
  events_total: number
  events_skipped: number
}

export interface LogTailResponse {
  lines: string[]
  new_offset: number
}

export interface LogStats {
  total_entries: number
  level_counts: Record<string, number>
  file_size_bytes?: number
  last_modified?: string
}
