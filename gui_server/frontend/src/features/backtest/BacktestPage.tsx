import { useEffect, useRef, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { getApi } from '../../api/client'
import type { BacktestReport } from '../../api/types'
import { Button, Section, TextField } from '../../components/primitives'

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

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-full">
      <div className="flex flex-col">
        <Section title="1 · Extract Historical Triggers">
          <div className="flex flex-col gap-3 max-w-xs">
            <TextField label="Start Date" mono value={startDate} onChange={(e) => setStartDate(e.target.value)} placeholder="YYYY-MM-DD" />
            <TextField label="End Date" mono value={endDate} onChange={(e) => setEndDate(e.target.value)} placeholder="YYYY-MM-DD" />
            <TextField label="Interval (min)" mono value={interval} onChange={(e) => setIntervalMin(e.target.value)} />
            <TextField label="Max Events" mono value={maxEvents} onChange={(e) => setMaxEvents(e.target.value)} />
            <Button className="mt-1 self-start" onClick={() => extractMutation.mutate()} disabled={extractJob.running}>
              {extractJob.running ? 'Extracting…' : 'Extract Events'}
            </Button>
          </div>
        </Section>

        <Section title="2 · Run Replay (real, throttled AI calls)">
          <div className="flex flex-col gap-3 max-w-xs">
            <TextField label="Throttle (sec/call)" mono value={throttle} onChange={(e) => setThrottle(e.target.value)} />
            <TextField label="Min Confidence" mono value={minConfidence} onChange={(e) => setMinConfidence(e.target.value)} />
            <TextField label="Min Risk:Reward" mono value={minRR} onChange={(e) => setMinRR(e.target.value)} />
            <Button variant="success" className="mt-1 self-start" onClick={() => replayMutation.mutate()} disabled={replayJob.running}>
              {replayJob.running ? 'Running…' : 'Run Backtest'}
            </Button>
            {replayJob.progress && (
              <div className="mt-1">
                <div className="h-1 bg-surface-alt w-56">
                  <div className="h-1 bg-accent transition-all duration-300" style={{ width: `${(replayJob.progress.current / replayJob.progress.total) * 100}%` }} />
                </div>
                <p className="text-[11px] font-mono tabular-nums text-text-secondary mt-1.5">{replayJob.progress.current}/{replayJob.progress.total} events</p>
              </div>
            )}
          </div>
        </Section>
      </div>

      <div className="lg:col-span-2 flex flex-col min-h-0">
        <Section title="Replay Log" className="flex-1 flex flex-col min-h-0">
          <div ref={logRef} className="flex-1 overflow-auto bg-surface border border-border font-mono tabular-nums text-[11px] leading-relaxed p-3.5 min-h-64">
            {log.length === 0
              ? <span className="text-text-disabled">Extraction and replay output streams here.</span>
              : log.map((l, i) => <div key={i}>{l}</div>)}
          </div>
        </Section>
      </div>

      <div className="lg:col-span-3">
        <Section title="3 · Results — Raw vs. AI-Filtered">
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
    </div>
  )
}
