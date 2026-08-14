import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from 'react'

// Shared layout/visual primitives. Structural philosophy ported from
// gui_server/gui/theme/layout.py's "grounded" approach: content sits
// directly on the window background; Section is the workhorse (heading +
// hairline divider + content), Card is reserved for genuinely repeating
// self-contained units (stat tiles, signal chips, template slots) rather
// than generic grouping. Section titles are rendered as small tracked
// uppercase labels — the "everything is labeled, nothing is decorated"
// vernacular of a trading terminal, not a stylistic flourish.

export function Section({ title, action, children, className = '' }: { title: string; action?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`mb-7 ${className}`}>
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-[11px] font-semibold tracking-[0.14em] uppercase text-text-secondary">{title}</h2>
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

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`bg-surface border border-border rounded-card ${className}`}>
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

export function SignalChip({ action, symbol, confidence, timestamp, reasoning }: {
  action: string; symbol: string; confidence: number; timestamp: string; reasoning: string
}) {
  const style = signalStyles[action] ?? signalStyles.WAIT
  return (
    <Card className="p-3 w-48 h-24 shrink-0 flex flex-col justify-between overflow-hidden">
      <div className={`text-xs font-semibold tracking-wide ${style.color}`}>{style.icon} {action} <span className="font-mono">{symbol}</span></div>
      <div className="text-[11px] font-mono tabular-nums text-text-secondary">{timestamp} · {confidence.toFixed(0)}%</div>
      <div className="text-[11px] text-text-primary line-clamp-2 leading-snug">{reasoning}</div>
    </Card>
  )
}

/** RUNNING/STOPPED-style status dot. Motion (a soft pulse ring) is reserved
 * for the one truly live signal in the app — everything else stays still. */
export function StatusDot({ live, color }: { live: boolean; color: 'success' | 'error' }) {
  const hex = color === 'success' ? 'var(--success)' : 'var(--error)'
  return (
    <span
      className={`inline-block h-2 w-2 rounded-full ${live ? 'animate-pulse-ring' : ''}`}
      style={{ backgroundColor: hex, ['--pulse-color' as string]: hex }}
    />
  )
}

export function Spinner({ className = '' }: { className?: string }) {
  return <div className={`inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent ${className}`} />
}
