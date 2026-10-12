import { useState, useEffect } from 'react'
import { TrendingUp, BarChart3, Activity, Zap } from 'lucide-react'
import clsx from 'clsx'
import {
  MetricCard,
} from '@/components/UI'
import { useRealAccountData, useRealWalletData } from '@/hooks'
import {
  formatCurrency,
  getStatusColor,
} from '@/utils/format'

const Dashboard: React.FC = () => {
  // Fetch real OpenAlgo data (analyzer mode) - poll every 1 second for live updates
  const { data: accountData, isLoading: accountLoading } = useRealAccountData(true, 1000)
  
  // Fetch real Fyers wallet data (live mode) - poll every 1 second for live updates
  const { wallet: walletData, isLoading: walletLoading } = useRealWalletData(true, 1000)
  
  const [mode, setMode] = useState<'analyzer' | 'live'>('analyzer')
  const [metrics, setMetrics] = useState({
    net_mtm: 0,
    available_margin: 50000,
    active_trades: 0,
    engine_status: 'Ready' as const,
  })

  // Detect mode based on available data - prioritize live over analyzer
  useEffect(() => {
    let newMode: 'analyzer' | 'live' = 'analyzer'
    
    // Priority: Live mode (wallet) > Analyzer mode (account) > Mock
    if (walletData) {
      newMode = 'live'
    } else if (accountData) {
      newMode = 'analyzer'
    }
    
    setMode(newMode)
    console.log(`[Mode] Switched to: ${newMode} (wallet=${!!walletData}, account=${!!accountData})`)
  }, [accountData, walletData])

  // Update metrics from real data when available
  useEffect(() => {
    if (mode === 'live' && walletData) {
      // Live mode: Use Fyers wallet data
      setMetrics({
        net_mtm: walletData.pnl,
        available_margin: walletData.available_balance,
        active_trades: 0, // Would need positions data
        engine_status: 'Ready',
      })
    } else if (accountData?.account) {
      // Analyzer mode: Use OpenAlgo account data
      const account = accountData.account
      const positions = accountData.positions || []
      const activeTrades = positions.filter((p: any) => parseFloat(p.qty || p.quantity || 0) !== 0).length
      
      setMetrics({
        // Try multiple field names for MTM (OpenAlgo may return different fields)
        net_mtm: parseFloat(account.mtm || account.pnl || account.m2munrealized || 0),
        // Try multiple field names for available margin
        available_margin: parseFloat(account.availableMargin || account.margin || account.available_margin || account.availablecash || 50000),
        active_trades: activeTrades,
        engine_status: 'Ready',
      })
    }
  }, [mode, accountData, walletData, accountLoading, walletLoading])

  const statusColor = getStatusColor(metrics.engine_status)
  const isProfit = metrics.net_mtm >= 0
  const mtmColor = isProfit ? 'green' : 'red'

  // Get current time for last sync display
  const lastSyncTime = new Date().toLocaleTimeString('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })

  return (
    <div className="space-y-8">
      {/* Hero Section with Clean Design */}
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs uppercase tracking-widest text-text-tertiary font-semibold mb-2">
              Live Control Room
            </p>
            <h1 className="text-4xl font-bold text-text-primary mb-2">Trading Dashboard</h1>
            <p className="text-text-secondary">
              Live overview of your trading account and market positions
            </p>
          </div>
          <div className="flex flex-col gap-3">
            {/* Engine Status */}
            <div className={clsx('flex items-center gap-3 px-4 py-2 rounded-lg border', statusColor.bg)}>
              <div className={clsx('w-3 h-3 rounded-full animate-pulse', statusColor.dot)} />
              <span className={clsx('font-semibold text-sm', statusColor.text)}>
                Engine: {metrics.engine_status}
              </span>
            </div>
          </div>
        </div>

        {/* Metrics Grid - Only 4 Essential Cards */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <MetricCard
            label="Net MTM (₹)"
            value={formatCurrency(metrics.net_mtm)}
            sublabel="Mark to Market"
            icon={<TrendingUp size={16} />}
            color={mtmColor}
            trend={isProfit ? 'up' : 'down'}
          />
          <MetricCard
            label="Available Margin"
            value={formatCurrency(metrics.available_margin)}
            sublabel="Buying Power"
            icon={<BarChart3 size={16} />}
            color="cyan"
          />
          <MetricCard
            label="Active Trades"
            value={metrics.active_trades}
            sublabel="Open Positions"
            icon={<Activity size={16} />}
            color="yellow"
          />
          <MetricCard
            label="Strategy"
            value="Active"
            sublabel="Ready for Trade"
            icon={<Zap size={16} />}
            color="green"
          />
        </div>

        {/* Sync Status Footer */}
        <div className="text-sm text-text-secondary">
          Live account syncing every 1s · Last updated: {lastSyncTime} IST
        </div>
      </div>
    </div>
  )
}

export default Dashboard
