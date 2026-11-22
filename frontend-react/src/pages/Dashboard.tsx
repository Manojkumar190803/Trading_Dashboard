import { TrendingUp, BarChart3, Activity, Zap } from 'lucide-react'
import clsx from 'clsx'
import {
  MetricCard,
} from '@/components/UI'
import ExecutionModeBadge from '@/components/ExecutionModeBadge'
import { useRealAccountData, useTestTradingActivity } from '@/hooks'
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
  const { data: accountData, isLoading: accountLoading, error: accountError, lastUpdated } = useRealAccountData(true)
  const { data: testActivity } = useTestTradingActivity()
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

  return (
    <div className="space-y-8">
      {/* Hero Section with Clean Design */}
      <div className="space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
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
            label="Live Net MTM (₹)"
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
            label="Live Positions"
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
          {lastUpdated
            ? `Account data · Last update: ${new Date(lastUpdated).toLocaleTimeString('en-IN')}`
            : accountLoading
              ? 'Connecting to account data'
              : 'Account data unavailable'}
        </div>
      </div>

      <section className="space-y-4 border-t border-bg-tertiary pt-6">
        <div className="flex items-center gap-3">
          <ExecutionModeBadge mode="TEST" />
          <h2 className="text-lg font-semibold text-text-primary">Test Activity</h2>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
          <MetricCard
            label="Open Test Positions"
            value={testActivity.summary.open_positions}
            sublabel="Virtual positions"
            icon={<Activity size={16} />}
            color="yellow"
          />
          <MetricCard
            label="Test Open P&L"
            value={formatCurrency(testActivity.summary.open_pnl)}
            sublabel="Unrealized"
            icon={<TrendingUp size={16} />}
            color={testActivity.summary.open_pnl >= 0 ? 'green' : 'red'}
          />
          <MetricCard
            label="Test Realized P&L"
            value={formatCurrency(testActivity.summary.realized_pnl)}
            sublabel="Closed virtual trades"
            icon={<BarChart3 size={16} />}
            color={testActivity.summary.realized_pnl >= 0 ? 'green' : 'red'}
          />
          <MetricCard
            label="Test Trades"
            value={testActivity.summary.completed_trades}
            sublabel="Completed virtual trades"
            icon={<Zap size={16} />}
            color="cyan"
          />
        </div>
        <div className="divide-y divide-bg-tertiary rounded-md border border-bg-tertiary">
          {testActivity.alerts.length === 0 ? (
            <p className="px-4 py-3 text-sm text-text-secondary">No Test signals or events yet.</p>
          ) : testActivity.alerts.slice(0, 5).map((alert) => (
            <div key={alert.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
              <span className="font-mono text-xs text-text-tertiary">
                {new Date(alert.timestamp).toLocaleTimeString()}
              </span>
              <span className="rounded bg-amber-300 px-2 py-0.5 text-[10px] font-black text-black">TEST</span>
              <span className="text-xs font-semibold text-amber-300">{alert.category}</span>
              <span className="min-w-0 flex-1 text-sm text-text-primary">{alert.message}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  )
}

export default Dashboard
