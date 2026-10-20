import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import {
  DashboardMetrics,
  Position,
  Trade,
  EquityCurvePoint,
  StrategyAlert,
  Order,
  LogEntry,
  Instrument,
  TrailingStopsConfig,
} from '@/types'

interface AppStore {
  // Dashboard
  metrics: DashboardMetrics | null
  setMetrics: (metrics: DashboardMetrics) => void

  // Positions
  positions: Position[]
  setPositions: (positions: Position[]) => void

  // Trades
  trades: Trade[]
  setTrades: (trades: Trade[]) => void

  // Equity curve
  equityCurve: EquityCurvePoint[]
  setEquityCurve: (curve: EquityCurvePoint[]) => void

  // Alerts
  alerts: StrategyAlert[]
  addAlert: (alert: StrategyAlert) => void
  clearAlerts: () => void
  maxAlertsDisplay: number

  // Orders
  orders: Order[]
  setOrders: (orders: Order[]) => void

  // Logs
  logs: LogEntry[]
  addLog: (log: LogEntry) => void
  setLogs: (logs: LogEntry[]) => void
  clearLogs: () => void
  maxLogsDisplay: number

  // Instruments
  instruments: Instrument[]
  setInstruments: (instruments: Instrument[]) => void
  addInstrument: (instrument: Instrument) => void
  updateInstrument: (id: string, instrument: Partial<Instrument>) => void
  deleteInstrument: (id: string) => void
  toggleInstrument: (id: string) => void
  exportInstruments: (instruments?: Instrument[]) => Promise<void>
  getStrategyStatus: () => Promise<any>

  // Global Trailing Stops Configuration
  trailingStopsConfig: TrailingStopsConfig
  setTrailingStopsConfig: (config: Partial<TrailingStopsConfig>) => void
  resetTrailingStopsConfig: () => void

  // Theme
  theme: 'dark' | 'light'
  setTheme: (theme: 'dark' | 'light') => void
  toggleTheme: () => void

  // UI State
  sidebarOpen: boolean
  setSidebarOpen: (open: boolean) => void
  currentPage: string
  setCurrentPage: (page: string) => void
  autoRefreshEnabled: boolean
  setAutoRefreshEnabled: (enabled: boolean) => void
  refreshInterval: number
  setRefreshInterval: (interval: number) => void

  // Loading
  isLoading: boolean
  setIsLoading: (loading: boolean) => void
  error: string | null
  setError: (error: string | null) => void
}

export const useAppStore = create<AppStore>(
  persist(
    (set) => ({
    // Dashboard
    metrics: null,
    setMetrics: (metrics) => set({ metrics }),

    // Positions
    positions: [],
    setPositions: (positions) => set({ positions }),

    // Trades
    trades: [],
    setTrades: (trades) => set({ trades }),

    // Equity curve
    equityCurve: [],
    setEquityCurve: (curve) => set({ equityCurve: curve }),

    // Alerts
    alerts: [],
    addAlert: (alert) =>
      set((state) => ({
        alerts: [alert, ...state.alerts].slice(0, state.maxAlertsDisplay),
      })),
    clearAlerts: () => set({ alerts: [] }),
    maxAlertsDisplay: 500,

    // Orders
    orders: [],
    setOrders: (orders) => set({ orders }),

    // Logs
    logs: [],
    addLog: (log) =>
      set((state) => ({
        logs: [log, ...state.logs].slice(0, state.maxLogsDisplay),
      })),
    setLogs: (logs) => set({ logs }),
    clearLogs: () => set({ logs: [] }),
    maxLogsDisplay: 200,

    // Instruments
    instruments: [],
    setInstruments: (instruments) => set({ instruments }),
    addInstrument: (instrument) =>
      set((state) => ({
        instruments: [...state.instruments, instrument],
      })),
    updateInstrument: (id, updates) =>
      set((state) => ({
        instruments: state.instruments.map((inst) =>
          inst.id === id ? { ...inst, ...updates, updatedAt: new Date().toISOString() } : inst
        ),
      })),
    deleteInstrument: (id) =>
      set((state) => ({
        instruments: state.instruments.filter((inst) => inst.id !== id),
      })),
    toggleInstrument: (id) =>
      set((state) => ({
        instruments: state.instruments.map((inst) =>
          inst.id === id ? { ...inst, status: !inst.status, updatedAt: new Date().toISOString() } : inst
        ),
      })),
    
    // Export instruments to backend for Python to consume
    exportInstruments: async (instruments) => {
      try {
        const state = useAppStore.getState()
        const response = await fetch('/api/instruments/export', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            instruments: instruments ?? state.instruments,
            trailingStopsConfig: state.trailingStopsConfig,
          }),
        })
        if (!response.ok) {
          throw new Error(`Export failed: ${response.statusText}`)
        }
        console.log('Instruments exported to Python backend')
      } catch (error) {
        console.error('Export instruments error:', error)
      }
    },
    
    // Get status of running strategies from backend
    getStrategyStatus: async () => {
      try {
        const response = await fetch('/api/instruments/status')
        if (!response.ok) {
          throw new Error(`Status fetch failed: ${response.statusText}`)
        }
        return await response.json()
      } catch (error) {
        console.error('Get strategy status error:', error)
        return null
      }
    },

    // Global Trailing Stops Configuration
    trailingStopsConfig: {
      breakEvenRR: 1.25,
      trailStepRR: 0.5,
      maxInitialRiskPoints: 20,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    },
    setTrailingStopsConfig: (config) =>
      set((state) => ({
        trailingStopsConfig: {
          ...state.trailingStopsConfig,
          ...config,
          updatedAt: new Date().toISOString(),
        },
      })),
    resetTrailingStopsConfig: () =>
      set({
        trailingStopsConfig: {
          breakEvenRR: 1.25,
          trailStepRR: 0.5,
          maxInitialRiskPoints: 20,
          createdAt: new Date().toISOString(),
          updatedAt: new Date().toISOString(),
        },
      }),

    // UI State
    sidebarOpen: true,
    setSidebarOpen: (open) => set({ sidebarOpen: open }),
    currentPage: 'dashboard',
    setCurrentPage: (page) => set({ currentPage: page }),
    autoRefreshEnabled: true,
    setAutoRefreshEnabled: (enabled) => set({ autoRefreshEnabled: enabled }),
    refreshInterval: 5000,
    setRefreshInterval: (interval) => set({ refreshInterval: interval }),

    // Theme
    theme: 'dark' as 'dark' | 'light',
    setTheme: (theme) => {
      set({ theme })
      // Apply theme to document
      if (theme === 'light') {
        document.documentElement.classList.add('light')
      } else {
        document.documentElement.classList.remove('light')
      }
    },
    toggleTheme: () => {
      set((state) => {
        const newTheme = state.theme === 'dark' ? 'light' : 'dark'
        if (newTheme === 'light') {
          document.documentElement.classList.add('light')
        } else {
          document.documentElement.classList.remove('light')
        }
        return { theme: newTheme }
      })
    },

    // Loading
    isLoading: false,
    setIsLoading: (loading) => set({ isLoading: loading }),
    error: null,
    setError: (error) => set({ error }),
    }),
    {
      name: 'app-store',
      partialize: (state: AppStore) => ({
        instruments: state.instruments,
        theme: state.theme,
        trailingStopsConfig: state.trailingStopsConfig,
      }),
    }
  ) as any
)

