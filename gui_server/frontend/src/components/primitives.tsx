import { useEffect, useState } from 'react'
import type { ButtonHTMLAttributes, HTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'
import { Download } from 'lucide-react'
import { getApi } from '../api/client'
import type { SignalRecord } from '../api/types'

// Shared layout/visual primitives. Structural philosophy ported from
// gui_server/gui/theme/layout.py's "grounded" approach: content sits
// directly on the window background; Section is the workhorse (heading +
// hairline divider + content), Card is reserved for genuinely repeating
// self-contained units (stat tiles, signal chips, template slots) rather
// than generic grouping. Section titles are rendered as small tracked
// uppercase labels — the "everything is labeled, nothing is decorated"
// vernacular of a trading terminal, not a stylistic flourish.

export function Section({ title, action, children, className = '' }: { title: ReactNode; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`mb-7 ${className}`}>
      <div className="flex items-center justify-between mb-2">
        <h2 className="flex items-center gap-2 text-[11px] font-semibold tracking-[0.14em] uppercase text-text-secondary">{title}</h2>
        {action}
      </div>
      <div className="h-px bg-divider/15 mb-3.5" />
      <div>{children}</div>
    </section>
  )
}

export function Divider({ vertical = false, className = '' }: { vertical?: boolean; className?: string }) {
  return vertical
    ? <div className={`w-px bg-divider/15 self-stretch ${className}`} />
    : <div className={`h-px bg-divider/15 ${className}`} />
}

/** `square` opts out of the card's default 10px radius -- for popups/modals,
 * which read as precise, dialog-like overlays rather than the persistent
 * "financial terminal" surfaces the rounded corner is meant for elsewhere. */
export function Card({ children, className = '', square = false, ...props }: HTMLAttributes<HTMLDivElement> & { children: ReactNode; className?: string; square?: boolean }) {
  return (
    <div {...props} className={`bg-surface border border-border ${square ? '' : 'rounded-card'} ${className}`}>
      {children}
    </div>
  )
}

const buttonVariants = {
  primary: 'bg-accent hover:bg-accent-hover active:bg-accent-pressed text-text-on-accent',
  success: 'bg-success hover:brightness-110 text-text-on-accent',
  danger: 'bg-error hover:brightness-110 text-text-on-accent',
  warning: 'bg-warning hover:brightness-110 text-text-on-accent',
  neutral: 'bg-surface-alt hover:brightness-95 dark:hover:brightness-125 text-text-primary',
  ghost: 'bg-transparent hover:bg-surface-alt text-text-primary border border-border',
} as const

export function Button({
  variant = 'neutral', pill = false, className = '', children, ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof buttonVariants; pill?: boolean }) {
  return (
    <button
      {...props}
      className={`px-4 py-2 text-xs font-semibold tracking-wide uppercase transition-all duration-150 disabled:opacity-35 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-2 focus-visible:ring-offset-ground active:scale-[0.98] ${pill ? 'rounded-full' : ''} ${buttonVariants[variant]} ${className}`}
    >
      {children}
    </button>
  )
}

const fieldBase = 'bg-surface border border-border px-3 py-1.5 text-sm text-text-primary placeholder:text-text-disabled transition-colors focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/40'

export function TextField({ label, mono = false, className = '', ...props }: InputHTMLAttributes<HTMLInputElement> & { label?: string; mono?: boolean }) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      {label && <span className="text-[11px] tracking-[0.08em] uppercase text-text-secondary">{label}</span>}
      <input {...props} className={`${fieldBase} ${mono ? 'font-mono tabular-nums' : ''} ${className}`} />
    </label>
  )
}

export function Select({ label, className = '', children, ...props }: SelectHTMLAttributes<HTMLSelectElement> & { label?: string }) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      {label && <span className="text-[11px] tracking-[0.08em] uppercase text-text-secondary">{label}</span>}
      <span className="relative inline-block">
        <select
          {...props}
          className={`${fieldBase} appearance-none pr-8 cursor-pointer ${className}`}
        >
          {children}
        </select>
        <svg className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-text-secondary" width="10" height="6" viewBox="0 0 10 6" fill="none">
          <path d="M1 1L5 5L9 1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
    </label>
  )
}

export function Slider({ label, value, display, onChange, min, max, step }: {
  label: string; value: number; display: string; onChange: (v: number) => void; min: number; max: number; step: number
}) {
  return (
    <label className="flex flex-col gap-1.5 text-sm">
      <span className="flex items-baseline justify-between text-[11px] tracking-[0.08em] uppercase text-text-secondary">
        <span>{label}</span>
        <span className="font-mono tabular-nums normal-case tracking-normal text-text-primary">{display}</span>
      </span>
      <input
        type="range" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1 w-full cursor-pointer appearance-none rounded-full bg-surface-alt accent-(--accent)"
      />
    </label>
  )
}

export function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <Card className="p-3.5">
      <div className="text-[10px] tracking-widest uppercase text-text-secondary">{label}</div>
      <div className="text-base font-mono tabular-nums font-medium text-text-primary mt-1.5">{value}</div>
    </Card>
  )
}

const signalStyles: Record<string, { icon: string; color: string }> = {
  BUY: { icon: '▲', color: 'text-success' },
  SELL: { icon: '▼', color: 'text-error' },
  WAIT: { icon: '■', color: 'text-signal-wait' },
}

/** One compact, single-line row in the decision-history list, using the
 * panel's full width instead of stacking action/entry/reasoning across
 * three lines. Click opens a detail modal with the full record — the AI's
 * complete reasoning doesn't fit (and shouldn't be squeezed into) one line. */
export function SignalRow({ record, onClick }: { record: SignalRecord; onClick: () => void }) {
  const { action, symbol, confidence, timestamp, reasoning, entry_price, stop_loss, take_profit } = record
  const style = signalStyles[action] ?? signalStyles.WAIT
  const vetoed = reasoning.includes('[VETOED')
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-4 py-2 first:pt-0 last:pb-0 text-left hover:bg-surface-alt/50 transition-colors focus-visible:outline-none focus-visible:bg-surface-alt/50"
    >
      <span className={`text-xs font-semibold tracking-wide shrink-0 whitespace-nowrap ${style.color}`}>
        {style.icon} {action} <span className="font-mono text-text-primary">{symbol}</span>
      </span>
      <span className="flex-1 min-w-0 truncate text-[11px] font-mono tabular-nums text-text-secondary">
        {entry_price != null ? (
          <>
            Entry <span className="text-text-primary">{entry_price.toFixed(2)}</span>
            {stop_loss != null && <> · SL <span className="text-error">{stop_loss.toFixed(2)}</span></>}
            {take_profit != null && <> · TP <span className="text-success">{take_profit.toFixed(2)}</span></>}
          </>
        ) : reasoning}
      </span>
      {vetoed && <span className="shrink-0 text-[10px] font-semibold tracking-widest uppercase text-warning">Vetoed</span>}
      <span className="shrink-0 text-[11px] font-mono tabular-nums text-text-secondary">
        {confidence.toFixed(0)}% · {new Date(timestamp).toLocaleTimeString()}
      </span>
    </button>
  )
}

/** One row in the live open-positions list, sourced from the EA heartbeat —
 * real-time floating P&L, not a decision record. */
export function PositionRow({ type, symbol, open_price, current_price, volume, stop_loss, take_profit, profit }: {
  type: string; symbol: string; open_price: number; current_price: number; volume: number
  stop_loss: number; take_profit: number; profit: number
}) {
  const style = signalStyles[type] ?? signalStyles.WAIT
  const profitColor = profit > 0 ? 'text-success' : profit < 0 ? 'text-error' : 'text-text-secondary'
  return (
    <div className="py-2.5 first:pt-0 last:pb-0 flex items-center justify-between gap-3">
      <div className="flex flex-col gap-0.5 min-w-0">
        <span className={`text-xs font-semibold tracking-wide ${style.color}`}>
          {style.icon} {type} <span className="font-mono text-text-primary">{symbol}</span>{' '}
          <span className="font-mono text-text-secondary font-normal">{volume.toFixed(2)} lots</span>
        </span>
        <span className="text-[11px] font-mono tabular-nums text-text-secondary truncate">
          Entry {open_price.toFixed(2)} &rarr; {current_price.toFixed(2)} · SL {stop_loss.toFixed(2)} · TP {take_profit.toFixed(2)}
        </span>
      </div>
      <span className={`text-sm font-mono tabular-nums font-semibold shrink-0 ${profitColor}`}>
        {profit >= 0 ? '+' : ''}{profit.toFixed(2)}
      </span>
    </div>
  )
}

/** RUNNING/STOPPED-style status dot. Motion (a soft pulse ring) is reserved
 * for the one truly live signal in the app — everything else stays still.
 * `pulse` opts a given usage out of that ring entirely (e.g. a badge that
 * should read as calmly "on" rather than actively blinking). */
export function StatusDot({ live, color, pulse = true }: { live: boolean; color: 'success' | 'error' | 'neutral'; pulse?: boolean }) {
  const hex = color === 'success' ? 'var(--success)' : color === 'error' ? 'var(--error)' : 'var(--text-disabled)'
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${live && pulse ? 'animate-pulse-ring' : ''}`}
      style={{ backgroundColor: hex, ['--pulse-color' as string]: hex }}
    />
  )
}

/** Full-size view of a thumbnail-sized preview image, dismissed via backdrop
 * click, X, or Escape. `downloadName` adds a download button + a live
 * width×height readout (read off the decoded image itself) -- the fastest
 * way to confirm a composite/export actually came out at the size expected,
 * without leaving the app to check a saved file's properties. */
export function Lightbox({ src, alt, onClose, downloadName }: { src: string; alt: string; onClose: () => void; downloadName?: string }) {
  const [dims, setDims] = useState<{ w: number; h: number } | null>(null)

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-8" onClick={onClose}>
      <img
        src={src} alt={alt} className="max-h-full max-w-full object-contain"
        onClick={(e) => e.stopPropagation()}
        onLoad={(e) => setDims({ w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
      />
      <div className="absolute top-5 right-5 flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
        {dims && (
          <span className="flex h-9 items-center bg-black/50 px-3 text-xs font-mono tabular-nums text-white">
            {dims.w} × {dims.h}px
          </span>
        )}
        {downloadName && (
          <button
            onClick={() => getApi().then((api) => api.save_data_uri(src, downloadName))}
            aria-label="Download image"
            className="flex h-9 w-9 items-center justify-center bg-black/50 text-white transition hover:bg-black/70"
          >
            <Download size={14} />
          </button>
        )}
        <button
          onClick={onClose}
          aria-label="Close"
          className="flex h-9 w-9 items-center justify-center rounded-full bg-black/50 text-white transition hover:bg-black/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        >
          ×
        </button>
      </div>
    </div>
  )
}

export function Spinner({ className = '' }: { className?: string }) {
  return <div className={`inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent ${className}`} />
}
