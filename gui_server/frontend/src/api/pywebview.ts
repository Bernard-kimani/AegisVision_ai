import type {
  BacktestReport,
  FlatConfig,
  HealthInfo,
  JobOutput,
  LatestChart,
  LivePositions,
  LogStats,
  LogTailResponse,
  PromptVersion,
  ServerStats,
  ServerStatus,
  SignalsResponse,
  StrategySummary,
  TemplateRecord,
  TemplateSourceImage,
  TestResult,
  TradeTelemetry,
} from './types'

// Method signatures mirror gui_server/webview_api.py::WebViewApi 1:1.
export interface PywebviewApi {
  get_config(): Promise<FlatConfig>
  save_config(flatConfig: FlatConfig): Promise<boolean>
  reset_config(): Promise<FlatConfig>
  get_theme(): Promise<string>
  set_theme(mode: string): Promise<boolean>
  export_config(flatConfig: FlatConfig): Promise<string | null>
  import_config(): Promise<FlatConfig | null>
  test_connection(host: string, port: string): Promise<TestResult>
  test_api_key(provider: string, apiKey: string): Promise<TestResult>

  start_server(): Promise<boolean>
  stop_server(): Promise<boolean>
  restart_server(): Promise<boolean>
  get_server_status(): Promise<ServerStatus>
  get_server_stats(): Promise<ServerStats>
  health_check(): Promise<HealthInfo | null>

  get_recent_signals(since?: number): Promise<SignalsResponse>
  get_trade_telemetry(): Promise<TradeTelemetry>
  get_live_positions(): Promise<LivePositions>
  get_latest_chart(): Promise<LatestChart | null>
  save_data_uri(dataUri: string, suggestedName: string): Promise<string | null>

  list_strategies(): Promise<StrategySummary[]>
  create_strategy(name: string, category?: string): Promise<StrategySummary | { error: string }>
  get_active_strategy(): Promise<StrategySummary | null>
  set_active_strategy(strategyId: string): Promise<boolean>
  get_strategy_templates(strategyId: string): Promise<Record<string, TemplateRecord | null>>
  get_template_sources(strategyId: string, slot: string): Promise<TemplateSourceImage[]>
  save_template_source(
    strategyId: string, slot: string, position: number, imageBase64: string,
    cropX: number, cropY: number, cropW: number, cropH: number, caption?: string | null,
  ): Promise<TemplateRecord>
  remove_template_source(strategyId: string, slot: string, position: number): Promise<TemplateRecord | null>
  update_template_caption(strategyId: string, slot: string, caption: string): Promise<TemplateRecord | null>
  get_cell_aspect_ratio(count: number, index: number): Promise<number>
  get_prompt(strategyId: string): Promise<PromptVersion | null>
  list_prompt_versions(strategyId: string): Promise<PromptVersion[]>
  save_prompt(strategyId: string, text: string, notes?: string): Promise<PromptVersion>

  start_extract(startDate: string, endDate: string, maxEvents: string): Promise<string>
  start_replay(throttleSeconds: string, minConfidence: string, minRiskReward: string): Promise<{ job_id?: string; error?: string }>
  get_job_output(jobId: string, since?: number): Promise<JobOutput>
  get_backtest_report(): Promise<BacktestReport | null>

  tail_log(offset?: number): Promise<LogTailResponse>
  get_log_stats(): Promise<LogStats>
  clear_log(): Promise<number>
  export_log(): Promise<string | null>
  open_log_file(): Promise<boolean>
}

declare global {
  interface Window {
    pywebview?: { api: PywebviewApi }
  }
}

let readyPromise: Promise<void> | null = null

/** Resolves once window.pywebview.api exists -- pywebview injects it
 * asynchronously and fires a 'pywebviewready' event on window, which may
 * fire before or after this module's code runs. */
function waitForPywebviewReady(): Promise<void> {
  if (window.pywebview?.api) return Promise.resolve()
  if (!readyPromise) {
    readyPromise = new Promise((resolve) => {
      window.addEventListener('pywebviewready', () => resolve(), { once: true })
    })
  }
  return readyPromise
}

export async function getRealApi(): Promise<PywebviewApi | null> {
  if (typeof window === 'undefined') return null
  if (window.pywebview?.api) return window.pywebview.api
  // Give the native bridge a short window to announce itself; if it never
  // does (plain browser tab, not an actual pywebview window), fall back.
  await Promise.race([waitForPywebviewReady(), new Promise((r) => setTimeout(r, 300))])
  return window.pywebview?.api ?? null
}
