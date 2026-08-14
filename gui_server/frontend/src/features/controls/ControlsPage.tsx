import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getApi } from '../../api/client'
import type { FlatConfig } from '../../api/types'
import { Button, PositionRow, Section, Select, SignalRow, StatusDot, TextField } from '../../components/primitives'
import { MODELS_BY_PROVIDER } from './models'

const DEFAULTS: FlatConfig = {
  host: 'localhost', port: '8080', llm_provider: 'gemini', model: 'gemini-2.5-flash',
  api_key: '', temperature: '0.3', max_tokens: '4000', min_confidence: '70',
  min_risk_reward: '1.5', max_spread: '2.0', max_trades: '3', max_daily_drawdown_percent: '5.0',
}

export default function ControlsPage({ onStatusMessage }: { onStatusMessage: (msg: string) => void }) {
  const qc = useQueryClient()
  const [form, setForm] = useState<FlatConfig>(DEFAULTS)
  const [dirty, setDirty] = useState(false)
  const [connMsg, setConnMsg] = useState<string | null>(null)
  const [apiMsg, setApiMsg] = useState<string | null>(null)

  const { data: config } = useQuery({ queryKey: ['config'], queryFn: async () => (await getApi()).get_config() })
  const { data: status } = useQuery({
    queryKey: ['server-status'], queryFn: async () => (await getApi()).get_server_status(), refetchInterval: 3000,
  })
  const { data: stats } = useQuery({
    queryKey: ['server-stats'], queryFn: async () => (await getApi()).get_server_stats(),
    refetchInterval: status?.is_running ? 2000 : false,
  })
  const { data: signalsResp } = useQuery({
    queryKey: ['signals'], queryFn: async () => (await getApi()).get_recent_signals(0), refetchInterval: 2000,
  })
  const { data: telemetry } = useQuery({
    queryKey: ['trade-telemetry'], queryFn: async () => (await getApi()).get_trade_telemetry(), refetchInterval: 5000,
  })
  const { data: livePositions } = useQuery({
    queryKey: ['live-positions'], queryFn: async () => (await getApi()).get_live_positions(), refetchInterval: 3000,
  })

  useEffect(() => {
    if (config && !dirty) setForm(config)
  }, [config, dirty])

  const set = (key: keyof FlatConfig, value: string) => { setForm((f) => ({ ...f, [key]: value })); setDirty(true) }

  const saveMutation = useMutation({
    mutationFn: async () => (await getApi()).save_config(form),
    onSuccess: () => { setDirty(false); onStatusMessage('Configuration saved'); qc.invalidateQueries({ queryKey: ['config'] }) },
  })
  const resetMutation = useMutation({
    mutationFn: async () => (await getApi()).reset_config(),
    onSuccess: (cfg) => { setForm(cfg); setDirty(false); onStatusMessage('Configuration reset to defaults') },
  })
  const exportMutation = useMutation({
    mutationFn: async () => (await getApi()).export_config(form),
    onSuccess: (path) => { if (path) onStatusMessage(`Configuration exported to ${path}`) },
  })
  const importMutation = useMutation({
    mutationFn: async () => (await getApi()).import_config(),
    onSuccess: (cfg) => { if (cfg) { setForm(cfg); setDirty(true); onStatusMessage('Configuration imported — review and Save') } },
  })

  const testConnMutation = useMutation({
    mutationFn: async () => (await getApi()).test_connection(form.host, form.port),
    onSuccess: (r) => setConnMsg(r.message),
  })
  const testApiMutation = useMutation({
    mutationFn: async () => (await getApi()).test_api_key(form.llm_provider, form.api_key),
    onSuccess: (r) => setApiMsg(r.message),
  })

  const startMutation = useMutation({
    mutationFn: async () => (await getApi()).start_server(),
    onSuccess: (ok) => { onStatusMessage(ok ? 'Server started successfully' : 'Failed to start server'); qc.invalidateQueries({ queryKey: ['server-status'] }) },
  })
  const stopMutation = useMutation({
    mutationFn: async () => (await getApi()).stop_server(),
    onSuccess: () => { onStatusMessage('Server stopped'); qc.invalidateQueries({ queryKey: ['server-status'] }) },
  })
  const restartMutation = useMutation({
    mutationFn: async () => (await getApi()).restart_server(),
    onSuccess: () => { onStatusMessage('Server restarted successfully'); qc.invalidateQueries({ queryKey: ['server-status'] }) },
  })
  const healthMutation = useMutation({
    mutationFn: async () => (await getApi()).health_check(),
    onSuccess: (h) => onStatusMessage(h ? `Health check: ${h.status}` : 'Server is not responding'),
  })

  const running = status?.is_running ?? false
  const models = MODELS_BY_PROVIDER[form.llm_provider] ?? []

  const lastDecisionLabel = telemetry?.last_decision_time
    ? new Date(telemetry.last_decision_time).toLocaleTimeString()
    : 'None yet'

  // Heartbeats land every ~10s (see the EA's HeartbeatIntervalSeconds) -
  // three missed cycles is a reasonable "actually disconnected" threshold,
  // rather than flickering on every single delayed tick.
  const eaConnected = (livePositions?.seconds_since ?? Infinity) < 30
  const heartbeatLabel = livePositions?.seconds_since == null
    ? null
    : livePositions.seconds_since < 60
      ? `${Math.round(livePositions.seconds_since)}s ago`
      : `${Math.round(livePositions.seconds_since / 60)}m ago`

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_1fr_0.85fr] gap-6 items-start">
        <div className="flex flex-col">
          <Section title="AI Configuration">
            <div className="flex flex-col gap-3">
              <Select
                label="Provider" value={form.llm_provider}
                onChange={(e) => { set('llm_provider', e.target.value); set('model', MODELS_BY_PROVIDER[e.target.value]?.[0] ?? '') }}
              >
                {Object.keys(MODELS_BY_PROVIDER).map((p) => <option key={p} value={p}>{p}</option>)}
              </Select>
              <Select label="Model" value={form.model} onChange={(e) => set('model', e.target.value)}>
                {models.map((m) => <option key={m} value={m}>{m}</option>)}
              </Select>
              <TextField
                label="API Key" mono type="password" autoComplete="off" value={form.api_key}
                onChange={(e) => set('api_key', e.target.value)} placeholder="Enter your API key..."
              />
              <Button onClick={() => testApiMutation.mutate()} disabled={testApiMutation.isPending} className="self-start">Test API</Button>
              {apiMsg && <p className="text-xs text-text-secondary">{apiMsg}</p>}
              <TextField label="Temperature" mono value={form.temperature} onChange={(e) => set('temperature', e.target.value)} className="w-28" />
            </div>
          </Section>
        </div>

        {/* Telemetry — one continuous section (label/value pairs directly on
            the page background) rather than a grid of bordered StatTiles,
            so it reads as a single instrument panel instead of a pile of cards. */}
        <div className="flex flex-col lg:border-l lg:border-divider/15 lg:pl-6">
          <Section title="Telemetry">
            <div className="grid grid-cols-2 gap-x-6 gap-y-4">
              <div>
                <div className="text-[10px] tracking-widest uppercase text-text-secondary">Active Conns</div>
                <div className="text-base font-mono tabular-nums font-medium mt-1">{stats?.active_connections ?? 0}</div>
              </div>
              <div>
                <div className="text-[10px] tracking-widest uppercase text-text-secondary">Uptime</div>
                <div className="text-base font-mono tabular-nums font-medium mt-1">{stats?.uptime ?? 'Not running'}</div>
              </div>

              <div className="col-span-2">
                <div className="text-[10px] tracking-widest uppercase text-text-secondary">Total Requests</div>
                <div className="text-3xl font-mono tabular-nums font-semibold text-accent mt-1">{stats?.total_requests ?? 0}</div>
              </div>

              <div className="col-span-2 h-px bg-divider/15" />

              <div>
                <div className="text-[10px] tracking-widest uppercase text-text-secondary">Approved Trades</div>
                <div className="text-base font-mono tabular-nums font-medium text-success mt-1">{telemetry?.approved ?? 0}</div>
              </div>
              <div>
                <div className="text-[10px] tracking-widest uppercase text-text-secondary">Filtered / Rejected</div>
                <div className="text-base font-mono tabular-nums font-medium text-warning mt-1">{telemetry?.rejected ?? 0}</div>
              </div>
              <div className="col-span-2">
                <div className="text-[10px] tracking-widest uppercase text-text-secondary">Last Decision</div>
                <div className="text-base font-mono tabular-nums font-medium mt-1">{lastDecisionLabel}</div>
              </div>
            </div>
          </Section>
        </div>

        {/* Server Engine, back on the right where it started. */}
        <div className="flex flex-col lg:border-l lg:border-divider/15 lg:pl-6">
          <Section title="Server Engine">
            <p className="flex items-center gap-2.5 text-sm mb-1">
              <StatusDot live={running} color={running ? 'success' : 'error'} />
              <span className={`font-mono font-medium tracking-wide ${running ? 'text-success' : 'text-error'}`}>
                {running ? 'RUNNING' : 'STOPPED'}
              </span>
            </p>
            <p className="text-[11px] font-mono text-text-disabled mb-3 h-4">{running ? status?.url : ''}</p>
            <div className="flex flex-col gap-3">
              <TextField label="Host" mono value={form.host} onChange={(e) => set('host', e.target.value)} />
              <TextField label="Port" mono value={form.port} onChange={(e) => set('port', e.target.value)} />
              <Button onClick={() => testConnMutation.mutate()} disabled={testConnMutation.isPending} className="self-start">Test Connection</Button>
              {connMsg && <p className="text-xs text-text-secondary">{connMsg}</p>}
            </div>
            <div className="grid grid-cols-2 gap-2 mt-4">
              <Button variant="success" disabled={running || startMutation.isPending} onClick={() => startMutation.mutate()}>Start</Button>
              <Button variant="danger" disabled={!running || stopMutation.isPending} onClick={() => stopMutation.mutate()}>Stop</Button>
              <Button variant="warning" disabled={!running || restartMutation.isPending} onClick={() => restartMutation.mutate()}>Restart</Button>
              <Button onClick={() => healthMutation.mutate()} disabled={healthMutation.isPending}>Health Check</Button>
            </div>
          </Section>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {dirty && <span className="text-xs text-warning mr-auto">Unsaved changes</span>}
        <Button onClick={() => resetMutation.mutate()} disabled={resetMutation.isPending}>Reset Defaults</Button>
        <Button onClick={() => importMutation.mutate()} disabled={importMutation.isPending}>Load Configuration</Button>
        <Button onClick={() => exportMutation.mutate()} disabled={exportMutation.isPending}>Export Config File</Button>
        <Button variant="primary" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>Save Changes</Button>
      </div>

      <Section title="Live Trading Activity">
        <p className="flex items-center gap-2.5 text-xs mb-5">
          <StatusDot live={eaConnected} color={eaConnected ? 'success' : 'neutral'} />
          <span className={eaConnected ? 'text-success font-medium' : 'text-text-disabled font-medium'}>
            {eaConnected ? `EA Connected · ${livePositions?.symbol}` : 'EA not connected'}
          </span>
          {heartbeatLabel && <span className="text-text-secondary">· heartbeat {heartbeatLabel}</span>}
        </p>

        {!!livePositions?.open_trades.length && (
          <div className="mb-5">
            <div className="text-[10px] tracking-widest uppercase text-text-secondary mb-1">Open Positions</div>
            <div className="flex flex-col divide-y divide-divider/10">
              {livePositions.open_trades.map((t) => (
                <PositionRow key={t.ticket} symbol={livePositions.symbol} {...t} />
              ))}
            </div>
          </div>
        )}

        <div>
          <div className="text-[10px] tracking-widest uppercase text-text-secondary mb-1">Decision History</div>
          {!signalsResp?.records.length && (
            <p className="text-xs text-text-secondary py-4">No trading signals yet. Start the server to begin receiving signals.</p>
          )}
          <div className="flex flex-col divide-y divide-divider/10 max-h-105 overflow-y-auto">
            {signalsResp?.records.map((r, i) => <SignalRow key={i} {...r} />)}
          </div>
        </div>
      </Section>
    </div>
  )
}
