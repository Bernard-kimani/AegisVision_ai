import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { getApi } from '../../api/client'
import type { BacktestReport } from '../../api/types'
import { Button, Section, Select, Slider, StatusDot, TextField } from '../../components/primitives'

const INTERVAL_OPTIONS = [
  { value: '1', label: '1m' },
  { value: '5', label: '5m' },
  { value: '15', label: '15m' },
  { value: '30', label: '30m' },
  { value: '60', label: '60m · 1h' },
  { value: '240', label: '240m · 4h' },
]

function StepBadge({ n }: { n: number }) {
  return (
    <span className="flex h-5 w-5 shrink-0 items-center justify-center border border-accent/30 bg-accent/10 font-mono text-[10px] font-semibold text-accent">
      {String(n).padStart(2, '0')}
    </span>
  )
}

// Matches replay_harness.py's per-event print: "[i/n] <ts> verdict=ACCEPT conf=91 guardrail=BUY"
const REPLAY_LINE_RE = /^\[(\d+)\/(\d+)\] (\S+) verdict=(ACCEPT|REJECT) conf=(\d+) guardrail=(BUY|SELL|WAIT)$/

function ReplayLine({ line }: { line: string }) {
  const m = line.match(REPLAY_LINE_RE)
  if (!m) return <div className="text-text-secondary">{line}</div>
  const [, idx, total, ts, verdict, conf, action] = m
  const actionColor = action === 'BUY' ? 'text-success' : action === 'SELL' ? 'text-error' : 'text-text-disabled'
  const verdictColor = verdict === 'ACCEPT' ? 'text-success' : 'text-warning'
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
      <span className="text-accent/70">[{idx}/{total}]</span>
      <span className="text-text-disabled">{ts}</span>
      <span className={verdictColor}>verdict={verdict}</span>
      <span className="text-text-secondary">conf={conf}%</span>
      <span className={`font-semibold ${actionColor}`}>guardrail={action}</span>
    </div>
  )
}

function useJobPolling(onLine: (line: string) => void) {
  const [jobId, setJobId] = useState<string | null>(null)
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState<{ current: number; total: number } | null>(null)
  const [returncode, setReturncode] = useState<number | null>(null)
  const sinceRef = useRef(0)

  useEffect(() => {
    if (!jobId) return
    let cancelled = false
    sinceRef.current = 0
    setRunning(true)
    setReturncode(null)
    const poll = async () => {
      const api = await getApi()
      const out = await api.get_job_output(jobId, sinceRef.current)
      if (cancelled) return
      sinceRef.current = out.since
      out.lines.forEach(onLine)
      if (out.progress) setProgress(out.progress)
      if (out.done) {
        setRunning(false)
        setReturncode(out.returncode)
        return
      }
      timer = setTimeout(poll, 500)
    }
    let timer = setTimeout(poll, 200)
    return () => { cancelled = true; clearTimeout(timer) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId])

  return { start: setJobId, running, progress, returncode }
}

export default function BacktestPage({ onStatusMessage }: { onStatusMessage: (msg: string) => void }) {
  const [log, setLog] = useState<string[]>([])
  const logRef = useRef<HTMLDivElement>(null)
  const appendLine = (line: string) => setLog((l) => [...l, line])

  const [startDate, setStartDate] = useState('2018-01-05')
  const [endDate, setEndDate] = useState('2018-01-15')
  const [interval, setIntervalMin] = useState('60')
  const [maxEvents, setMaxEvents] = useState('50')

  const [throttle, setThrottle] = useState('12')
  const [minConfidence, setMinConfidence] = useState('60')
  const [minRR, setMinRR] = useState('1.2')

  const extractJob = useJobPolling(appendLine)
  const replayJob = useJobPolling(appendLine)

  const [report, setReport] = useState<BacktestReport | null>(null)

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight
  }, [log.length])

  useEffect(() => {
    if (replayJob.returncode === 0) {
      getApi().then((api) => api.get_backtest_report()).then((r) => { setReport(r); onStatusMessage('Backtest complete') })
    } else if (replayJob.returncode !== null) {
      onStatusMessage('Backtest failed')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [replayJob.returncode])

  const extractMutation = useMutation({
    mutationFn: async () => (await getApi()).start_extract(startDate, endDate, interval, maxEvents),
    onSuccess: (jobId) => { appendLine('Starting trigger extraction...'); extractJob.start(jobId) },
  })

  const replayMutation = useMutation({
    mutationFn: async () => (await getApi()).start_replay(throttle, minConfidence, minRR),
    onSuccess: (r) => {
      if ('error' in r && r.error) { onStatusMessage(r.error); return }
      appendLine('Starting backtest replay...')
      if (r.job_id) replayJob.start(r.job_id)
    },
  })

  const engineState = replayJob.running ? 'REPLAYING' : extractJob.running ? 'EXTRACTING' : 'IDLE'
  const engineBusy = engineState !== 'IDLE'

  return (
    <div className="flex flex-col gap-6 h-full">
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6 items-start">
        <div className="xl:col-span-3">
          <Section title={<><StepBadge n={1} /> Extract Historical Triggers</>}>
            <div className="flex flex-col gap-3">
              <TextField label="Start Date" mono value={startDate} onChange={(e) => setStartDate(e.target.value)} placeholder="YYYY-MM-DD" />
              <TextField label="End Date" mono value={endDate} onChange={(e) => setEndDate(e.target.value)} placeholder="YYYY-MM-DD" />
              <Select label="Resolution Interval" value={interval} onChange={(e) => setIntervalMin(e.target.value)}>
                {INTERVAL_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </Select>
              <TextField label="Max Event Limit" mono value={maxEvents} onChange={(e) => setMaxEvents(e.target.value)} />
              <Button className="mt-1 self-start" onClick={() => extractMutation.mutate()} disabled={extractJob.running}>
                {extractJob.running ? 'Extracting…' : 'Extract Events'}
              </Button>
            </div>
          </Section>
        </div>

        <div className="xl:col-span-3">
          <Section title={<><StepBadge n={2} /> Run Replay (real, throttled AI calls)</>}>
            <div className="flex flex-col gap-4">
              <Slider label="Execution Throttle" value={Number(throttle)} display={`${throttle}s/call`}
                min={1} max={30} step={1} onChange={(v) => setThrottle(String(v))} />
              <Slider label="AI Confidence Threshold" value={Number(minConfidence)} display={`${minConfidence}%`}
                min={0} max={100} step={1} onChange={(v) => setMinConfidence(String(v))} />
              <Slider label="Min Risk:Reward" value={Number(minRR)} display={`${Number(minRR).toFixed(1)}×`}
                min={1} max={3} step={0.1} onChange={(v) => setMinRR(v.toFixed(1))} />
              <Button variant="success" className="mt-1 self-start" onClick={() => replayMutation.mutate()} disabled={replayJob.running}>
                {replayJob.running ? 'Running…' : 'Run Backtest'}
              </Button>
              {replayJob.progress && (
                <div className="mt-1">
                  <div className="flex items-baseline justify-between text-[11px] font-mono tabular-nums text-text-secondary mb-1">
                    <span>Processing event matrix…</span>
                    <span>{Math.round((replayJob.progress.current / replayJob.progress.total) * 100)}%</span>
                  </div>
                  <div className="h-1 rounded-full bg-surface-alt w-full">
                    <div className="h-1 rounded-full bg-accent transition-all duration-300" style={{ width: `${(replayJob.progress.current / replayJob.progress.total) * 100}%` }} />
                  </div>
                </div>
              )}
            </div>
          </Section>
        </div>

        <div className="xl:col-span-6 flex flex-col min-h-0">
          <Section
            title="Replay Log"
            action={
              <span className="flex items-center gap-2 normal-case tracking-normal">
                <StatusDot live={engineBusy} color={engineBusy ? 'success' : 'neutral'} />
                <span className={`font-mono text-[11px] font-medium ${engineBusy ? 'text-success' : 'text-text-disabled'}`}>{engineState}</span>
              </span>
            }
            className="flex-1 flex flex-col min-h-0"
          >
            <div ref={logRef} className="flex-1 overflow-auto bg-surface border border-border font-mono tabular-nums text-[11px] leading-relaxed p-3.5 h-105">
              {log.length === 0
                ? <span className="text-text-disabled">Extraction and replay output streams here.</span>
                : log.map((l, i) => <ReplayLine key={i} line={l} />)}
            </div>
          </Section>
        </div>
      </div>

      <Section title={<><StepBadge n={3} /> Results — Raw vs. AI-Filtered</>}>
          {!report ? (
            <p className="text-sm text-text-secondary">Run a backtest to compare raw triggers against the AI-filtered result.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="text-sm w-full max-w-2xl">
                <thead>
                  <tr className="text-left border-b border-border">
                    <th className="pr-6 pb-2 text-[11px] font-semibold tracking-widest uppercase text-text-secondary">Metric</th>
                    <th className="pr-6 pb-2 text-[11px] font-semibold tracking-widest uppercase text-text-secondary">Raw</th>
                    <th className="pb-2 text-[11px] font-semibold tracking-widest uppercase text-accent">AI-Filtered</th>
                  </tr>
                </thead>
                <tbody>
                  {[
                    ['Total Trades', report.raw.total_trades ?? 0, report.ai_filtered.total_trades ?? 0],
                    ['Win Rate', `${((report.raw.win_rate ?? 0) * 100).toFixed(1)}%`, `${((report.ai_filtered.win_rate ?? 0) * 100).toFixed(1)}%`],
                    ['Profit Factor', (report.raw.profit_factor ?? 0).toFixed(2), (report.ai_filtered.profit_factor ?? 0).toFixed(2)],
                    ['Total P&L', (report.raw.total_pnl ?? 0).toFixed(2), (report.ai_filtered.total_pnl ?? 0).toFixed(2)],
                    ['Max Drawdown', (report.raw.max_drawdown ?? 0).toFixed(2), (report.ai_filtered.max_drawdown ?? 0).toFixed(2)],
                    ['Expectancy/Trade', (report.raw.expectancy ?? 0).toFixed(3), (report.ai_filtered.expectancy ?? 0).toFixed(3)],
                  ].map(([label, raw, ai]) => (
                    <tr key={String(label)} className="border-b border-border/50">
                      <td className="pr-6 py-1.5 text-text-secondary">{label}</td>
                      <td className="pr-6 py-1.5 font-mono tabular-nums">{raw}</td>
                      <td className="py-1.5 font-mono tabular-nums font-medium">{ai}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-[11px] font-mono tabular-nums text-text-secondary mt-3">
                {report.events_skipped}/{report.events_total} events skipped — insufficient warm-up data
              </p>
            </div>
          )}
      </Section>
    </div>
  )
}
