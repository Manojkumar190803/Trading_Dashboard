import { useState, useEffect } from 'react'
import { AlertCircle, AlertTriangle, CheckCircle2, Info, Pause, TrendingUp, Clock, Download, RotateCcw, X } from 'lucide-react'
import {
  Card,
  SectionTitle,
  Badge,
} from '@/components/UI'
import { formatTime } from '@/utils/format'
import { useAppStore } from '@/stores'
import { useToast } from '@/components/Toast'
import { useInstruments } from '@/hooks/useInstruments'
import { clsx } from 'clsx'
import { isMarketOpen } from '@/utils/market-hours'
import Papa from 'papaparse'

interface LogEntry {
  id: string
  timestamp: string
  level: 'INFO' | 'SUCCESS' | 'WARNING' | 'ERROR'
  message: string
  category?: string
  strategy?: string
  details?: string
  type?: string
  setupName?: string
  instrument?: string
  setupStatus?: string
  candleTime?: string
  candleOhlc?: { open: string; high: string; low: string; close: string }
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

interface ActiveSymbol {
  name: string
  baseSymbol: string
  strike: string
  strategy: string
  hasCE: boolean
  hasPE: boolean
}

const Logs: React.FC = () => {
  const { logs: storeLogs, setLogs: setStoreLogs, setInstruments: setStoreInstruments } = useAppStore()
  const { instruments: apiInstruments } = useInstruments()
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [alerts, setAlerts] = useState<AlertEntry[]>([])
  const [dismissedAlertIds, setDismissedAlertIds] = useState<Set<string>>(new Set())
  const [previousLogCount, setPreviousLogCount] = useState(0)
  const [previousAlertCount, setPreviousAlertCount] = useState(0)
  const [isInitialLoad, setIsInitialLoad] = useState(true)
  const [lastToastTime, setLastToastTime] = useState<number>(Date.now())
  const toast = useToast()

  // Sync API instruments to Zustand store for other components to use
  useEffect(() => {
    if (apiInstruments.length > 0) {
      setStoreInstruments(apiInstruments)
    }
  }, [apiInstruments, setStoreInstruments])

  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  // TOAST NOTIFICATION SYSTEM FOR TRADING EVENTS
  // ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  // Detect and show toast for trading events
  useEffect(() => {
    // Skip toast triggers on initial load (when logs first sync from store)
    if (isInitialLoad) {
      setPreviousLogCount(logs.length)
      setIsInitialLoad(false)
      setLastToastTime(Date.now())
      return
    }

    // Only show toasts for new logs
    if (logs.length <= previousLogCount) return

    // Get new logs since last check
    const newLogs = logs.slice(previousLogCount)
    setPreviousLogCount(logs.length)

    // Only trigger toasts for logs that arrived within the last 60 seconds
    // This prevents replaying old logs when the file is reloaded
    const sixtySecondsAgo = Date.now() - 60000

    newLogs.forEach((log) => {
      // Skip logs that are older than 60 seconds (prevents replay of old logs)
      const logTime = new Date(log.timestamp).getTime()
      if (logTime < sixtySecondsAgo) return

      const messageUpper = log.message.toUpperCase()
      const timeStr = new Date(log.timestamp).toLocaleTimeString('en-IN')

      // 🚨 ALERT TRIGGERED
      if (messageUpper.includes('ALERT') || messageUpper.includes('TRIGGERED')) {
        const symbolMatch = log.message.match(/([A-Z]+\d+[A-Z]+\d+[CE|PE]{2})/)?.[0]
        const symbol = symbolMatch || 'Unknown'
        toast.addToast({
          type: 'warning',
          title: '🚨 Alert Triggered',
          message: `Alert for ${symbol} triggered at ${timeStr}`,
          duration: 8000,
        })
      }

      // 📍 ENTRY TRIGGERED / ENTRY FILLED
      if (messageUpper.includes('ENTRY') && (messageUpper.includes('FILLED') || messageUpper.includes('TRIGGERED'))) {
        const symbolMatch = log.message.match(/([A-Z]+\d+[A-Z]+\d+[CE|PE]{2})/)?.[0]
        const priceMatch = log.message.match(/₹?(\d+\.?\d*)/)?.[1]
        const qtyMatch = log.message.match(/(\d+)\s*(?:contracts|qty|quantity)/i)?.[1]
        
        const symbol = symbolMatch || 'Unknown'
        const price = priceMatch ? `₹${priceMatch}` : 'Market Price'
        const qty = qtyMatch || '1'
        
        toast.addToast({
          type: 'success',
          title: '📍 Entry Filled',
          message: `Entry for ${symbol} at ${price} (${qty} contracts)`,
          duration: 6000,
        })
      }

      // 🛑 STOP LOSS PLACED / SET
      if (messageUpper.includes('STOP') || messageUpper.includes('SL')) {
        if (!messageUpper.includes('TRAILING')) {
          const symbolMatch = log.message.match(/([A-Z]+\d+[A-Z]+\d+[CE|PE]{2})/)?.[0]
          const priceMatch = log.message.match(/(?:at|@)\s*₹?(\d+\.?\d*)/)?.[1]
          
          const symbol = symbolMatch || 'Unknown'
          const price = priceMatch ? `₹${priceMatch}` : 'Value'
          
          toast.addToast({
            type: 'info',
            title: '🛑 Stop Loss Placed',
            message: `SL placed at ${price} for ${symbol}`,
            duration: 5000,
          })
        }
      }

      // 📉 TRAILING STOP LOSS
      if (messageUpper.includes('TRAILING') && messageUpper.includes('SL')) {
        const oldPriceMatch = log.message.match(/from\s*₹?(\d+\.?\d*)/)?.[1]
        const newPriceMatch = log.message.match(/to\s*₹?(\d+\.?\d*)/)?.[1]
        
        const oldPrice = oldPriceMatch ? `₹${oldPriceMatch}` : 'Previous'
        const newPrice = newPriceMatch ? `₹${newPriceMatch}` : 'Updated'
        
        toast.addToast({
          type: 'info',
          title: '📉 Trailing SL Updated',
          message: `Trailing SL moved from ${oldPrice} to ${newPrice}`,
          duration: 4000,
        })
      }

      // ✅ POSITION CLOSED / TRADE CLOSED
      if ((messageUpper.includes('CLOSED') || messageUpper.includes('EXIT')) && 
          (messageUpper.includes('POSITION') || messageUpper.includes('TRADE'))) {
        const pnlMatch = log.message.match(/(?:P&L|PNL|P\&L)\s*[:-]?\s*₹?(-?\d+\.?\d*)/i)?.[1]
        const pnlNum = pnlMatch ? parseFloat(pnlMatch) : null
        
        const pnlStr = pnlNum !== null 
          ? (pnlNum >= 0 ? `✅ +₹${pnlNum}` : `❌ -₹${Math.abs(pnlNum)}`)
          : 'Closed'
        
        const toastType = pnlNum !== null && pnlNum >= 0 ? 'success' : 'error'
        
        toast.addToast({
          type: toastType,
          title: '✅ Position Closed',
          message: `Trade closed with P&L: ${pnlStr}`,
          duration: 7000,
        })
      }

      // 🔄 BREAKEVEN HIT
      if (messageUpper.includes('BREAKEVEN')) {
        const symbolMatch = log.message.match(/([A-Z]+\d+[A-Z]+\d+[CE|PE]{2})/)?.[0]
        const symbol = symbolMatch || 'Unknown'
        
        toast.addToast({
          type: 'success',
          title: '🔄 Breakeven Hit',
          message: `Position ${symbol} reached breakeven`,
          duration: 5000,
        })
      }

      // ⚠️ ERROR / EXECUTION ISSUES
      if (log.level === 'ERROR' || messageUpper.includes('FAILED') || messageUpper.includes('ERROR')) {
        toast.addToast({
          type: 'error',
          title: '⚠️ Execution Error',
          message: log.message,
          duration: 8000,
        })
      }
    })
  }, [logs, previousLogCount, isInitialLoad, toast])

  // Detect and show toast for alert events
  useEffect(() => {
    // Skip toast triggers on initial load
    if (isInitialLoad) {
      setPreviousAlertCount(alerts.length)
      return
    }

    // Only show toasts for new alerts
    if (alerts.length <= previousAlertCount) return

    // Get new alerts since last check
    const newAlerts = alerts.slice(previousAlertCount)
    setPreviousAlertCount(alerts.length)

    // Only trigger toasts for alerts that arrived within the last 60 seconds
    // This prevents replaying old alerts when the file is reloaded
    const sixtySecondsAgo = Date.now() - 60000

    newAlerts.forEach((alert) => {
      // Skip alerts older than 60 seconds (prevents replay of old alerts)
      const alertTime = new Date(alert.timestamp).getTime()
      if (alertTime < sixtySecondsAgo) return
      const timeStr = new Date(alert.timestamp).toLocaleTimeString('en-IN')
      
      // Map alert types to appropriate toast types
      const getAlertTypeInfo = (type: string): { title: string; toastType: 'warning' | 'success' | 'info' | 'error' } => {
        const typeUpper = type.toUpperCase()
        
        if (typeUpper.includes('ENTRY')) {
          return { title: '📍 Entry Alert', toastType: 'success' }
        } else if (typeUpper.includes('EXIT') || typeUpper.includes('CLOSE')) {
          return { title: '✅ Exit Alert', toastType: 'info' }
        } else if (typeUpper.includes('SL')) {
          return { title: '🛑 SL Alert', toastType: 'warning' }
        } else if (typeUpper.includes('TP')) {
          return { title: '🎯 Target Alert', toastType: 'success' }
        } else {
          return { title: '🚨 Trade Alert', toastType: 'warning' }
        }
      }

      const { title, toastType } = getAlertTypeInfo(alert.alert_type)

      toast.addToast({
        type: toastType,
        title,
        message: `${alert.symbol}: ${alert.message} at ${timeStr}`,
        duration: 6000,
      })
    })
  }, [alerts, previousAlertCount, isInitialLoad, toast])

  // Load logs from real signal log file - reads actual EMA21 strategy signals
  // Only load when instruments are configured
  useEffect(() => {
    // If no instruments configured, clear logs in local state
    if (apiInstruments.length === 0) {
      setStoreLogs([])
      setLogs([])
      setAlerts([])
      return
    }

    const loadLogsFromData = async () => {
      try {
        // Get today's date for monitoring file
        const today = new Date()
        const dateStr = today.toISOString().split('T')[0].replace(/-/g, '')
        // Backend is on host machine localhost:4000, accessible from host browser
        const monitoringFile = `http://localhost:4000/logs/monitoring_${dateStr}.csv?t=${Date.now()}`
        
        console.log('🔍 Fetching monitoring file:', monitoringFile)
        
        // Fetch monitoring data which contains real 3min candles
        const response = await fetch(monitoringFile)
        console.log('📡 Response status:', response.status, response.ok)
        
        if (!response.ok) {
          console.log('❌ File not found or error:', response.status)
          setStoreLogs([])
          return
        }

        const text = await response.text()
        console.log('📄 File size:', text.length, 'bytes')
        
        const parsed = Papa.parse<Record<string, string>>(text, { header: true, skipEmptyLines: true })
        console.log('📋 Monitoring rows:', parsed.data.length)

        const candleDataByKey = new Map<string, LogEntry['candleOhlc']>()
        parsed.data.forEach((row) => {
          if (row.category?.trim() !== 'DATA') return
          const candleMatch = row.message?.match(/3m candle\s+(\d{2}:\d{2}:\d{2})\s+O=([\d.]+)\s+H=([\d.]+)\s+L=([\d.]+)\s+C=([\d.]+)/i)
          const symbol = row.symbol?.trim()
          if (!candleMatch || !symbol) return
          candleDataByKey.set(`${symbol}|${candleMatch[1]}`, {
            open: candleMatch[2],
            high: candleMatch[3],
            low: candleMatch[4],
            close: candleMatch[5],
          })
        })

        const logs: LogEntry[] = parsed.data.flatMap((row, index) => {
          if (row.category?.trim() !== 'SETUP_STATUS' || !row.timestamp || !row.message) return []

          const parts = row.message.split('|').map((part) => part.trim())
          const setupName = parts[0] || 'EMA21 setup'
          const instrument = row.symbol?.trim() || parts[1] || ''
          const side = setupName.match(/^(CE|PE)\b/i)?.[1]?.toUpperCase()
          const strategy = setupName.match(/^(?:CE|PE)\s+(.+?)\s+setup$/i)?.[1] || 'EMA21'
          const parsedTimestamp = new Date(row.timestamp)
          if (Number.isNaN(parsedTimestamp.getTime())) return []
          const candleTime = row.message.match(/candle\s*=\s*(\d{2}:\d{2}:\d{2})/i)?.[1] || ''
          const setupOhlcMatch = row.message.match(/\bO=([\d.]+)\s+H=([\d.]+)\s+L=([\d.]+)\s+C=([\d.]+)/i)
          const setupOhlc = setupOhlcMatch
            ? {
                open: setupOhlcMatch[1],
                high: setupOhlcMatch[2],
                low: setupOhlcMatch[3],
                close: setupOhlcMatch[4],
              }
            : undefined

          return [{
            id: `setup-${index}-${row.timestamp}`,
            timestamp: parsedTimestamp.toISOString(),
            level: 'INFO' as const,
            category: row.category,
            message: row.message,
            strategy,
            type: side || 'SETUP',
            setupName,
            instrument,
            setupStatus: parts[2] || row.status?.trim() || 'WAITING',
            candleTime,
            candleOhlc: setupOhlc || candleDataByKey.get(`${instrument}|${candleTime}`),
          }]
        }).sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())
        
        console.log('✅ Parsed logs:', logs.length)
        setStoreLogs(logs)
      } catch (error) {
        console.error('❌ Error loading logs:', error)
        setStoreLogs([])
      }
    }
    
    // Load logs on mount and every 2 seconds for real-time updates
    loadLogsFromData()
    const interval = setInterval(loadLogsFromData, 2000)
    
    return () => clearInterval(interval)
  }, [setStoreLogs, apiInstruments])

  // Sync logs from store
  useEffect(() => {
    setLogs(storeLogs as any)
  }, [storeLogs])

  // Load triggered alerts from CSV file
  // Only load when instruments are configured
  useEffect(() => {
    // If no instruments configured, clear alerts
    if (apiInstruments.length === 0) {
      setAlerts([])
      return
    }

    const loadAlertsFromData = async () => {
      try {
        // Get today's date for trade alerts file
        const today = new Date()
        const dateStr = today.toISOString().split('T')[0].replace(/-/g, '')
        
        const persistedDismissedIds = new Set(dismissedAlertIds)
        try {
          const resetResponse = await fetch(`http://localhost:4000/api/alerts/reset-status?t=${Date.now()}`)
          if (resetResponse.ok) {
            const resetData = await resetResponse.json()
            for (const id of resetData.dismissedIds || []) persistedDismissedIds.add(id)
          }
        } catch (error) {
          console.warn('Unable to read triggered-alert reset marker:', error)
        }

        // Fetch alerts for all configured instruments (NIFTY, BANKNIFTY, etc.)
        const allAlerts: AlertEntry[] = []
        
        for (const instrument of apiInstruments) {
          // Backend is on host machine localhost:4000, accessible from host browser
          const alertsFile = `http://localhost:4000/logs/trade_alerts_${instrument.brokerSymbol}_${dateStr}.csv?t=${Date.now()}`
          
          console.log('🔍 Fetching alerts file:', alertsFile)
          
          try {
            // Fetch triggered alerts from EMA21 strategy CSV
            const response = await fetch(alertsFile)
            console.log('📡 Alerts response status:', response.status, response.ok, `for ${instrument.brokerSymbol}`)
            
            if (!response.ok) {
              console.log(`❌ Alerts file not found for ${instrument.brokerSymbol}:`, response.status)
              continue
            }

            const text = await response.text()
            console.log('📄 Alerts file size:', text.length, 'bytes', `for ${instrument.brokerSymbol}`)
            
            const rows = Papa.parse<Record<string, string>>(text, { header: true, skipEmptyLines: true }).data
            console.log('📋 Parsed alert rows:', rows.length, `for ${instrument.brokerSymbol}`)

            rows.forEach((row) => {
              const timestamp = row.timestamp?.trim()
              const message = row.message?.trim()
              if (!timestamp || !message) return

              const timestampWithZone = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(timestamp)
                ? timestamp
                : `${timestamp}+05:30`
              const parsedDate = new Date(timestampWithZone)
              if (Number.isNaN(parsedDate.getTime())) return

              const symbolMatch = message.match(/([A-Z]+\d+[A-Z]+\d+\d+(?:CE|PE))/)
              const symbol = row.symbol?.trim() || symbolMatch?.[1] || instrument.brokerSymbol
              const strategy = row.strategy?.replace('SignalProvider', '').trim() || instrument.strategy || 'EMA21'
              const alertType = row.category?.trim() || row.alert_type?.trim() ||
                (/entry|signal/i.test(message) ? 'ENTRY' : /exit|closed/i.test(message) ? 'EXIT' : 'ALERT')
              const sourceStatus = row.status?.trim().toUpperCase()
              const status = sourceStatus === 'ACTIVE' || sourceStatus === 'CLOSED'
                ? sourceStatus
                : /ENTRY|SIGNAL/i.test(alertType) ? 'ACTIVE' : 'CLOSED'
              const id = `alert_${timestamp}_${symbol}_${strategy}_${alertType}`

              allAlerts.push({
                id,
                timestamp: parsedDate.toISOString(),
                strategy,
                alert_type: alertType,
                message,
                symbol,
                status,
              })
            })
          } catch (err) {
            console.error(`❌ Error loading alerts for ${instrument.brokerSymbol}:`, err)
            // Continue to next instrument if one fails
            continue
          }
        }
        
        console.log('✅ Parsed all alerts:', allAlerts.length)
        // Sort alerts by timestamp in descending order (newest first)
        const sortedAlerts = [...allAlerts]
          .filter((alert) => !persistedDismissedIds.has(alert.id))
          .sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())
        setAlerts(sortedAlerts)
      } catch (error) {
        console.error('❌ Error loading alerts:', error)
        setAlerts([])
      }
    }
    
    // Load alerts on mount and every 2 seconds for real-time updates
    loadAlertsFromData()
    const interval = setInterval(loadAlertsFromData, 2000)
    
    return () => clearInterval(interval)
  }, [apiInstruments, dismissedAlertIds])

  const [filterLevel, setFilterLevel] = useState<LogEntry['level'] | 'ALL'>('ALL')
  const [filterStrategy, setFilterStrategy] = useState<string>('ALL')
  const [expandedLog, setExpandedLog] = useState<string | null>(null)

  // Helper function to check if market is currently open (9:00 AM to 3:30 PM IST)
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

  const parseOptionSymbol = (symbol: string) => {
    const match = symbol.match(/^([A-Z]+)(\d{1,2}[A-Z]{3}\d{2})(\d+)(CE|PE)$/i)
    return match
      ? {
          baseSymbol: match[1].toUpperCase(),
          expiry: match[2].toUpperCase(),
          strike: match[3],
          side: match[4].toUpperCase(),
        }
      : null
  }

  const getInstrumentVisual = (baseSymbol: string) => {
    if (baseSymbol === 'BANKNIFTY') {
      return {
        frame: 'border-accent-yellow/45 border-l-accent-yellow bg-accent-yellow/5',
        header: 'border-accent-yellow/30 bg-accent-yellow/10',
        badge: 'bg-accent-yellow/20 text-accent-yellow',
        name: 'text-accent-yellow',
      }
    }
    if (baseSymbol === 'NIFTY') {
      return {
        frame: 'border-accent-cyan/45 border-l-accent-cyan bg-accent-cyan/5',
        header: 'border-accent-cyan/30 bg-accent-cyan/10',
        badge: 'bg-accent-cyan/20 text-accent-cyan',
        name: 'text-accent-cyan',
      }
    }
    return {
      frame: 'border-accent-green/45 border-l-accent-green bg-accent-green/5',
      header: 'border-accent-green/30 bg-accent-green/10',
      badge: 'bg-accent-green/20 text-accent-green',
      name: 'text-accent-green',
    }
  }

  const normalizeStrategy = (strategy: string): string => {
    const normalized = strategy.toUpperCase().replace(/[^A-Z0-9]/g, '')
    return normalized === '21EMA' ? 'EMA21' : normalized
  }

  const hasFreshLog = (log: LogEntry): boolean => {
    const ageMs = Date.now() - new Date(log.timestamp).getTime()
    return Number.isFinite(ageMs) && ageMs >= 0 && ageMs <= 10 * 60 * 1000
  }

  // Use configured active instruments as the source of truth; setup logs only supply their live ATM strike.
  const getActiveSymbols = (): ActiveSymbol[] => {
    return apiInstruments
      .filter((instrument) => instrument.status)
      .map((instrument) => {
        const configuredContract = parseOptionSymbol(instrument.brokerSymbol)
        const baseMatch = instrument.brokerSymbol.match(/^([A-Z]+)\d+/)
        const baseSymbol = configuredContract?.baseSymbol
          || (baseMatch ? baseMatch[1] : instrument.brokerSymbol.toUpperCase())
        const latestSetup = [...logs].reverse().find((log) => {
          const contract = parseOptionSymbol(log.instrument || '')
          return contract?.baseSymbol === baseSymbol
            && normalizeStrategy(log.strategy || '') === normalizeStrategy(instrument.strategy)
            && hasFreshLog(log)
        })
        const latestContract = latestSetup ? parseOptionSymbol(latestSetup.instrument || '') : null
        const strike = configuredContract?.strike
          || (instrument.premiumOptionStrike ? String(instrument.premiumOptionStrike) : undefined)
          || latestContract?.strike
          || '—'
        return {
          name: instrument.name,
          baseSymbol,
          strike,
          strategy: instrument.strategy,
          hasCE: true,
          hasPE: true,
        }
      })
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
    const activeBases = new Set(
      getActiveSymbols()
        .filter((instrument) => normalizeStrategy(instrument.strategy) === normalizeStrategy(strategy))
        .map((instrument) => instrument.baseSymbol)
    )
    return logs.filter((log) => {
      const contract = parseOptionSymbol(log.instrument || '')
      const isCorrectStrategy = normalizeStrategy(log.strategy || '') === normalizeStrategy(strategy)
      const hasCorrectSide = log.type === side
      const isActiveInstrument = contract !== null && activeBases.has(contract.baseSymbol)
      const is3MinuteLog = log.message.toLowerCase().includes('setup') || 
                           log.message.toLowerCase().includes('candle')
      return isCorrectStrategy && hasCorrectSide && isActiveInstrument && is3MinuteLog
    })
  }

  const getInstrumentSetups = (strategy: string, side: 'CE' | 'PE') => {
    return getActiveSymbols()
      .filter((instrument) => normalizeStrategy(instrument.strategy) === normalizeStrategy(strategy))
      .map((instrument) => {
        const matchingLogs = getThreeMinuteLogs(strategy, side).filter((log) => {
          const contract = parseOptionSymbol(log.instrument || '')
          return contract?.baseSymbol === instrument.baseSymbol
            && (instrument.strike === '—' || contract.strike === instrument.strike)
            && Boolean(log.candleOhlc)
            && hasFreshLog(log)
        })
        return {
          instrument,
          current: matchingLogs[matchingLogs.length - 1] || null,
          previous: matchingLogs.length > 1 ? matchingLogs[matchingLogs.length - 2] : null,
        }
      })
  }

  const getSetupFields = (log: LogEntry | null) => {
    if (!log) return null
    const parts = log.message.split('|').map((part) => part.trim())
    const symbol = log.instrument || parts[1] || ''
    const symbolMatch = symbol.match(/^([A-Z]+)(\d{1,2}[A-Z]{3}\d{2})(\d+)(CE|PE)$/)
    const instrument = symbolMatch
      ? `${symbolMatch[1]} ${symbolMatch[2]} ${symbolMatch[3]} ${symbolMatch[4]}`
      : symbol || '—'

    return {
      setupName: log.setupName || parts[0] || `${log.strategy || 'EMA21'} setup`,
      instrument,
      status: log.setupStatus || parts[2] || '—',
      candleTime: log.candleTime || log.message.match(/candle\s*=\s*(\d{2}:\d{2}:\d{2})/i)?.[1] || '—',
      candleOhlc: log.candleOhlc,
    }
  }

  const renderSetupFields = (
    log: LogEntry | null,
    accentClass: string,
    fallbackInstrument?: ActiveSymbol,
    fallbackSetupName = 'No candle data',
    fallbackSide?: 'CE' | 'PE'
  ) => {
    const contract = parseOptionSymbol(log?.instrument || '')
    const baseSymbol = contract?.baseSymbol || fallbackInstrument?.baseSymbol || 'INSTRUMENT'
    const strike = contract?.strike || fallbackInstrument?.strike || '—'
    const expiry = contract?.expiry
    const side = contract?.side || fallbackSide || ''
    const visual = getInstrumentVisual(baseSymbol)
    const fields = log
      ? getSetupFields(log)
      : fallbackInstrument
        ? {
            setupName: fallbackSetupName,
            instrument: `${baseSymbol} ${strike} ${fallbackSide || ''}`.trim(),
            status: '—',
            candleTime: '—',
            candleOhlc: undefined,
          }
        : null
    if (!fields) return null

    return (
      <dl className={`grid grid-cols-2 gap-x-3 gap-y-2 overflow-hidden rounded border border-l-4 px-3 py-2 text-xs ${accentClass} ${visual.frame}`}>
        <div className={`col-span-2 -mx-3 -mt-2 flex items-center justify-between gap-2 border-b px-3 py-2 ${visual.header}`}>
          <div className="flex min-w-0 items-center gap-2">
            <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${visual.badge}`}>
              INDEX
            </span>
            <span className={`truncate text-sm font-black ${visual.name}`}>{baseSymbol}</span>
          </div>
          <span className={`shrink-0 rounded px-2 py-1 font-mono text-xs font-bold ${visual.badge}`}>
            {expiry ? `${expiry} · ` : ''}{strike} {side}
          </span>
        </div>
        <div className="min-w-0">
          <dt className="text-text-tertiary">Setup</dt>
          <dd className="mt-0.5 break-words font-semibold text-text-primary">{fields.setupName}</dd>
        </div>
        <div>
          <dt className="text-text-tertiary">Status</dt>
          <dd className="mt-0.5 font-semibold text-text-primary">{fields.status}</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-text-tertiary">Candle time</dt>
          <dd className="mt-0.5 font-mono font-semibold text-text-primary">{fields.candleTime}</dd>
        </div>
        <div className="col-span-2 grid grid-cols-4 gap-2 border-t border-bg-tertiary/30 pt-2">
          {(['open', 'high', 'low', 'close'] as const).map((value) => (
            <div key={value}>
              <dt className="text-text-tertiary">{value.toUpperCase()}</dt>
              <dd className="mt-0.5 font-mono font-semibold text-text-primary">
                {fields.candleOhlc?.[value] || '—'}
              </dd>
            </div>
          ))}
        </div>
      </dl>
    )
  }

  // Get completed 3-minute candle history (all logs for this side)
  const get3MinuteCandleHistory = (logs: LogEntry[]): LogEntry[] => {
    // Return all logs sorted by timestamp (newest first - descending order)
    return [...logs].sort(
      (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
    )
  }

  // Get unique strategies that have 3-minute logs
  const getActiveStrategies = (): string[] => {
    return Array.from(new Set(getActiveSymbols().map((instrument) => instrument.strategy)))
  }

  const renderActiveInstrumentCards = () => getActiveSymbols().map((instrument) => {
    const visual = getInstrumentVisual(instrument.baseSymbol)
    return (
      <div
        key={instrument.baseSymbol}
        className={`rounded border border-l-4 px-3 py-2 ${visual.frame}`}
      >
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${visual.badge}`}>
              INDEX
            </span>
            <span className={`truncate text-sm font-black ${visual.name}`}>{instrument.baseSymbol}</span>
          </div>
          <span className="shrink-0 text-[10px] font-semibold uppercase text-text-tertiary">
            {instrument.strategy}
          </span>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <span className="text-[10px] font-semibold uppercase text-text-tertiary">ATM</span>
          <span className={`font-mono text-sm font-bold ${visual.name}`}>
            {instrument.strike === '—' ? 'Pending' : instrument.strike}
          </span>
          {instrument.hasCE && (
            <span className="rounded bg-accent-cyan/20 px-1.5 py-0.5 text-[10px] font-bold text-accent-cyan">CE</span>
          )}
          {instrument.hasPE && (
            <span className="rounded bg-accent-red/20 px-1.5 py-0.5 text-[10px] font-bold text-accent-red">PE</span>
          )}
        </div>
      </div>
    )
  })

  // Reset hides existing CSV alerts using a durable cutoff without deleting audit records.
  const resetAlerts = async () => {
    if (!confirm('Are you sure you want to clear all triggered alerts?')) {
      return
    }
    
    try {
      const idsToDismiss = Array.from(new Set([
        ...dismissedAlertIds,
        ...alerts.map((alert) => alert.id),
      ]))
      const response = await fetch('http://localhost:4000/api/alerts/reset', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ alertIds: idsToDismiss }),
      })
      
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      
      const data = await response.json()
      setDismissedAlertIds(new Set(data.dismissedIds || idsToDismiss))
      setAlerts([])
      setPreviousAlertCount(0)
      toast.clearAll()
      
      toast.addToast({
        type: 'success',
        title: '✅ Alerts Cleared',
        message: 'Existing alerts are hidden; new alerts will continue to appear',
        duration: 3000,
      })
      
      console.log('✅ Alerts cleared successfully')
    } catch (error) {
      console.error('Failed to reset alerts:', error)
      toast.addToast({
        type: 'error',
        title: '❌ Reset Failed',
        message: 'Failed to clear alerts. Please try again.',
        duration: 4000,
      })
    }
  }

  // Clear visible alert rows and toast messages for this page session.
  const clearAllMessages = () => {
    setDismissedAlertIds((current) => new Set([...current, ...alerts.map((alert) => alert.id)]))
    setAlerts([])
    setPreviousAlertCount(0)
    toast.clearAll()
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
        {apiInstruments.length === 0 ? (
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
                    <p className="text-text-primary font-mono font-bold mt-1">09:15:00 AM IST</p>
                  </div>
                </div>
              </div>
            </div>
          </Card>
        )}

        {/* Active Symbols Card - Only show when instruments are configured and during market hours */}
        {apiInstruments.length === 0 ? (
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
            <div className="relative space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-accent-cyan/20">
                    <TrendingUp size={20} className="text-accent-cyan" />
                  </div>
                  <p className="text-xs uppercase text-text-secondary font-semibold">Active Instruments</p>
                </div>
                <div className="text-right">
                  <p className="text-xs font-bold text-accent-green">{getActiveSymbols().length} monitored</p>
                  <p className="text-[10px] text-text-tertiary">Last: {getLatestCandleTime()}</p>
                </div>
              </div>
              <div className="grid grid-cols-1 gap-2 pl-4">
                {getActiveSymbols().length > 0 ? (
                  renderActiveInstrumentCards()
                ) : (
                  <div className="space-y-1">
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
            <div className="relative space-y-3">
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-bg-tertiary/20">
                    <TrendingUp size={20} className="text-text-secondary" />
                  </div>
                  <p className="text-xs uppercase text-text-secondary font-semibold">Active Instruments</p>
                </div>
                <p className="text-xs font-semibold text-text-tertiary">{getActiveSymbols().length} monitored</p>
              </div>
              <div className="grid grid-cols-1 gap-2 pl-4">
                {getActiveSymbols().length > 0 ? (
                  renderActiveInstrumentCards()
                ) : (
                  <div className="space-y-1">
                    <p className="text-sm text-text-secondary">No active symbols</p>
                    <p className="text-xs text-text-secondary/60">Market closed - resume monitoring at 9:15 AM IST</p>
                  </div>
                )}
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
            const ceInstrumentSetups = getInstrumentSetups(strategy, 'CE')
            const peInstrumentSetups = getInstrumentSetups(strategy, 'PE')
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
                      <div className="text-xs text-text-tertiary font-semibold">{Math.min(ceLogs.length, 25)} latest rows</div>
                    </div>

                    {!isMarketOpen() ? (
                      <div className="text-center py-12">
                        <AlertCircle size={32} className="mx-auto mb-3 text-accent-cyan/50" />
                        <p className="text-sm font-semibold text-accent-cyan mb-1">Waiting for Market Open</p>
                        <p className="text-xs text-text-tertiary">Signals will appear here during market hours (9:15 AM - 3:30 PM IST)</p>
                      </div>
                    ) : ceInstrumentSetups.length > 0 ? (
                      <div className="space-y-3">
                        {/* Current setup */}
                        <div className="space-y-2">
                          <p className="text-xs font-bold text-accent-cyan uppercase tracking-wider">Current setup</p>
                          {ceInstrumentSetups.map(({ instrument, current }) => (
                            <div key={instrument.baseSymbol}>
                              {renderSetupFields(
                                current,
                                'border-accent-cyan/30',
                                instrument,
                                'No candle data',
                                'CE'
                              )}
                            </div>
                          ))}
                        </div>

                        {/* Previous setup event */}
                        <div className="space-y-2">
                          <p className="text-xs font-bold text-text-secondary uppercase tracking-wider">Previous setup event</p>
                          {ceInstrumentSetups.map(({ instrument, previous }) => (
                            <div key={instrument.baseSymbol}>
                              {renderSetupFields(
                                previous,
                                'border-accent-cyan/30',
                                instrument,
                                'No previous candle',
                                'CE'
                              )}
                            </div>
                          ))}
                        </div>

                        {/* Completed 3-minute candles */}
                        <div className="space-y-2">
                          <p className="text-xs font-bold text-text-secondary uppercase tracking-wider">Completed 3-minute candles</p>
                          {historyLogs.length > 0 ? (
                            <div className="bg-bg-secondary/30 rounded border border-accent-cyan/30 overflow-hidden">
                              {/* Table Header */}
                              <div className="grid grid-cols-4 gap-2 px-3 py-2 bg-bg-secondary/50 border-b border-accent-cyan/30 font-bold text-text-secondary text-xs sticky top-0">
                                <div>Setup</div>
                                <div>Instrument</div>
                                <div>Status</div>
                                <div>Candle time</div>
                              </div>
                              {/* Table Body - Max 25 rows */}
                              <div className="max-h-96 overflow-y-auto">
                                {historyLogs.slice(0, 25).map((log, idx) => {
                                  const fields = getSetupFields(log)
                                  if (!fields) return null
                                  return (
                                    <div key={idx} className="grid grid-cols-4 gap-2 px-3 py-2 border-b border-accent-cyan/10 text-xs text-text-secondary hover:bg-bg-secondary/20 transition-colors">
                                      <div className="break-words text-text-primary">{fields.setupName}</div>
                                      <div className="break-words text-text-primary">{fields.instrument}</div>
                                      <div className="break-words">{fields.status}</div>
                                      <div className="font-mono">{fields.candleTime}</div>
                                    </div>
                                  )
                                })}
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
                      <div className="text-xs text-text-tertiary font-semibold">{Math.min(peLogs.length, 25)} latest rows</div>
                    </div>

                    {!isMarketOpen() ? (
                      <div className="text-center py-12">
                        <AlertCircle size={32} className="mx-auto mb-3 text-accent-red/50" />
                        <p className="text-sm font-semibold text-accent-red mb-1">Waiting for Market Open</p>
                        <p className="text-xs text-text-tertiary">Signals will appear here during market hours (9:15 AM - 3:30 PM IST)</p>
                      </div>
                    ) : peInstrumentSetups.length > 0 ? (
                      <div className="space-y-3">
                        {/* Current setup */}
                        <div className="space-y-2">
                          <p className="text-xs font-bold text-accent-red uppercase tracking-wider">Current setup</p>
                          {peInstrumentSetups.map(({ instrument, current }) => (
                            <div key={instrument.baseSymbol}>
                              {renderSetupFields(
                                current,
                                'border-accent-red/30',
                                instrument,
                                'No candle data',
                                'PE'
                              )}
                            </div>
                          ))}
                        </div>

                        {/* Previous setup event */}
                        <div className="space-y-2">
                          <p className="text-xs font-bold text-text-secondary uppercase tracking-wider">Previous setup event</p>
                          {peInstrumentSetups.map(({ instrument, previous }) => (
                            <div key={instrument.baseSymbol}>
                              {renderSetupFields(
                                previous,
                                'border-accent-red/30',
                                instrument,
                                'No previous candle',
                                'PE'
                              )}
                            </div>
                          ))}
                        </div>

                        {/* Completed 3-minute candles */}
                        <div className="space-y-2">
                          <p className="text-xs font-bold text-text-secondary uppercase tracking-wider">Completed 3-minute candles</p>
                          {historyLogsP.length > 0 ? (
                            <div className="bg-bg-secondary/30 rounded border border-accent-red/30 overflow-hidden">
                              {/* Table Header */}
                              <div className="grid grid-cols-4 gap-2 px-3 py-2 bg-bg-secondary/50 border-b border-accent-red/30 font-bold text-text-secondary text-xs sticky top-0">
                                <div>Setup</div>
                                <div>Instrument</div>
                                <div>Status</div>
                                <div>Candle time</div>
                              </div>
                              {/* Table Body - Max 25 rows */}
                              <div className="max-h-96 overflow-y-auto">
                                {historyLogsP.slice(0, 25).map((log, idx) => {
                                  const fields = getSetupFields(log)
                                  if (!fields) return null
                                  return (
                                    <div key={idx} className="grid grid-cols-4 gap-2 px-3 py-2 border-b border-accent-red/10 text-xs text-text-secondary hover:bg-bg-secondary/20 transition-colors">
                                      <div className="break-words text-text-primary">{fields.setupName}</div>
                                      <div className="break-words text-text-primary">{fields.instrument}</div>
                                      <div className="break-words">{fields.status}</div>
                                      <div className="font-mono">{fields.candleTime}</div>
                                    </div>
                                  )
                                })}
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
          <SectionTitle>
            <div className="flex items-center gap-2">
              <AlertTriangle size={20} className="text-accent-red" />
              Triggered Alerts
            </div>
          </SectionTitle>
          <div className="flex items-center gap-2">
            <button
              onClick={clearAllMessages}
              className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-accent-red/70 hover:text-accent-red bg-accent-red/10 hover:bg-accent-red/20 rounded transition-all"
              title="Clear visible alert rows and toast messages"
            >
              <X size={14} />
              Clear Messages
            </button>
            <button
              onClick={exportAlertsToCSV}
              disabled={alerts.length === 0}
              className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-white/70 hover:text-white bg-bg-tertiary/50 hover:bg-bg-tertiary/80 rounded transition-all disabled:cursor-not-allowed disabled:opacity-40"
            >
              <Download size={14} />
              Export
            </button>
            <button
              onClick={resetAlerts}
              className="flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-white/70 hover:text-white bg-bg-tertiary/50 hover:bg-bg-tertiary/80 rounded transition-all hover:bg-red-900/30"
              title="Hide existing triggered alerts without deleting CSV history"
            >
              <RotateCcw size={14} />
              Reset
            </button>
          </div>
        </div>

        <Card className="border border-bg-tertiary/50">
          {alerts.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[900px] table-fixed text-xs">
                <colgroup>
                  <col className="w-[12%]" />
                  <col className="w-[15%]" />
                  <col className="w-[16%]" />
                  <col className="w-[12%]" />
                  <col className="w-[35%]" />
                  <col className="w-[10%]" />
                </colgroup>
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
                  {[...alerts].sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()).map((alert) => (
                    <tr key={alert.id} className="border-b border-bg-tertiary/30 hover:bg-bg-tertiary/20 transition-colors">
                      <td className="px-4 py-2 text-text-secondary">
                        {formatTime(alert.timestamp)}
                      </td>
                      <td className="px-4 py-2">
                        <Badge variant="info">{alert.strategy}</Badge>
                      </td>
                      <td className="px-4 py-2 text-text-primary font-semibold">
                        {alert.symbol}
                      </td>
                      <td className="px-4 py-2 text-text-tertiary">
                        {alert.alert_type.replace(/_/g, ' ').toUpperCase()}
                      </td>
                      <td className="px-4 py-2 text-text-primary max-w-xl whitespace-normal break-words [overflow-wrap:anywhere]">
                        {alert.message}
                      </td>
                      <td className="px-4 py-2 text-center">
                        <span 
                          className={clsx(
                            'inline-block px-3 py-1 rounded-full text-xs font-bold border',
                            alert.status === 'ACTIVE' 
                              ? 'bg-green-500/20 text-green-400 border-green-500/50' 
                              : 'bg-red-500/20 text-red-400 border-red-500/50'
                          )}
                        >
                          {alert.status}
                        </span>
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
