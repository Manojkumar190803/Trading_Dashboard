import { TrendingUp, BarChart3, Activity, Zap } from 'lucide-react'
import clsx from 'clsx'
import {
  MetricCard,
} from '@/components/UI'
import { useRealAccountData } from '@/hooks'
import {
  formatCurrency,
  getStatusColor,
} from '@/utils/format'

const getAccountAmount = (account: Record<string, unknown>, keys: string[]): number => {
  for (const key of keys) {
    const value = account[key]
    if (value === null || value === undefined || value === '') continue
    const amount = Number(value)
    if (Number.isFinite(amount)) return amount
  }
  return 0
}

const getBrokerDisplayName = (brokerName: unknown): string => {
  if (typeof brokerName !== 'string' || !brokerName.trim()) return 'Broker unavailable'

  const broker = brokerName.trim().toLowerCase()
  const knownBrokerNames: Record<string, string> = {
    '5paisa': '5paisa',
    aliceblue: 'AliceBlue',
    angel: 'Angel One',
    angelone: 'Angel One',
    dhan: 'Dhan',
    fyers: 'Fyers',
    groww: 'Groww',
    kotak: 'Kotak',
    upstox: 'Upstox',
    zerodha: 'Zerodha',
  }

  return knownBrokerNames[broker] ?? broker.replace(/[_-]+/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
}

const Dashboard: React.FC = () => {
  const { data: accountData, isLoading: accountLoading, error: accountError } = useRealAccountData(true, 1000)
  const account = accountData?.account ?? {}
  const brokerName = getBrokerDisplayName(account.broker_name)
  const positions = accountData?.positions ?? []
  const metrics = {
    net_mtm: getAccountAmount(account, ['mtm', 'm2munrealized', 'pnl']),
    available_margin: getAccountAmount(account, [
      'availableMargin',
      'available_margin',
      'availablecash',
      'availableCash',
      'margin',
      'cash',
    ]),
    active_trades: positions.filter(
      (position: any) => Number(position.qty ?? position.quantity ?? 0) !== 0
    ).length,
    engine_status: accountError
      ? 'Unavailable'
      : accountData
        ? 'Ready'
        : accountLoading
          ? 'Connecting'
          : 'Unavailable',
  }

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
            sublabel={
              <span
                className="inline-flex items-center gap-1.5"
                aria-label={brokerName === 'Broker unavailable' ? brokerName : `Connected to ${brokerName}`}
                title={brokerName === 'Broker unavailable' ? brokerName : `Connected to ${brokerName}`}
              >
                <span
                  className={clsx(
                    'h-1.5 w-1.5 rounded-full',
                    brokerName === 'Broker unavailable' ? 'bg-text-tertiary' : 'bg-accent-green'
                  )}
                  aria-hidden="true"
                />
                {brokerName === 'Broker unavailable' ? brokerName : `Connected to ${brokerName}`}
              </span>
            }
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
