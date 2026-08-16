import { ArrowRight } from 'lucide-react'
import coverWebp from '../../assets/aegisvision-cover.webp'
import coverJpg from '../../assets/aegisvision-cover.jpg'

export default function LandingPage({ onEnter }: { onEnter: () => void }) {
  return (
    <div className="relative flex h-screen flex-col overflow-hidden bg-ground text-text-primary">
      <picture className="absolute inset-0 block">
        <source srcSet={coverWebp} type="image/webp" />
        <img src={coverJpg} alt="" aria-hidden="true" className="h-full w-full object-cover" />
      </picture>
      <div className="pointer-events-none absolute inset-0 bg-linear-to-t from-ground via-ground/40 to-ground/70" />

      <header className="relative z-10 shrink-0 px-6 py-3.5 md:px-16">
        <span className="text-[20px] tracking-wide" style={{ fontFamily: 'var(--font-logo)' }}>
          <span className="text-accent">Aegis</span>
          <span className="text-text-primary">Vision</span>{' '}
          <span className="text-accent">AI</span>
        </span>
      </header>

      <main className="relative z-10 flex flex-1 items-end px-6 pb-16 md:px-16 md:pb-24">
        <div className="max-w-2xl">
          <p className="mb-4 text-[11px] font-mono font-semibold uppercase tracking-[0.22em] text-accent">
            Multi-Agent Vision Pipeline · MT5
          </p>
          <h1 className="text-[40px] font-medium leading-[1.1] md:text-[52px]" style={{ fontFamily: 'var(--font-display)' }}>
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
          </div>
        </div>
      </main>

      <footer className="relative z-10 grid shrink-0 grid-cols-3 items-center px-6 py-4 text-[11px] text-text-disabled md:px-16">
        <span className="justify-self-start">© {new Date().getFullYear()} AegisVision AI</span>
        <span className="justify-self-center text-center">
          Runs locally against your own MT5 terminal. Nothing you see here leaves your machine.
        </span>
        <span aria-hidden="true" />
      </footer>
    </div>
  )
}
