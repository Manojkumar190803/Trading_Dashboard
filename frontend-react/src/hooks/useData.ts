import { useEffect, useCallback, useState } from 'react'
import { fetchAndParseCSV, getTodayDateString, watchFile } from '@/utils/files'
import { parseCSV } from '@/utils/format'
import { StrategyAlert, Trade, EquityCurvePoint } from '@/types'

/**
 * Hook to fetch strategy alerts from daily CSV
 */
export const useStrategyAlerts = (shouldWatch = true) => {
  const [alerts, setAlerts] = useState<StrategyAlert[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchAlerts = useCallback(async () => {
    try {
      setIsLoading(true)
      setError(null)
      const today = getTodayDateString()
      const fileName = `trade_alerts_${today}.csv`

      try {
        const rows = await fetchAndParseCSV(fileName)
        const parsed = rows
          .filter((row) => row.category && row.message)
          .map((row) => ({
            timestamp: row.timestamp || '',
            category: row.category as StrategyAlert['category'],
            message: row.message || '',
            strategy: row.strategy || '',
            symbol: row.symbol || '',
          }))
          .reverse() // Most recent first

        setAlerts(parsed)
      } catch (err) {
        console.debug(`No alerts file found for today`)
        setAlerts([])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch alerts')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchAlerts()

    // Watch for changes if enabled
    if (shouldWatch) {
      const today = getTodayDateString()
      const fileName = `trade_alerts_${today}.csv`
      let unwatch: (() => void) | null = null

      try {
        unwatch = watchFile(
          fileName,
          async (content) => {
            const rows = await parseCSV(content)
            const parsed = rows
              .filter((row) => row.category && row.message)
              .map((row) => ({
                timestamp: row.timestamp || '',
                category: row.category as StrategyAlert['category'],
                message: row.message || '',
                strategy: row.strategy || '',
                symbol: row.symbol || '',
              }))
              .reverse()
            setAlerts(parsed)
          },
          2000 // Check every 2 seconds
        )
      } catch (err) {
        console.debug(`Cannot watch alerts file:`, err)
      }

      return () => {
        if (unwatch) unwatch()
      }
    }
  }, [fetchAlerts, shouldWatch])

  return { alerts, isLoading, error, refetch: fetchAlerts }
}

/**
 * Hook to fetch analytics trades
 */
export const useAnalyticsTrades = () => {
  const [trades, setTrades] = useState<Trade[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchTrades = useCallback(async () => {
    try {
      setIsLoading(true)
      setError(null)

      try {
        const rows = await fetchAndParseCSV('analytics_trades.csv')
        const parsed = rows
          .filter((row) => row.timestamp && row.pnl)
          .map((row) => ({
            timestamp: row.timestamp || '',
            strategy: row.strategy || '',
            pnl: parseFloat(row.pnl) || 0,
            source: row.source || '',
            message: row.message || '',
          }))

        setTrades(parsed)
      } catch (err) {
        console.debug(`No analytics trades file found`)
        setTrades([])
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch trades')
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchTrades()

    // Poll for updates every 3 seconds
    const interval = setInterval(fetchTrades, 3000)
    return () => clearInterval(interval)
  }, [fetchTrades])

  return { trades, isLoading, error, refetch: fetchTrades }
}

/**
 * Hook to calculate analytics summary from trades
 */
export const useAnalyticsSummary = (trades: Trade[]) => {
  return {
    completed_trades: trades.length,
    gross_profit: trades.filter((t) => t.pnl > 0).reduce((sum, t) => sum + t.pnl, 0),
    gross_loss: Math.abs(
      trades.filter((t) => t.pnl < 0).reduce((sum, t) => sum + t.pnl, 0)
    ),
    winning_trades: trades.filter((t) => t.pnl > 0).length,
    expectancy: trades.length > 0 ? trades.reduce((sum, t) => sum + t.pnl, 0) / trades.length : 0,
    win_rate: trades.length > 0 ? (trades.filter((t) => t.pnl > 0).length / trades.length) * 100 : 0,
    profit_factor:
      trades.length > 0
        ? trades.filter((t) => t.pnl > 0).reduce((sum, t) => sum + t.pnl, 0) /
          (Math.abs(trades.filter((t) => t.pnl < 0).reduce((sum, t) => sum + t.pnl, 0)) || 1)
        : 0,
  }
}

/**
 * Hook to generate equity curve data
 */
export const useEquityCurve = (trades: Trade[]) => {
  const [curve, setCurve] = useState<EquityCurvePoint[]>([])

  useEffect(() => {
    let runningPnl = 0
    const newCurve = trades.map((trade) => {
      runningPnl += trade.pnl
      return {
        datetime: trade.timestamp,
        total_pnl: runningPnl,
      }
    })
    setCurve(newCurve)
  }, [trades])

  return curve
}

/**
 * Hook for polling live metrics
 */
export const useLiveMetrics = () => {
  const [lastUpdate, setLastUpdate] = useState<string>(new Date().toISOString())

  useEffect(() => {
    const interval = setInterval(() => {
      setLastUpdate(new Date().toISOString())
    }, 5000)

    return () => clearInterval(interval)
  }, [])

  return { lastUpdate }
}

/**
 * Hook to fetch real OpenAlgo account data
 */
export const useRealAccountData = (shouldFetch = true, interval = 1000) => {
  const [data, setData] = useState<{
    positions: any[]
    orders: any[]
    account: any
    mode?: 'live' | 'analyzer'
    engine_status?: string
  } | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    try {
      setIsLoading(true)
      // Add timestamp to bypass cache and always get fresh data
      const response = await fetch(`/logs/dashboard_data.json?t=${Date.now()}`)
      if (response.ok) {
        const accountData = await response.json()
        console.log('[useRealAccountData] Fetched data:', {
          mode: accountData.mode,
          availableMargin: accountData.account?.availableMargin,
          timestamp: new Date().toISOString()
        })
        // Store in localStorage for debugging
        window.localStorage.setItem('lastAccountData', JSON.stringify({
          mode: accountData.mode,
          availableMargin: accountData.account?.availableMargin,
          timestamp: new Date().toISOString()
        }))
        setData({
          positions: accountData.positions || [],
          orders: accountData.orders || [],
          account: accountData.account || {},
          mode: accountData.mode,
          engine_status: accountData.engine_status,
        })
        setError(null)
      } else {
        // File not found or error - clear data
        console.log('[useRealAccountData] Failed to fetch:', response.status)
        setData(null)
        setError(null) // Don't show error if file just doesn't exist
      }
    } catch (err) {
      console.log('[useRealAccountData] Error:', err)
      setData(null) // Clear data on error
      setError(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!shouldFetch) return

    fetchData()
    const timer = setInterval(fetchData, interval)
    return () => clearInterval(timer)
  }, [shouldFetch, interval, fetchData])

  return { data, isLoading, error, refetch: fetchData }
}

/**
 * Hook to fetch real Fyers wallet data (live mode)
 */
export const useRealWalletData = (shouldFetch = true, interval = 1000) => {
  const [wallet, setWallet] = useState<{
    available_balance: number
    used_margin: number
    available_margin: number
    pnl: number
  } | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const fetchWallet = useCallback(async () => {
    try {
      setIsLoading(true)
      // Add timestamp to bypass cache and always get fresh data
      const response = await fetch(`/logs/wallet_data.json?t=${Date.now()}`)
      if (response.ok) {
        const walletData = await response.json()
        setWallet({
          available_balance: parseFloat(walletData.available_balance || 0),
          used_margin: parseFloat(walletData.utilisedMargin || 0),
          available_margin: parseFloat(walletData.availableMargin || 0),
          pnl: parseFloat(walletData.pnl || 0),
        })
        setError(null)
      } else {
        // File not found or error - clear wallet
        setWallet(null)
        setError(null) // Don't show error if file just doesn't exist
      }
    } catch (err) {
      console.debug('Wallet data not available - live mode may be inactive')
      setWallet(null) // Clear wallet on error
      setError(null)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!shouldFetch) return

    fetchWallet()
    const timer = setInterval(fetchWallet, interval)
    return () => clearInterval(timer)
  }, [shouldFetch, interval, fetchWallet])

  return { wallet, isLoading, error, refetch: fetchWallet }
}
