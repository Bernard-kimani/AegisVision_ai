import { useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getApi } from '../../api/client'
import type { FlatConfig } from '../../api/types'
import { Button, Section, Select, SignalChip, StatTile, StatusDot, TextField } from '../../components/primitives'
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

  return (
    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
      <div className="lg:col-span-3 flex flex-col">
        <Section title="Server Settings">
          <div className="flex flex-wrap items-end gap-3">
            <TextField label="Host" mono value={form.host} onChange={(e) => set('host', e.target.value)} className="w-40" />
            <TextField label="Port" mono value={form.port} onChange={(e) => set('port', e.target.value)} className="w-24" />
            <Button onClick={() => testConnMutation.mutate()} disabled={testConnMutation.isPending}>Test Connection</Button>
          </div>
          {connMsg && <p className="text-xs text-text-secondary mt-2">{connMsg}</p>}
        </Section>

        <Section title="AI Configuration">
          <div className="flex flex-wrap items-end gap-3">
            <Select
              label="Provider" value={form.llm_provider} className="w-40"
              onChange={(e) => { set('llm_provider', e.target.value); set('model', MODELS_BY_PROVIDER[e.target.value]?.[0] ?? '') }}
            >
              {Object.keys(MODELS_BY_PROVIDER).map((p) => <option key={p} value={p}>{p}</option>)}
            </Select>
            <Select label="Model" value={form.model} className="w-56" onChange={(e) => set('model', e.target.value)}>
              {models.map((m) => <option key={m} value={m}>{m}</option>)}
            </Select>
          </div>
          <div className="flex flex-wrap items-end gap-3 mt-3">
            <TextField label="API Key" mono type="password" value={form.api_key} onChange={(e) => set('api_key', e.target.value)} className="w-72" placeholder="Enter your API key..." />
            <Button onClick={() => testApiMutation.mutate()} disabled={testApiMutation.isPending}>Test API</Button>
          </div>
          {apiMsg && <p className="text-xs text-text-secondary mt-2">{apiMsg}</p>}
          <div className="flex flex-wrap items-end gap-3 mt-3">
            <TextField label="Temperature" mono value={form.temperature} onChange={(e) => set('temperature', e.target.value)} className="w-20" />
            <TextField label="Max Tokens" mono value={form.max_tokens} onChange={(e) => set('max_tokens', e.target.value)} className="w-24" />
          </div>
        </Section>

        <Section title="Trading Parameters">
          <div className="flex flex-wrap items-end gap-3">
            <TextField label="Min Confidence (%)" mono value={form.min_confidence} onChange={(e) => set('min_confidence', e.target.value)} className="w-20" />
            <TextField label="Min Risk:Reward" mono value={form.min_risk_reward} onChange={(e) => set('min_risk_reward', e.target.value)} className="w-20" />
            <TextField label="Max Spread (pips)" mono value={form.max_spread} onChange={(e) => set('max_spread', e.target.value)} className="w-20" />
            <TextField label="Max Trades" mono value={form.max_trades} onChange={(e) => set('max_trades', e.target.value)} className="w-20" />
          </div>
        </Section>

        <Section title="Configuration Management">
          <div className="flex flex-wrap gap-2">
            <Button variant="primary" onClick={() => saveMutation.mutate()} disabled={saveMutation.isPending}>Save Configuration</Button>
            <Button onClick={() => importMutation.mutate()} disabled={importMutation.isPending}>Load Configuration</Button>
            <Button onClick={() => resetMutation.mutate()} disabled={resetMutation.isPending}>Reset to Defaults</Button>
            <Button onClick={() => exportMutation.mutate()} disabled={exportMutation.isPending}>Export Config File</Button>
          </div>
          {dirty && <p className="text-xs text-warning mt-2">Unsaved changes</p>}
        </Section>
      </div>

      <div className="lg:col-span-2 flex flex-col">
        <Section title="Server Status">
          <p className="flex items-center gap-2.5 text-sm">
            <StatusDot live={running} color={running ? 'success' : 'error'} />
            <span className={`font-mono font-medium tracking-wide ${running ? 'text-success' : 'text-error'}`}>
              {running ? 'RUNNING' : 'STOPPED'}
            </span>
            <span className="text-text-secondary">{running ? `— accepting requests on ${status?.url}` : '— not running'}</span>
          </p>
        </Section>

        <Section title="Server Control">
          <div className="grid grid-cols-2 gap-2">
            <Button variant="success" pill disabled={running || startMutation.isPending} onClick={() => startMutation.mutate()}>Start Server</Button>
            <Button variant="danger" pill disabled={!running || stopMutation.isPending} onClick={() => stopMutation.mutate()}>Stop Server</Button>
            <Button variant="warning" pill disabled={!running || restartMutation.isPending} onClick={() => restartMutation.mutate()}>Restart</Button>
            <Button pill onClick={() => healthMutation.mutate()} disabled={healthMutation.isPending}>Health Check</Button>
          </div>
        </Section>

        <Section title="Server Statistics">
          <div className="grid grid-cols-2 gap-2">
            <StatTile label="Active Connections" value={String(stats?.active_connections ?? 0)} />
            <StatTile label="Server Uptime" value={stats?.uptime ?? 'Not running'} />
            <StatTile label="Total Requests Today" value={String(stats?.total_requests ?? 0)} />
            <StatTile label="Last Request" value={stats?.last_request_time ?? 'None'} />
          </div>
        </Section>
      </div>

      <div className="lg:col-span-5">
        <Section title="Recent Trading Signals">
          <div className="flex gap-3 overflow-x-auto pb-2">
            {!signalsResp?.records.length && (
              <p className="text-xs text-text-secondary py-4">No trading signals yet. Start the server to begin receiving signals.</p>
            )}
            {signalsResp?.records.map((r, i) => <SignalChip key={i} {...r} />)}
          </div>
        </Section>
      </div>
    </div>
  )
}
