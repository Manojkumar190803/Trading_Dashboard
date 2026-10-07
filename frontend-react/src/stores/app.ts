import { create } from 'zustand'
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
  clearLogs: () => void
  maxLogsDisplay: number

  // Instruments
  instruments: Instrument[]
  setInstruments: (instruments: Instrument[]) => void
  addInstrument: (instrument: Instrument) => void
  updateInstrument: (id: string, instrument: Partial<Instrument>) => void
  deleteInstrument: (id: string) => void
  toggleInstrument: (id: string) => void

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

export const useAppStore = create<AppStore>((set) => ({
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
  }))

