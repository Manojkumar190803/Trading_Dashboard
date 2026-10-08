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
  exportInstruments: () => Promise<void>
  getStrategyStatus: () => Promise<any>

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
    exportInstruments: async () => {
      try {
        const state = useAppStore.getState()
        const response = await fetch('/api/instruments/export', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ instruments: state.instruments }),
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

    // UI State
    sidebarOpen: true,
    setSidebarOpen: (open) => set({ sidebarOpen: open }),
    currentPage: 'dashboard',
    setCurrentPage: (page) => set({ currentPage: page }),
    autoRefreshEnabled: true,
    setAutoRefreshEnabled: (enabled) => set({ autoRefreshEnabled: enabled }),
    refreshInterval: 5000,
    setRefreshInterval: (interval) => set({ refreshInterval: interval }),

    // Loading
    isLoading: false,
    setIsLoading: (loading) => set({ isLoading: loading }),
    error: null,
    setError: (error) => set({ error }),
    }),
    {
      name: 'app-store',
      partialize: (state) => ({
        instruments: state.instruments,
      }),
    }
  )
)

