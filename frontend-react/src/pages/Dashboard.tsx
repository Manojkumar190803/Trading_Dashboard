import { useState, useEffect } from 'react'
import { TrendingUp, BarChart3, Activity, Zap } from 'lucide-react'
import clsx from 'clsx'
import {
  MetricCard,
} from '@/components/UI'
import { useRealAccountData, useRealWalletData } from '@/hooks'
import {
  formatCurrency,
} from '@/utils/format'

const Dashboard: React.FC = () => {
  // Fetch real OpenAlgo data (analyzer mode) - poll every 1 second for live updates
  const { data: accountData, isLoading: accountLoading } = useRealAccountData(true, 1000)
  
  // Fetch real Fyers wallet data (live mode) - poll every 1 second for live updates
  const { wallet: walletData, isLoading: walletLoading } = useRealWalletData(true, 1000)
  
  const [metrics, setMetrics] = useState({
    net_mtm: 0,
    available_margin: 50000,
    active_trades: 0,
  })

  const [engineStatus, setEngineStatus] = useState<'active' | 'pause' | 'stopped'>('pause')

  // Update metrics from real data when available
  useEffect(() => {
    // Priority 1: Use OpenAlgo account data (works for both live and analyzer modes)
    if (accountData?.account) {
      const account = accountData.account
      const positions = accountData.positions || []
      const activeTrades = positions.filter((p: any) => parseFloat(p.qty || p.quantity || 0) !== 0).length
      
      // Extract margin with fallback chain for different OpenAlgo versions
      const margin = account.availableMargin || account.margin || account.available_margin || account.availablecash || 50000
      
      setMetrics({
        net_mtm: parseFloat(account.mtm || account.pnl || account.m2munrealized || 0),
        available_margin: parseFloat(margin),
        active_trades: activeTrades,
      })
      
      // Update engine status from accountData
      if (accountData?.engine_status) {
        setEngineStatus(accountData.engine_status as 'active' | 'pause' | 'stopped')
      }
      return
    }
    
    // Priority 2: Fallback to Fyers wallet data if available
    if (walletData) {
      setMetrics({
        net_mtm: walletData.pnl,
        available_margin: walletData.available_balance,
        active_trades: 0, // Would need positions data
      })
      return
    }
    
    // Keep default values if no data available
  }, [accountData, walletData])

  const isProfit = metrics.net_mtm >= 0
  const mtmColor = isProfit ? 'green' : 'red'

  // Get engine status color and label
  const getEngineStatusColor = () => {
    switch (engineStatus) {
      case 'active':
        return { color: 'emerald', label: 'Engine Active', statusText: 'RUNNING' }
      case 'pause':
        return { color: 'amber', label: 'Engine Paused', statusText: 'OFF MARKET' }
      case 'stopped':
        return { color: 'red', label: 'Engine Stopped', statusText: 'ERROR' }
      default:
        return { color: 'slate', label: 'Status Unknown', statusText: 'N/A' }
    }
  }

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

          {/* Engine Status Indicator */}
          <div className={clsx(
            'flex items-center gap-3 px-4 py-2.5 rounded-lg border-2 font-semibold text-sm',
            engineStatus === 'active' && 'bg-emerald-500/15 border-emerald-400 text-emerald-700',
            engineStatus === 'pause' && 'bg-amber-500/15 border-amber-400 text-amber-700',
            engineStatus === 'stopped' && 'bg-red-500/15 border-red-400 text-red-700',
          )}>
            <div className={clsx(
              'w-2.5 h-2.5 rounded-full',
              engineStatus === 'active' && 'bg-emerald-500 animate-pulse',
              engineStatus === 'pause' && 'bg-amber-500',
              engineStatus === 'stopped' && 'bg-red-500',
            )} />
            <div>
              <div className="text-xs uppercase tracking-widest font-semibold opacity-70">Engine</div>
              <div className="font-bold">{getEngineStatusColor().statusText}</div>
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
            label="Engine Status"
            value={getEngineStatusColor().statusText}
            sublabel={engineStatus === 'active' ? 'Ready for Trading' : engineStatus === 'pause' ? 'Waiting for Market' : 'Check Connection'}
            icon={<Zap size={16} />}
            color={getEngineStatusColor().color as 'emerald' | 'amber' | 'red' | 'cyan'}
          />
        </div>

        {/* Sync Status Footer */}
        <div className="text-sm text-text-secondary">
          Live account syncing every 1s · Engine status: {engineStatus.toUpperCase()} · Last updated: {lastSyncTime} IST
        </div>
      </div>
    </div>
  )
}

export default Dashboard
