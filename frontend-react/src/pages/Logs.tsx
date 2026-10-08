import { useState, useEffect } from 'react'
import { AlertCircle, AlertTriangle, CheckCircle2, Info, Pause, TrendingUp, Clock, Download, RotateCcw } from 'lucide-react'
import {
  Card,
  SectionTitle,
  EmptyState,
  Badge,
} from '@/components/UI'
import { formatTime } from '@/utils/format'
import { useAppStore } from '@/stores'
import { clsx } from 'clsx'

interface LogEntry {
  id: string
  timestamp: string
  level: 'INFO' | 'SUCCESS' | 'WARNING' | 'ERROR'
  message: string
  category?: string
  strategy?: string
  details?: string
}

interface AlertEntry {
  id: string
  timestamp: string
  strategy: string
  alert_type: string
  symbol: string
  message: string
  status: string
}

const Logs: React.FC = () => {
  const { instruments, logs: storeLogs, setLogs: setStoreLogs } = useAppStore()
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [alerts, setAlerts] = useState<AlertEntry[]>([])

  // Load logs from real signal log file - reads actual EMA21 strategy signals
  useEffect(() => {
    const loadLogsFromData = async () => {
      try {
        // Fetch real signal logs from EMA21 strategy
        const response = await fetch(`/logs/ema21_3min_logs.json?t=${Date.now()}`)
        if (response.ok) {
          const data = await response.json()
          if (data.logs && Array.isArray(data.logs)) {
            // Set logs in Zustand store
            setStoreLogs(data.logs)
          }
        }
      } catch (error) {
        // File might not exist yet - that's OK
        console.debug('No signal logs available yet:', error)
      }
    }
    
    // Load logs on mount and every 2 seconds for real-time updates
    loadLogsFromData()
    const interval = setInterval(loadLogsFromData, 2000)
    
    return () => clearInterval(interval)
  }, [setStoreLogs])

  // Sync logs from store
  useEffect(() => {
    setLogs(storeLogs as any)
  }, [storeLogs])

  // Load triggered alerts from JSON file
  useEffect(() => {
    const loadAlertsFromData = async () => {
      try {
        // Fetch triggered alerts from EMA21 strategy
        const response = await fetch(`/logs/ema21_triggered_alerts.json?t=${Date.now()}`)
        if (response.ok) {
          const data = await response.json()
          if (data.alerts && Array.isArray(data.alerts)) {
            setAlerts(data.alerts)
          }
        }
      } catch (error) {
        // File might not exist yet - that's OK
        console.debug('No triggered alerts available yet:', error)
      }
    }
    
    // Load alerts on mount and every 2 seconds for real-time updates
    loadAlertsFromData()
    const interval = setInterval(loadAlertsFromData, 2000)
    
    return () => clearInterval(interval)
  }, [])

  const [filterLevel, setFilterLevel] = useState<LogEntry['level'] | 'ALL'>('ALL')
  const [filterStrategy, setFilterStrategy] = useState<string>('ALL')
  const [expandedLog, setExpandedLog] = useState<string | null>(null)

  // Helper function to check if market is currently open (9:00 AM to 3:30 PM IST)
  const isMarketOpen = (): boolean => {
    const now = new Date()
    const hours = now.getHours()
    const minutes = now.getMinutes()
    
    // Market hours: 9:00 AM (9) to 3:30 PM (15:30)
    // 9 = 9:00 AM, 15 = 3:00 PM, 16 = 4:00 PM
    if (hours < 9) return false // Before 9 AM
    if (hours > 15) return false // After 3:30 PM
    if (hours === 9) return true // From 9 AM onwards
    if (hours === 15 && minutes >= 30) return false // After 3:30 PM
    return true // Between 10 AM to 3:30 PM
  }

  // Get unique strategies
  const strategies = Array.from(
    new Set(logs.map((l) => l.strategy).filter(Boolean))
  ) as string[]

  // Get latest candle time from logs
  const getLatestCandleTime = (): string => {
    if (logs.length === 0) return 'N/A'
    const sortedLogs = [...logs].sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    )
    const latestTimestamp = sortedLogs[0].timestamp
    const date = new Date(latestTimestamp)
    const hours = String(date.getHours()).padStart(2, '0')
    const minutes = String(date.getMinutes()).padStart(2, '0')
    const seconds = String(date.getSeconds()).padStart(2, '0')
    return `${hours}:${minutes}:${seconds}`
  }

  // Extract active symbols from logs
  const getActiveSymbols = (): Array<{
    name: string
    symbol: string
    strike: string
    premium?: string
    directions: string[]
    strategy: string
  }> => {
    const activeSymbols: Record<string, any> = {}
    
    logs.forEach((log) => {
      // Extract symbols from messages like "NIFTY25SEP26000CE" or "NIFTY25SEP26100CE"
      const symbolMatch = log.message.match(/([A-Z]+\d+[A-Z]+\d+[CE|PE]{2})/g)
      if (symbolMatch && log.strategy !== 'All') {
        symbolMatch.forEach((sym) => {
          const isCE = sym.endsWith('CE')
          const isPE = sym.endsWith('PE')
          
          // Extract base symbol from something like "NIFTY25SEP26000CE"
          const instrumentMatch = sym.match(/^([A-Z]+)/)
          const instrument = instrumentMatch ? instrumentMatch[1] : 'NIFTY'
          const strike = sym.match(/\d{5,6}(?=[CE|PE]{2})/)?.[0] || 'N/A'
          
          // Use strike as part of the key to differentiate between same instrument with different strikes
          const key = `${instrument}_${strike}`
          
          if (!activeSymbols[key]) {
            activeSymbols[key] = {
              name: `${instrument} (${strike})`,
              symbol: sym,
              strike: strike,
              premium: 'Real-time',
              directions: [],
              strategy: log.strategy,
            }
          }
          
          if (isCE && !activeSymbols[key].directions.includes('CE')) {
            activeSymbols[key].directions.push('CE')
          }
          if (isPE && !activeSymbols[key].directions.includes('PE')) {
            activeSymbols[key].directions.push('PE')
          }
        })
      }
    })
    
    return Object.values(activeSymbols).slice(0, 3) // Return max 3 active symbols
  }

  // Filter logs - exclude INFO level logs
  const filteredLogs = logs.filter((log) => {
    const levelMatch = (filterLevel === 'ALL' || log.level === filterLevel) && log.level !== 'INFO'
    const strategyMatch =
      filterStrategy === 'ALL' || log.strategy === filterStrategy
    return levelMatch && strategyMatch
  })

  // Get log level icon
  const getLevelIcon = (level: LogEntry['level']) => {
    switch (level) {
      case 'INFO':
        return <Info size={16} className="text-accent-cyan" />
      case 'SUCCESS':
        return <CheckCircle2 size={16} className="text-accent-green" />
      case 'WARNING':
        return <AlertTriangle size={16} className="text-accent-yellow" />
      case 'ERROR':
        return <AlertCircle size={16} className="text-accent-red" />
    }
  }

  const getLevelColor = (level: LogEntry['level']) => {
    switch (level) {
      case 'INFO':
        return 'info'
      case 'SUCCESS':
        return 'success'
      case 'WARNING':
        return 'warning'
      case 'ERROR':
        return 'danger'
    }
  }

  const getLevelBgColor = (level: LogEntry['level']) => {
    switch (level) {
      case 'INFO':
        return 'bg-accent-cyan/5 border-accent-cyan/30'
      case 'SUCCESS':
        return 'bg-accent-green/5 border-accent-green/30'
      case 'WARNING':
        return 'bg-accent-yellow/5 border-accent-yellow/30'
      case 'ERROR':
        return 'bg-accent-red/5 border-accent-red/30'
    }
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // ACTIVE LOGS HELPER FUNCTIONS
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  // Extract 3-minute logs (containing "setup" or "candle" keywords) for a specific strategy and side
  const getThreeMinuteLogs = (strategy: string, side: 'CE' | 'PE'): LogEntry[] => {
    return logs.filter((log) => {
      const isCorrectStrategy = log.strategy === strategy
      const hasCorrectSide = log.message.includes(side)
      const is3MinuteLog = log.message.toLowerCase().includes('setup') || 
                           log.message.toLowerCase().includes('candle')
      return isCorrectStrategy && hasCorrectSide && is3MinuteLog
    })
  }

  // Get the most recent (current) setup log for a side
  const getCurrentSetup = (logs: LogEntry[]): LogEntry | null => {
    if (logs.length === 0) return null
    return logs[logs.length - 1] // Last log is most recent
  }

  // Get the second most recent (previous) setup event for a side
  const getPreviousSetup = (logs: LogEntry[]): LogEntry | null => {
    if (logs.length < 2) return null
    return logs[logs.length - 2] // Second to last
  }

  // Get completed 3-minute candle history (all logs for this side)
  const get3MinuteCandleHistory = (logs: LogEntry[]): LogEntry[] => {
    // Return all logs sorted by timestamp (oldest first for display)
    return [...logs].sort(
      (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
    )
  }

  // Get unique strategies that have 3-minute logs
  const getActiveStrategies = (): string[] => {
    const activeStrategies = new Set<string>()
    logs.forEach((log) => {
      if (log.strategy && (log.message.toLowerCase().includes('setup') || 
                           log.message.toLowerCase().includes('candle'))) {
        activeStrategies.add(log.strategy)
      }
    })
    return Array.from(activeStrategies)
  }

  // Reset triggered alerts
  const resetAlerts = async () => {
    if (!confirm('Are you sure you want to clear all triggered alerts?')) {
      return
    }
    try {
      const response = await fetch('/api/alerts/reset', { method: 'POST' })
      if (response.ok) {
        setAlerts([])
      }
    } catch (error) {
      console.error('Failed to reset alerts:', error)
    }
  }

  // Export 3-minute logs to CSV
  const export3MinuteLogsToCSV = () => {
    const csvLogs = logs.filter((log) => 
      log.message.toLowerCase().includes('setup') || 
      log.message.toLowerCase().includes('candle')
    )

    if (csvLogs.length === 0) {
      alert('No 3-minute logs to export')
      return
    }

    // Extract side (CE/PE) from message
    const getSideFromMessage = (message: string): string => {
      return message.includes('CE') ? 'CE' : message.includes('PE') ? 'PE' : 'UNKNOWN'
    }

    // Prepare CSV data
    const csvHeader = ['Time', 'Level', 'Message', 'Strategy', 'Side']
    const csvData = csvLogs.map((log) => [
      new Date(log.timestamp).toLocaleString('en-IN'),
      log.level,
      log.message,
      log.strategy || 'N/A',
      getSideFromMessage(log.message),
    ])

    // Create CSV content
    const csvContent = [
      csvHeader,
      ...csvData,
    ]
      .map((row) =>
        row
          .map((cell) => {
            // Escape quotes and wrap in quotes if contains comma
            const escaped = String(cell).replace(/"/g, '""')
            return escaped.includes(',') ? `"${escaped}"` : escaped
          })
          .join(',')
      )
      .join('\n')

    // Create blob and download
    const blob = new Blob([csvContent], { type: 'text/csv' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `3min_logs_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.csv`
    link.click()
    window.URL.revokeObjectURL(url)
  }

  // Export triggered alerts to CSV
  const exportAlertsToCSV = () => {
    if (alerts.length === 0) {
      alert('No triggered alerts to export')
      return
    }

    // Prepare CSV data
    const csvHeader = ['Time', 'Strategy', 'Symbol', 'Alert Type', 'Message', 'Status']
    const csvData = alerts.map((alert) => [
      new Date(alert.timestamp).toLocaleString('en-IN'),
      alert.strategy,
      alert.symbol,
      alert.alert_type,
      alert.message,
      alert.status,
    ])

    // Create CSV content
    const csvContent = [
      csvHeader,
      ...csvData,
    ]
      .map((row) =>
        row
          .map((cell) => {
            // Escape quotes and wrap in quotes if contains comma
            const escaped = String(cell).replace(/"/g, '""')
            return escaped.includes(',') ? `"${escaped}"` : escaped
          })
          .join(',')
      )
      .join('\n')

    // Create blob and download
    const blob = new Blob([csvContent], { type: 'text/csv' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `triggered_alerts_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.csv`
    link.click()
    window.URL.revokeObjectURL(url)
  }

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  return (
    <div className="space-y-8">
      {/* Monitoring Status Section - Enhanced with Market Hours Logic */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Status Card */}
        {instruments.length === 0 ? (
          // No instruments configured state
          <Card className="relative overflow-hidden border border-bg-tertiary/50 bg-gradient-to-br from-bg-tertiary/5 to-transparent">
            <div className="absolute -right-8 -top-8 w-20 h-20 bg-text-secondary/5 rounded-full blur-2xl"></div>
            <div className="relative space-y-2">
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-bg-tertiary/20">
                  <AlertCircle size={20} className="text-text-secondary" />
                </div>
                <div>
                  <p className="text-xs uppercase text-text-secondary font-semibold">Monitoring Status</p>
                </div>
              </div>
              <div className="space-y-1.5 ml-0">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-text-secondary/50 rounded-full"></div>
                  <span className="text-lg font-bold text-text-secondary">IDLE</span>
                </div>
                <p className="text-xs text-text-secondary font-medium pl-4">No instruments configured</p>
                <div className="flex items-start gap-2 mt-2 pt-2 border-t border-bg-tertiary/30 pl-4">
                  <Clock size={14} className="text-text-secondary mt-0.5 flex-shrink-0" />
                  <div className="text-xs">
                    <p className="text-text-secondary font-semibold uppercase tracking-wide">Last Candle</p>
                    <p className="text-text-primary font-mono font-bold mt-1">—</p>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        ) : isMarketOpen() ? (
          <Card className="relative overflow-hidden border border-accent-green/30 bg-gradient-to-br from-accent-green/5 to-transparent">
            <div className="absolute -right-8 -top-8 w-20 h-20 bg-accent-green/10 rounded-full blur-2xl"></div>
            <div className="relative space-y-2">
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-accent-green/20">
                  <div className="w-3 h-3 bg-accent-green rounded-full animate-pulse"></div>
                </div>
                <div>
                  <p className="text-xs uppercase text-text-secondary font-semibold">Monitoring Status</p>
                </div>
              </div>
              <div className="space-y-1.5 ml-0">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-accent-green rounded-full animate-pulse"></div>
                  <span className="text-lg font-bold text-accent-green">ACTIVE</span>
                </div>
                <p className="text-xs text-accent-green font-medium pl-4">✓ Live polling active</p>
                <div className="flex items-start gap-2 mt-2 pt-2 border-t border-accent-green/20 pl-4">
                  <Clock size={14} className="text-text-secondary mt-0.5 flex-shrink-0" />
                  <div className="text-xs">
                    <p className="text-text-secondary font-semibold uppercase tracking-wide">Last Candle</p>
                    <p className="text-text-primary font-mono font-bold mt-1">{logs.length > 0 ? getLatestCandleTime() : '—'} IST</p>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        ) : (
          <Card className="relative overflow-hidden border border-accent-yellow/30 bg-gradient-to-br from-accent-yellow/5 to-transparent">
            <div className="absolute -right-8 -top-8 w-20 h-20 bg-accent-yellow/10 rounded-full blur-2xl"></div>
            <div className="relative space-y-4">
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-accent-yellow/20">
                  <Pause size={20} className="text-accent-yellow animate-pulse" />
                </div>
                <div>
                  <p className="text-xs uppercase text-text-secondary font-semibold">Monitoring Status</p>
                </div>
              </div>
              <div className="space-y-3 ml-0">
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-accent-yellow rounded-full animate-pulse"></div>
                  <span className="text-2xl font-bold text-accent-yellow">PAUSED</span>
                </div>
                <p className="text-xs text-text-secondary font-medium pl-4">Market closed</p>
                <div className="flex items-start gap-2 mt-3 pt-3 border-t border-accent-yellow/20 pl-4">
                  <Clock size={14} className="text-text-secondary mt-0.5 flex-shrink-0" />
                  <div className="text-xs">
                    <p className="text-text-secondary font-semibold uppercase tracking-wide">Next Open</p>
                    <p className="text-text-primary font-mono font-bold mt-1">09:00:00 AM IST</p>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        )}

        {/* Active Symbols Card - Only show when instruments are configured and during market hours */}
        {instruments.length === 0 ? (
          // No instruments state
          <Card className="relative overflow-hidden border border-bg-tertiary/50 bg-gradient-to-br from-bg-tertiary/5 to-transparent">
            <div className="absolute -right-8 -top-8 w-20 h-20 bg-text-secondary/5 rounded-full blur-2xl"></div>
            <div className="relative space-y-4">
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-bg-tertiary/20">
                  <TrendingUp size={20} className="text-text-secondary" />
                </div>
                <div>
                  <p className="text-xs uppercase text-text-secondary font-semibold">Active Symbols</p>
                </div>
              </div>
              <div className="space-y-2 ml-0">
                <div className="space-y-1.5 pl-4">
                  <p className="text-sm text-text-secondary">No instruments</p>
                  <p className="text-xs text-text-tertiary">Configure instruments to enable monitoring</p>
                </div>
              </div>
            </div>
          </Card>
        ) : isMarketOpen() ? (
          <Card className="relative overflow-hidden border border-accent-cyan/30 bg-gradient-to-br from-accent-cyan/5 to-transparent">
            <div className="absolute -right-8 -top-8 w-20 h-20 bg-accent-cyan/10 rounded-full blur-2xl"></div>
            <div className="relative space-y-2">
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-accent-cyan/20">
                  <TrendingUp size={20} className="text-accent-cyan" />
                </div>
                <div>
                  <p className="text-xs uppercase text-text-secondary font-semibold">Active Symbols</p>
                </div>
              </div>
              <div className="space-y-1.5 ml-0">
                {getActiveSymbols().length > 0 ? (
                  getActiveSymbols().map((symbol, idx) => (
                    <div key={idx} className="space-y-1.5 pl-4">
                      <div>
                        <p className="text-sm text-text-primary font-bold">{symbol.name}</p>
                        <p className="text-xs text-text-tertiary">{symbol.strategy}</p>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <div className="w-1.5 h-1.5 rounded-full bg-accent-cyan"></div>
                        <p className="text-xs text-text-secondary">Strike: {symbol.strike}</p>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <div className="w-1.5 h-1.5 rounded-full bg-accent-cyan"></div>
                        <p className="text-xs text-text-secondary">Premium: {symbol.premium}</p>
                      </div>
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {symbol.directions.includes('CE') && (
                          <span className="px-2 py-1 text-xs rounded bg-accent-cyan/10 text-accent-cyan font-medium">CE</span>
                        )}
                        {symbol.directions.includes('PE') && (
                          <span className="px-2 py-1 text-xs rounded bg-accent-red/10 text-accent-red font-medium">PE</span>
                        )}
                      </div>
                      {idx < getActiveSymbols().length - 1 && (
                        <div className="mt-3 pt-3 border-t border-bg-tertiary/30"></div>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="space-y-1.5 pl-4">
                    <p className="text-sm text-text-secondary">No active symbols</p>
                    <p className="text-xs text-text-tertiary">Waiting for signals...</p>
                  </div>
                )}
              </div>
            </div>
          </Card>
        ) : (
          <Card className="relative overflow-hidden border border-bg-tertiary/50 bg-gradient-to-br from-bg-tertiary/5 to-transparent">
            <div className="absolute -right-8 -top-8 w-20 h-20 bg-text-secondary/5 rounded-full blur-2xl"></div>
            <div className="relative space-y-4">
              <div className="flex items-center gap-3">
                <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-bg-tertiary/20">
                  <TrendingUp size={20} className="text-text-secondary" />
                </div>
                <div>
                  <p className="text-xs uppercase text-text-secondary font-semibold">Active Symbols</p>
                </div>
              </div>
              <div className="space-y-2 ml-0">
                <div className="space-y-1.5 pl-4">
                  <p className="text-sm text-text-secondary">No active symbols</p>
                  <p className="text-xs text-text-secondary/60">Market is closed</p>
                </div>
              </div>
            </div>
          </Card>
        )}

        {/* Market Phase Card */}
        <Card className="relative overflow-hidden border border-accent-yellow/30 bg-gradient-to-br from-accent-yellow/5 to-transparent">
          <div className="absolute -right-8 -top-8 w-20 h-20 bg-accent-yellow/10 rounded-full blur-2xl"></div>
          <div className="relative space-y-4">
            <div className="flex items-center gap-3">
              <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-accent-yellow/20">
                <Clock size={20} className="text-accent-yellow" />
              </div>
              <div>
                <p className="text-xs uppercase text-text-secondary font-semibold">Market Phase</p>
              </div>
            </div>
            <div className="ml-0 pt-2">
              {isMarketOpen() ? (
                <>
                  <div className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-accent-green/10 border border-accent-green/50">
                    <div className="w-2 h-2 bg-accent-green rounded-full animate-pulse"></div>
                    <span className="text-sm font-bold text-accent-green">In-Market</span>
                  </div>
                  <p className="text-xs text-text-secondary mt-3 text-center">Trading active</p>
                </>
              ) : (
                <>
                  <div className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg bg-accent-yellow/10 border border-accent-yellow/50">
                    <div className="w-2 h-2 bg-accent-yellow rounded-full"></div>
                    <span className="text-sm font-bold text-accent-yellow">After-Market</span>
                  </div>
                  <p className="text-xs text-text-secondary mt-3 text-center">Market closed</p>
                </>
              )}
            </div>
          </div>
        </Card>
      </div>

      {/* ACTIVE LOGS SECTION - CE/PE Columns with 3-minute Data - Reference Layout */}
      <div className="space-y-4">
        {/* Header with Export Button */}
        <div className="flex items-center justify-between">
          <SectionTitle subtitle="Real-time 3-minute candle data by strategy and side">
            Active Logs
          </SectionTitle>
          <button
            onClick={export3MinuteLogsToCSV}
            disabled={logs.filter((l) => l.message.toLowerCase().includes('setup') || l.message.toLowerCase().includes('candle')).length === 0}
            className={clsx(
              'flex items-center gap-2 px-4 py-2 rounded-lg font-semibold text-sm transition-all',
              logs.filter((l) => l.message.toLowerCase().includes('setup') || l.message.toLowerCase().includes('candle')).length === 0
                ? 'bg-bg-tertiary/50 text-text-secondary cursor-not-allowed'
                : 'bg-accent-cyan/20 text-accent-cyan hover:bg-accent-cyan/30 cursor-pointer'
            )}
            title="Download all 3-minute logs from section start"
          >
            <Download size={16} />
            Export 3-Min Logs
          </button>
        </div>

        {/* Strategy Sections - Always show CE/PE blocks */}
        {(() => {
          const strategies = getActiveStrategies().length > 0 ? getActiveStrategies() : ['ema21']
          
          return strategies.map((strategy) => {
            const ceLogs = getThreeMinuteLogs(strategy, 'CE')
            const peLogs = getThreeMinuteLogs(strategy, 'PE')
            const historyLogs = get3MinuteCandleHistory(ceLogs)
            const historyLogsP = get3MinuteCandleHistory(peLogs)

            return (
              <div key={strategy} className="space-y-3">
                {/* Meta info: Row count and order */}
                <div className="text-xs text-text-secondary font-semibold">
                  {ceLogs.length} CE rows | {peLogs.length} PE rows | newest events first
                </div>

                {/* CE/PE Columns Layout - Side by Side */}
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {/* CE Column */}
                  <div className="space-y-3 border border-accent-cyan/40 rounded-lg p-4 bg-gradient-to-br from-accent-cyan/5 to-bg-secondary/30">
                    {/* Column Header */}
                    <div className="flex items-center justify-between pb-3 border-b border-accent-cyan/30">
                      <div className="flex items-center gap-2">
                        <div className="w-3 h-3 bg-accent-cyan rounded-full"></div>
                        <h4 className="text-sm font-bold text-accent-cyan">CE · Call option</h4>
                      </div>
                      <div className="text-xs text-text-tertiary font-semibold">{Math.min(ceLogs.length, 60)} latest rows</div>
                    </div>

                    {!isMarketOpen() ? (
                      <div className="text-center py-12">
                        <AlertCircle size={32} className="mx-auto mb-3 text-accent-cyan/50" />
                        <p className="text-sm font-semibold text-accent-cyan mb-1">Waiting for Market Open</p>
                        <p className="text-xs text-text-tertiary">Signals will appear here during market hours (9 AM - 3:30 PM IST)</p>
                      </div>
                    ) : ceLogs.length > 0 ? (
                      <div className="space-y-3">
                        {/* Current setup */}
                        {getCurrentSetup(ceLogs) && (
                          <div className="space-y-2">
                            <p className="text-xs font-bold text-accent-cyan uppercase tracking-wider">Current setup</p>
                            <div className="text-xs space-y-1 px-3 py-2 bg-bg-secondary/50 rounded border border-accent-cyan/30 font-mono text-text-primary">
                              <p>{getCurrentSetup(ceLogs)?.message}</p>
                            </div>
                          </div>
                        )}

                        {/* Previous setup event */}
                        {getPreviousSetup(ceLogs) && (
                          <div className="space-y-2">
                            <p className="text-xs font-bold text-text-secondary uppercase tracking-wider">Previous setup event</p>
                            <p className="text-xs text-text-tertiary">Time: {formatTime(getPreviousSetup(ceLogs)?.timestamp || '')}</p>
                            <div className="text-xs space-y-1 px-3 py-2 bg-bg-secondary/50 rounded border border-accent-cyan/30 font-mono text-text-primary">
                              <p>{getPreviousSetup(ceLogs)?.message}</p>
                            </div>
                          </div>
                        )}

                        {/* Completed 3-minute candles */}
                        <div className="space-y-2">
                          <p className="text-xs font-bold text-text-secondary uppercase tracking-wider">Completed 3-minute candles</p>
                          {historyLogs.length > 0 ? (
                            <div className="bg-bg-secondary/30 rounded border border-accent-cyan/30 overflow-hidden">
                              {/* Table Header */}
                              <div className="grid grid-cols-3 gap-3 px-3 py-2 bg-bg-secondary/50 border-b border-accent-cyan/30 font-bold text-text-secondary text-xs sticky top-0">
                                <div>Time</div>
                                <div>Level</div>
                                <div>Message</div>
                              </div>
                              {/* Table Body - Max 60 rows */}
                              <div className="max-h-96 overflow-y-auto">
                                {historyLogs.slice(0, 60).map((log, idx) => (
                                  <div key={idx} className="grid grid-cols-3 gap-3 px-3 py-2 border-b border-accent-cyan/10 text-xs text-text-secondary hover:bg-bg-secondary/20 transition-colors">
                                    <div className="font-mono text-text-tertiary">{formatTime(log.timestamp)}</div>
                                    <div>
                                      <Badge size="xs" variant={getLevelColor(log.level)}>
                                        {log.level}
                                      </Badge>
                                    </div>
                                    <div className="text-text-primary break-words" title={log.message}>{log.message}</div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ) : (
                            <p className="text-xs text-text-tertiary italic px-3 py-2">No completed 3-minute candles yet.</p>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="text-center py-8">
                        <p className="text-xs text-text-tertiary">No Active Logs</p>
                      </div>
                    )}
                  </div>

                  {/* PE Column */}
                  <div className="space-y-3 border border-accent-red/40 rounded-lg p-4 bg-gradient-to-br from-accent-red/5 to-bg-secondary/30">
                    {/* Column Header */}
                    <div className="flex items-center justify-between pb-3 border-b border-accent-red/30">
                      <div className="flex items-center gap-2">
                        <div className="w-3 h-3 bg-accent-red rounded-full"></div>
                        <h4 className="text-sm font-bold text-accent-red">PE · Put option</h4>
                      </div>
                      <div className="text-xs text-text-tertiary font-semibold">{Math.min(peLogs.length, 60)} latest rows</div>
                    </div>

                    {!isMarketOpen() ? (
                      <div className="text-center py-12">
                        <AlertCircle size={32} className="mx-auto mb-3 text-accent-red/50" />
                        <p className="text-sm font-semibold text-accent-red mb-1">Waiting for Market Open</p>
                        <p className="text-xs text-text-tertiary">Signals will appear here during market hours (9 AM - 3:30 PM IST)</p>
                      </div>
                    ) : peLogs.length > 0 ? (
                      <div className="space-y-3">
                        {/* Current setup */}
                        {getCurrentSetup(peLogs) && (
                          <div className="space-y-2">
                            <p className="text-xs font-bold text-accent-red uppercase tracking-wider">Current setup</p>
                            <div className="text-xs space-y-1 px-3 py-2 bg-bg-secondary/50 rounded border border-accent-red/30 font-mono text-text-primary">
                              <p>{getCurrentSetup(peLogs)?.message}</p>
                            </div>
                          </div>
                        )}

                        {/* Previous setup event */}
                        {getPreviousSetup(peLogs) && (
                          <div className="space-y-2">
                            <p className="text-xs font-bold text-text-secondary uppercase tracking-wider">Previous setup event</p>
                            <p className="text-xs text-text-tertiary">Time: {formatTime(getPreviousSetup(peLogs)?.timestamp || '')}</p>
                            <div className="text-xs space-y-1 px-3 py-2 bg-bg-secondary/50 rounded border border-accent-red/30 font-mono text-text-primary">
                              <p>{getPreviousSetup(peLogs)?.message}</p>
                            </div>
                          </div>
                        )}

                        {/* Completed 3-minute candles */}
                        <div className="space-y-2">
                          <p className="text-xs font-bold text-text-secondary uppercase tracking-wider">Completed 3-minute candles</p>
                          {historyLogsP.length > 0 ? (
                            <div className="bg-bg-secondary/30 rounded border border-accent-red/30 overflow-hidden">
                              {/* Table Header */}
                              <div className="grid grid-cols-3 gap-3 px-3 py-2 bg-bg-secondary/50 border-b border-accent-red/30 font-bold text-text-secondary text-xs sticky top-0">
                                <div>Time</div>
                                <div>Level</div>
                                <div>Message</div>
                              </div>
                              {/* Table Body - Max 60 rows */}
                              <div className="max-h-96 overflow-y-auto">
                                {historyLogsP.slice(0, 60).map((log, idx) => (
                                  <div key={idx} className="grid grid-cols-3 gap-3 px-3 py-2 border-b border-accent-red/10 text-xs text-text-secondary hover:bg-bg-secondary/20 transition-colors">
                                    <div className="font-mono text-text-tertiary">{formatTime(log.timestamp)}</div>
                                    <div>
                                      <Badge size="xs" variant={getLevelColor(log.level)}>
                                        {log.level}
                                      </Badge>
                                    </div>
                                    <div className="text-text-primary break-words" title={log.message}>{log.message}</div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ) : (
                            <p className="text-xs text-text-tertiary italic px-3 py-2">No completed 3-minute candles yet.</p>
                          )}
                        </div>
                      </div>
                    ) : (
                      <div className="text-center py-8">
                        <p className="text-xs text-text-tertiary">No Active Logs</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })
        })()}
      </div>

      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      {/* Triggered Alerts Section - Shows rule-triggered strategy events */}
      {/* ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <SectionTitle title="Triggered Alerts" icon={<AlertTriangle size={20} />} />
          {alerts.length > 0 && (
            <div className="flex items-center gap-2">
              <button
                onClick={exportAlertsToCSV}
                className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-white/70 hover:text-white bg-bg-tertiary/50 hover:bg-bg-tertiary/80 rounded transition-all"
              >
                <Download size={14} />
                Export
              </button>
              <button
                onClick={resetAlerts}
                className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-white/70 hover:text-white bg-bg-tertiary/50 hover:bg-bg-tertiary/80 rounded transition-all hover:bg-red-900/30"
              >
                <RotateCcw size={14} />
                Reset
              </button>
            </div>
          )}
        </div>

        <Card className="border border-bg-tertiary/50">
          {alerts.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-bg-tertiary/50 bg-bg-tertiary/30">
                    <th className="px-4 py-2 text-left font-semibold text-text-secondary">Time</th>
                    <th className="px-4 py-2 text-left font-semibold text-text-secondary">Strategy</th>
                    <th className="px-4 py-2 text-left font-semibold text-text-secondary">Symbol</th>
                    <th className="px-4 py-2 text-left font-semibold text-text-secondary">Type</th>
                    <th className="px-4 py-2 text-left font-semibold text-text-secondary">Message</th>
                    <th className="px-4 py-2 text-center font-semibold text-text-secondary">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {alerts.map((alert) => (
                    <tr key={alert.id} className="border-b border-bg-tertiary/30 hover:bg-bg-tertiary/20 transition-colors">
                      <td className="px-4 py-2 text-text-secondary">
                        {formatTime(alert.timestamp)}
                      </td>
                      <td className="px-4 py-2">
                        <Badge variant="default">{alert.strategy}</Badge>
                      </td>
                      <td className="px-4 py-2 text-text-primary font-semibold">
                        {alert.symbol}
                      </td>
                      <td className="px-4 py-2 text-text-tertiary">
                        {alert.alert_type.replace(/_/g, ' ').toUpperCase()}
                      </td>
                      <td className="px-4 py-2 text-text-primary max-w-xs truncate">
                        {alert.message}
                      </td>
                      <td className="px-4 py-2 text-center">
                        <Badge 
                          variant={alert.status === 'PENDING' ? 'warning' : 'success'}
                        >
                          {alert.status}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center py-8">
              <p className="text-xs text-text-tertiary italic">No triggered alerts yet.</p>
              <p className="text-xs text-text-tertiary/70 mt-2">Alerts will appear here when strategy rules are triggered.</p>
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

export default Logs
