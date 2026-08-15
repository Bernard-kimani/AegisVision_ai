import { useMemo } from 'react'
import { ArrowRight } from 'lucide-react'

/** Ambient candlestick tape + its own trailing moving-average line, built
 * from the app's real success/error/accent tokens rather than a stock photo
 * — the one signature element on this page, and it's literally the same
 * visual grammar Agent 2 looks at (see chart_generator.py). Deterministic
 * (fixed seed) so the hero doesn't re-jitter on every re-render. */
function CandleTape() {
  const w = 960
  const h = 440

  const candles = useMemo(() => {
    let seed = 1337
    const rand = () => {
      seed = (seed * 9301 + 49297) % 233280
      return seed / 233280
    }
    let price = 52
    const out: { open: number; close: number; high: number; low: number }[] = []
    for (let i = 0; i < 64; i++) {
      const drift = (rand() - 0.47) * 9
      const open = price
      const close = Math.max(10, Math.min(92, open + drift))
      const high = Math.max(open, close) + rand() * 5
      const low = Math.min(open, close) - rand() * 5
      out.push({ open, close, high: Math.min(98, high), low: Math.max(2, low) })
      price = close
    }
    return out
  }, [])

  const gap = w / candles.length
  const bodyW = gap * 0.5
  const y = (v: number) => h - (v / 100) * h

  const maPath = useMemo(() => {
    const win = 7
    return candles
      .map((c, i) => {
        const slice = candles.slice(Math.max(0, i - win + 1), i + 1)
        const avg = slice.reduce((a, b) => a + b.close, 0) / slice.length
        return `${i === 0 ? 'M' : 'L'} ${i * gap + gap / 2},${y(avg)}`
      })
      .join(' ')
  }, [candles, gap])

  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="xMidYMid slice" className="absolute inset-0 h-full w-full" aria-hidden="true">
      <defs>
        <linearGradient id="tape-fade" x1="0" x2="1">
          <stop offset="0%" stopColor="var(--ground)" stopOpacity="1" />
          <stop offset="52%" stopColor="var(--ground)" stopOpacity="0.85" />
          <stop offset="78%" stopColor="var(--ground)" stopOpacity="0.15" />
          <stop offset="100%" stopColor="var(--ground)" stopOpacity="0" />
        </linearGradient>
      </defs>
      {candles.map((c, i) => {
        const x = i * gap + gap / 2
        const up = c.close >= c.open
        const color = up ? 'var(--success)' : 'var(--error)'
        const top = y(Math.max(c.open, c.close))
        const bottom = y(Math.min(c.open, c.close))
        return (
          <g key={i}>
            <line x1={x} x2={x} y1={y(c.high)} y2={y(c.low)} stroke={color} strokeWidth={1.1} opacity={0.32} />
            <rect x={x - bodyW / 2} y={top} width={bodyW} height={Math.max(1.5, bottom - top)} fill={color} opacity={0.32} />
          </g>
        )
      })}
      <path d={maPath} fill="none" stroke="var(--accent)" strokeWidth={2} opacity={0.55} />
      <rect x="0" y="0" width={w} height={h} fill="url(#tape-fade)" />
    </svg>
  )
}

export default function LandingPage({ onEnter }: { onEnter: () => void }) {
  return (
    <div className="relative flex h-screen flex-col overflow-hidden bg-ground text-text-primary">
      <CandleTape />
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-t from-ground via-transparent to-ground/70" />

      <header className="relative z-10 shrink-0 px-6 py-3.5 md:px-16">
        <span className="text-[20px] tracking-wide" style={{ fontFamily: 'var(--font-logo)' }}>
          <span className="text-accent">Aegis</span>
          <span className="text-text-primary">Vision</span>{' '}
          <span className="text-accent">AI</span>
        </span>
      </header>

      <main className="relative z-10 flex flex-1 items-center px-6 md:px-16">
        <div className="max-w-2xl">
          <p className="mb-4 text-[11px] font-mono font-semibold uppercase tracking-[0.22em] text-accent">
            Multi-Agent Vision Pipeline · MT5
          </p>
          <h1 className="text-[36px] font-medium leading-[1.1] md:text-[46px]" style={{ fontFamily: 'var(--font-display)' }}>
            It Watches Every Candle.
            <br />
            <span className="font-semibold italic text-accent">It Trades Only What It Sees.</span>
          </h1>
          <p className="mt-6 max-w-md text-[15px] leading-relaxed text-text-secondary">
            A live MT5 feed runs through an autonomous pipeline — preprocessing, chart rendering, and a vision
            model that checks each setup against your reference template — before a single order reaches the
            market. Every call ships with its own reasoning and a full audit trail.
          </p>
          <div className="mt-9 flex flex-wrap items-center gap-4">
            <button
              onClick={onEnter}
              className="inline-flex items-center gap-2 rounded-full bg-accent px-7 py-3.5 text-[13px] font-semibold uppercase tracking-[0.08em] text-text-on-accent transition-all duration-150 hover:bg-accent-hover active:scale-[0.98] active:bg-accent-pressed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-ground"
            >
              Console
              <ArrowRight size={15} />
            </button>
            <span className="text-xs text-text-disabled">No account needed — opens your local console.</span>
          </div>
        </div>
      </main>

      <footer className="relative z-10 shrink-0 px-6 py-4 text-[11px] text-text-disabled md:px-16">
        Runs locally against your own MT5 terminal. Nothing you see here leaves your machine.
      </footer>
    </div>
  )
}
