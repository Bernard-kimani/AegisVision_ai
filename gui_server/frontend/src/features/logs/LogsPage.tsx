import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { getApi } from '../../api/client'
import { Button, Divider, Select, TextField } from '../../components/primitives'

const LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] as const
const LEVEL_ORDER: Record<string, number> = { DEBUG: 0, INFO: 1, WARNING: 2, ERROR: 3, CRITICAL: 4 }

// Mirrors main.py's logging format: '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
const LOG_LINE_RE = /^(\S+ \S+) - (.+?) - (DEBUG|INFO|WARNING|ERROR|CRITICAL) - ([\s\S]*)$/

type ParsedLine = { time: string; module: string; level: (typeof LEVELS)[number]; message: string }

function parseLine(line: string): ParsedLine | null {
  const m = line.match(LOG_LINE_RE)
  if (!m) return null
  const [, timestamp, module, level, message] = m
  const time = timestamp.split(' ')[1]?.split(',')[0] ?? timestamp
  return { time, module, level: level as ParsedLine['level'], message }
}

function lineLevel(line: string): string | null {
  return parseLine(line)?.level ?? null
}

const LEVEL_STYLE: Record<(typeof LEVELS)[number], { text: string; row: string }> = {
  DEBUG: { text: 'text-text-disabled', row: '' },
  INFO: { text: 'text-text-secondary', row: '' },
  WARNING: { text: 'text-warning', row: 'border-l-2 border-warning bg-warning/[0.06]' },
  ERROR: { text: 'text-error', row: 'border-l-2 border-error bg-error/[0.06]' },
  CRITICAL: { text: 'text-error', row: 'border-l-2 border-error bg-error/10' },
}

export default function LogsPage({ onStatusMessage }: { onStatusMessage: (msg: string) => void }) {
  const [buffer, setBuffer] = useState<string[]>([])
  const [level, setLevel] = useState<(typeof LEVELS)[number]>('INFO')
  const [search, setSearch] = useState('')
  const [autoScroll, setAutoScroll] = useState(true)
  const offsetRef = useRef(0)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    const poll = async () => {
      const api = await getApi()
      const { lines, new_offset } = await api.tail_log(offsetRef.current)
      if (cancelled) return
      if (lines.length) {
        offsetRef.current = new_offset
        setBuffer((b) => [...b, ...lines].slice(-1000))
      }
    }
    poll()
    const id = setInterval(poll, 1000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const filtered = buffer.filter((line) => {
    const lvl = lineLevel(line)
    if (lvl && LEVEL_ORDER[lvl] < LEVEL_ORDER[level]) return false
    if (search && !line.toLowerCase().includes(search.toLowerCase())) return false
    return true
  })

  useEffect(() => {
    if (!autoScroll || !scrollRef.current) return
    // Don't yank the view out from under an in-progress text selection
    // (e.g. the user drag-selecting a line to copy) - the poll-driven
    // re-render happens every second, which would otherwise cancel the
    // selection before they can finish it.
    const selection = window.getSelection()
    if (selection && selection.toString().length > 0 && scrollRef.current.contains(selection.anchorNode)) return
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [filtered.length, autoScroll])

  const { data: stats } = useQuery({ queryKey: ['log-stats'], queryFn: async () => (await getApi()).get_log_stats(), refetchInterval: 5000 })

  const exportMutation = useMutation({
    mutationFn: async () => (await getApi()).export_log(),
    onSuccess: (path) => onStatusMessage(path ? `Logs exported to ${path}` : 'Export cancelled'),
  })
  const openMutation = useMutation({
    mutationFn: async () => (await getApi()).open_log_file(),
    onSuccess: (ok) => onStatusMessage(ok ? 'Opened log file' : 'Log file not found'),
  })
  const clearMutation = useMutation({
    mutationFn: async () => (await getApi()).clear_log(),
    onSuccess: (newOffset) => {
      offsetRef.current = newOffset
      setBuffer([])
      onStatusMessage('Logs cleared')
    },
  })

  return (
    <div className="flex flex-col h-full">
      <div className="flex flex-wrap items-end gap-3 pb-4">
        <Select label="Level" value={level} onChange={(e) => setLevel(e.target.value as typeof level)} className="w-32">
          {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
        </Select>
        <TextField label="Search" mono placeholder="Filter logs…" value={search} onChange={(e) => setSearch(e.target.value)} className="w-56" />
        <label className="flex items-center gap-1.5 text-xs text-text-secondary pb-2">
          <input type="checkbox" checked={autoScroll} onChange={(e) => setAutoScroll(e.target.checked)} className="accent-(--accent)" /> Auto-scroll
        </label>
        <div className="ml-auto flex gap-2">
          <Button onClick={() => clearMutation.mutate()} disabled={clearMutation.isPending}>Clear</Button>
        </div>
      </div>
      <Divider />
      <div ref={scrollRef} className="flex-1 overflow-auto bg-surface border border-border font-mono tabular-nums text-[11px] leading-relaxed py-2 my-4">
        {filtered.length === 0
          ? <div className="px-4 py-2 text-text-disabled">Waiting for server activity — logs stream here once the server is running.</div>
          : filtered.map((l, i) => {
              const parsed = parseLine(l)
              if (!parsed) {
                return <div key={i} className="px-4 py-0.5 text-text-disabled whitespace-pre">{l}</div>
              }
              const style = LEVEL_STYLE[parsed.level]
              return (
                <div key={i} className={`flex gap-3 px-3.5 py-0.5 ${style.row}`}>
                  <span className="shrink-0 w-17.5 text-text-disabled">{parsed.time}</span>
                  <span className={`shrink-0 w-16 font-semibold ${style.text}`}>{parsed.level}</span>
                  <span className="shrink-0 w-35 truncate text-accent/85">[{parsed.module}]</span>
                  <span className="min-w-0 flex-1 text-text-primary wrap-break-word">{parsed.message}</span>
                </div>
              )
            })}
      </div>
      <Divider />
      <div className="flex items-center gap-2 pt-4">
        <Button onClick={() => exportMutation.mutate()}>Export Logs</Button>
        <Button onClick={() => openMutation.mutate()}>Open Log File</Button>
        <span className="ml-auto text-[11px] font-mono tabular-nums text-text-secondary">
          {stats ? `${stats.total_entries} entries · ${((stats.file_size_bytes ?? 0) / 1024).toFixed(1)} KB` : 'Log file: not available'}
        </span>
      </div>
    </div>
  )
}
