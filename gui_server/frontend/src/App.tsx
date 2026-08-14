import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Settings, X } from 'lucide-react'
import { getApi } from './api/client'
import { StatusDot } from './components/primitives'
import ControlsPage from './features/controls/ControlsPage'
import StrategiesPage from './features/strategies/StrategiesPage'
import BacktestPage from './features/backtest/BacktestPage'
import LogsPage from './features/logs/LogsPage'

const TABS = ['Controls', 'Strategies', 'Backtest', 'Logs'] as const
type Tab = (typeof TABS)[number]

export default function App() {
  const [tab, setTab] = useState<Tab>('Controls')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [theme, setTheme] = useState<'dark' | 'light'>('dark')
  const [statusMessage, setStatusMessage] = useState('Ready')

  useEffect(() => {
    getApi().then((api) => api.get_theme()).then((t) => setTheme(t === 'light' ? 'light' : 'dark'))
  }, [])

  useEffect(() => {
    document.documentElement.classList.toggle('dark', theme === 'dark')
  }, [theme])

  const { data: status } = useQuery({
    queryKey: ['server-status'],
    queryFn: async () => (await getApi()).get_server_status(),
    refetchInterval: 3000,
  })

  const toggleTheme = async () => {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next)
    ;(await getApi()).set_theme(next)
  }

  const running = status?.is_running ?? false

  return (
    <div className="flex h-screen flex-col bg-ground text-text-primary">
      <header className="grid grid-cols-3 items-center px-6 py-3.5 shrink-0">
        <h1 className="justify-self-start text-[22px] leading-none" style={{ fontFamily: 'var(--font-display)' }}>
          <span className="font-medium">AegisVision</span>{' '}
          <span className="italic font-semibold text-accent">AI</span>
        </h1>

        <nav className="flex justify-self-center gap-6">
          {TABS.map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`border-b-2 pb-1 text-[11px] font-semibold tracking-[0.14em] uppercase transition-colors focus-visible:outline-none ${
                tab === t ? 'border-accent text-text-primary' : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              {t}
            </button>
          ))}
        </nav>

        <button
          onClick={() => setDrawerOpen(true)}
          className="justify-self-end p-2 rounded-full text-text-secondary hover:text-text-primary hover:bg-surface-alt transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
          aria-label="Settings"
        >
          <Settings size={18} />
        </button>
      </header>

      {/* Ticker rule — a thin market-open line that carries the accent only
          while the server is actually live, echoing the app's one real-time
          signal instead of decorating unconditionally. */}
      <div className={`h-px shrink-0 transition-colors duration-700 ${running ? 'bg-accent' : 'bg-divider/15'}`} />

      <main className="flex-1 overflow-auto p-6">
        {tab === 'Controls' && <ControlsPage onStatusMessage={setStatusMessage} />}
        {tab === 'Strategies' && <StrategiesPage onStatusMessage={setStatusMessage} />}
        {tab === 'Backtest' && <BacktestPage onStatusMessage={setStatusMessage} />}
        {tab === 'Logs' && <LogsPage onStatusMessage={setStatusMessage} />}
      </main>

      <footer className="flex items-center justify-between px-6 py-2.5 border-t border-border text-[11px] text-text-secondary shrink-0">
        <span>{statusMessage}</span>
        <span className="flex items-center gap-2 font-mono tracking-wide">
          <StatusDot live={running} color={running ? 'success' : 'error'} />
          {running ? 'RUNNING' : 'STOPPED'}
        </span>
      </footer>

      {drawerOpen && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="flex-1 bg-black/40" onClick={() => setDrawerOpen(false)} />
          <div className="w-72 bg-surface border-l border-border p-6 flex flex-col gap-5">
            <div className="flex items-center justify-between">
              <h2 className="text-[11px] font-semibold tracking-[0.14em] uppercase text-text-secondary">Settings</h2>
              <button onClick={() => setDrawerOpen(false)} aria-label="Close" className="text-text-secondary hover:text-text-primary">
                <X size={16} />
              </button>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm">Appearance</span>
              <button
                onClick={toggleTheme}
                className="px-3 py-1.5 text-[11px] font-semibold tracking-wide uppercase bg-accent text-text-on-accent rounded-full transition hover:bg-accent-hover"
              >
                {theme === 'dark' ? 'Dark' : 'Light'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
