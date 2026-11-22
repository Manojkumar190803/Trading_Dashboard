import { useState, useEffect, useMemo, memo } from 'react'
import { AlertCircle, TrendingUp, Activity, DollarSign, Target, Download, Clock3 } from 'lucide-react'
import {
  Card,
  SectionTitle,
  LoadingSpinner,
  EmptyState,
  Badge,
  MetricCard,
} from '@/components/UI'
import ExecutionModeBadge from '@/components/ExecutionModeBadge'
import { useCurrentTime, useRealAccountData, useTestTradingActivity } from '@/hooks'
import { formatCurrency, formatPercent, getValueColor } from '@/utils/format'
import { exportPositionsCSV } from '@/utils/csv-export'
import { clsx } from 'clsx'

const terminalOrderStatuses = new Set([
  'complete',
  'filled',
  'executed',
  'cancelled',
  'canceled',
  'rejected',
  'failed',
  'expired',
])

const getProtectiveStopPrice = (position: any, orders: any[]): number | null => {
  const quantity = Math.abs(parseFloat(position.quantity || position.qty || 0))
  const stopOrders = orders
    .filter((order) => {
      const type = String(order.pricetype || order.price_type || order.order_type || '')
        .toUpperCase()
        .replace(/[ _]/g, '-')
      const action = String(order.action || order.side || '').toUpperCase()
      const triggerPrice = Number(order.trigger_price ?? order.triggerPrice)
      return (
        order.symbol === position.symbol
        && action === 'SELL'
        && ['SL', 'SL-M', 'SLM', 'STOP', 'STOP-LOSS', 'STOPLOSS'].includes(type)
        && Number.isFinite(triggerPrice)
        && triggerPrice > 0
      )
    })
    .sort((left, right) => {
      const leftTime = String(left.timestamp || left.created_at || '')
      const rightTime = String(right.timestamp || right.created_at || '')
      return rightTime.localeCompare(leftTime)
    })

  const activeStopOrders = stopOrders.filter(
    (order) => !terminalOrderStatuses.has(String(order.order_status || order.status || '').toLowerCase())
  )
  const selectedOrder = quantity > 0
    ? activeStopOrders.find((order) => {
        const orderQuantity = Math.abs(parseFloat(order.quantity || 0))
        return orderQuantity === quantity
      }) || activeStopOrders[0]
    : stopOrders[0]
  const triggerPrice = Number(selectedOrder?.trigger_price ?? selectedOrder?.triggerPrice)

  return Number.isFinite(triggerPrice) && triggerPrice > 0 ? triggerPrice : null
}

// Custom comparison function for PositionTableRow
// Only re-render if actual position values change, not object reference
const arePositionPropsEqual = (prevProps: any, nextProps: any) => {
  const p = prevProps.position
  const n = nextProps.position
  
  return (
    p.id === n.id &&
    p.symbol === n.symbol &&
    p.entryPrice === n.entryPrice &&
    p.quantity === n.quantity &&
    p.currentPrice === n.currentPrice &&
    p.protectiveSL === n.protectiveSL &&
    p.pnl === n.pnl &&
    p.pnlPercent === n.pnlPercent
  )
}

// Memoized table row with custom comparison to prevent re-renders on identical data
const PositionTableRow = memo(
  ({ position }: { position: any }) => (
    <tr
      className={clsx(
        'border-b border-bg-tertiary transition-colors',
        position.pnl > 0
          ? 'bg-green-500/15 hover:bg-green-500/25'
          : 'bg-red-500/15 hover:bg-red-500/25'
      )}
    >
      <td className="px-6 py-4">
        <p className="font-mono font-bold text-text-primary">
          {position.symbol}
        </p>
      </td>
      <td className="px-6 py-4">
        <p className="font-mono text-text-primary">
          {formatCurrency(position.entryPrice)}
        </p>
      </td>
      <td className="px-6 py-4">
        <p className="font-mono text-text-primary">
          {formatCurrency(position.currentPrice)}
        </p>
      </td>
      <td className="px-6 py-4">
        <p className="font-mono font-semibold text-text-primary">
          {position.quantity}
        </p>
      </td>
      <td className="px-6 py-4">
        <p className="font-mono text-text-primary">
          {position.protectiveSL === null ? '—' : formatCurrency(position.protectiveSL, 2)}
        </p>
      </td>
      <td className="px-6 py-4">
        <div>
          <p
            className={clsx(
              'font-mono font-bold',
              position.pnl > 0
                ? 'text-green-400'
                : 'text-red-400'
            )}
          >
            {formatCurrency(position.pnl)}
          </p>
          <p
            className={clsx(
              'text-xs font-mono',
              position.pnl > 0
                ? 'text-green-400/70'
                : 'text-red-400/70'
            )}
          >
            {position.pnl > 0 ? '+' : ''}{formatPercent(position.pnlPercent)}
          </p>
        </div>
      </td>
      <td className="px-6 py-4">
        <Badge
          variant={position.pnl > 0 ? 'success' : 'danger'}
          size="sm"
        >
          {position.pnl > 0 ? 'PROFIT' : 'LOSS'}
        </Badge>
      </td>
    </tr>
  ),
  arePositionPropsEqual
)

PositionTableRow.displayName = 'PositionTableRow'

// Custom comparison for LiveTickCard
// Only re-render if actual tick values change
const areTickPropsEqual = (prevProps: any, nextProps: any) => {
  const p = prevProps.tick
  const n = nextProps.tick
  
  return (
    p.symbol === n.symbol &&
    p.price === n.price &&
    p.quantity === n.quantity
  )
}

// Memoized live tick card with custom comparison
const LiveTickCard = memo(
  ({ tick }: { tick: any }) => (
    <Card key={tick.symbol} className="border-emerald-500/30">
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <p className="font-mono font-bold text-text-primary text-sm">
            {tick.symbol}
          </p>
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-text-tertiary" />
            <span className="text-xs text-text-tertiary font-semibold">SNAPSHOT</span>
          </div>
        </div>
        <div className="border-t border-bg-tertiary pt-2">
          <p className="text-xs text-text-secondary mb-1">Current Price</p>
          <p className="font-mono text-lg font-bold text-text-primary">
            {formatCurrency(tick.price)}
          </p>
        </div>
        <div>
          <p className="text-xs text-text-secondary mb-1">Qty</p>
          <p className="font-mono text-text-primary">{tick.quantity}</p>
        </div>
        <div className="text-xs text-text-tertiary pt-2 border-t border-bg-tertiary">
          Updated: {new Date(tick.timestamp).toLocaleTimeString()}
        </div>
      </div>
    </Card>
  ),
  areTickPropsEqual
)

LiveTickCard.displayName = 'LiveTickCard'

const Positions: React.FC = () => {
  const { data: accountData, isLoading: dataLoading, lastUpdated } = useRealAccountData(true, {
    refreshInterval: 60000,
    subscribeToStream: false,
  })
  const { data: testActivity, isLoading: testLoading } = useTestTradingActivity()
  const currentTime = useCurrentTime()
  const [strategyStatus, setStrategyStatus] = useState<{
    available: boolean
    names: string[]
  } | null>(null)

  useEffect(() => {
    let isMounted = true

    const fetchStrategyStatus = async () => {
      try {
        const response = await fetch(`/logs/strategies_status.json?t=${Date.now()}`)
        if (!response.ok) throw new Error('Strategy status unavailable')

        const payload = await response.json()
        const entries = Object.values(payload.running_strategies || {}) as any[]
        const names = [...new Set(
          entries
            .filter((entry) => entry?.status?.toLowerCase() === 'running' && typeof entry.strategy === 'string')
            .map((entry) => entry.strategy.trim())
            .filter(Boolean)
        )]

        if (isMounted) setStrategyStatus({ available: true, names })
      } catch {
        if (isMounted) setStrategyStatus({ available: false, names: [] })
      }
    }

    void fetchStrategyStatus()
    const intervalId = window.setInterval(() => void fetchStrategyStatus(), 60000)
    return () => {
      isMounted = false
      window.clearInterval(intervalId)
    }
  }, [])

  const strategyLabel = strategyStatus === null
    ? 'Loading...'
    : !strategyStatus.available
      ? 'Unavailable'
      : strategyStatus.names.length === 0
        ? 'None'
        : strategyStatus.names.length === 1
          ? strategyStatus.names[0]
          : 'Multiple'
  const strategySublabel = strategyStatus === null
    ? 'Reading strategy status'
    : !strategyStatus.available
      ? 'Strategy status unavailable'
      : strategyStatus.names.length === 0
        ? 'No strategies running'
        : strategyStatus.names.length > 1
          ? strategyStatus.names.join(', ')
          : 'Running strategy'

  // Create a stable key from position data to only trigger updates when data actually changes
  const positionDataKey = useMemo(() => {
    if (!accountData?.positions) return 'empty'
    
    // Create a key from actual position data (symbol + quantity)
    // This only changes when positions actually change, not on every poll
    return accountData.positions
      .map((p: any) => `${p.symbol}:${p.quantity}:${p.pnl}`)
      .join('|')
  }, [accountData?.positions])

  const orderDataKey = useMemo(() => {
    if (!accountData?.orders) return 'empty'
    return accountData.orders
      .map((order: any) => [
        order.symbol,
        order.action,
        order.pricetype,
        order.order_status,
        order.trigger_price,
        order.quantity,
        order.timestamp,
      ].join(':'))
      .join('|')
  }, [accountData?.orders])

  // Memoize metrics and positions data - only update when position data actually changes
  const { metrics, triggeredPositions, liveTickFeed } = useMemo(() => {
    if (!accountData) {
      return {
        metrics: {
          openPositions: 0,
          totalPnL: 0,
          triggeredToday: 0,
        },
        triggeredPositions: [],
        liveTickFeed: [],
      }
    }

    const positions = accountData.positions || []
    const orders = accountData.orders || []

    const activePositions = positions.filter(
      (p: any) => Math.abs(parseFloat(p.quantity || p.qty || 0)) > 0
    )
    const openPositionsCount = activePositions.length

    // Calculate total P&L from all positions
    const totalPnL = positions.reduce(
      (sum: number, p: any) => sum + parseFloat(p.pnl || 0),
      0
    )

    // Count triggered positions (all positions from today)
    const triggeredCount = positions.length

    // Prepare triggered positions data
    const triggered = positions.map((p: any) => ({
      id: p.symbol,
      symbol: p.symbol,
      entryPrice: parseFloat(p.average_price || 0),
      quantity: parseFloat(p.quantity || 0),
      currentPrice: parseFloat(p.ltp || 0),
      pnl: parseFloat(p.pnl || 0),
      pnlPercent: parseFloat(p.pnlpercent || 0),
      protectiveSL: getProtectiveStopPrice(p, orders),
    }))

    // Prepare live tick feed ONLY for active positions (quantity > 0)
    // ONLY re-render this section when active positions change
    const activeTicks = activePositions.length > 0 
      ? activePositions.map((p: any) => ({
          symbol: p.symbol,
          price: parseFloat(p.ltp || 0),
          quantity: parseFloat(p.quantity || 0),
          timestamp: new Date().toISOString(),
        }))
      : []

    return {
      metrics: {
        openPositions: openPositionsCount,
        totalPnL: totalPnL,
        triggeredToday: triggeredCount,
      },
      triggeredPositions: triggered,
      liveTickFeed: activeTicks,
    }
  }, [positionDataKey, orderDataKey]) // Recompute when positions or protective orders change

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <div className="mb-2 flex items-center gap-2">
          <ExecutionModeBadge mode="LIVE" />
          <ExecutionModeBadge mode="TEST" />
        </div>
        <SectionTitle subtitle="Live broker positions and Test virtual positions are shown separately.">
          Positions & Trades
        </SectionTitle>
      </div>

      {/* Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          icon={<Activity className="text-emerald-500" />}
          label="Open Positions"
          value={metrics.openPositions}
          sublabel="Active trades"
          color="green"
        />
        <MetricCard
          icon={<Target className="text-blue-500" />}
          label="Current Strategy"
          value={strategyLabel}
          sublabel={strategySublabel}
          color="cyan"
        />
        <MetricCard
          icon={<DollarSign className="text-amber-500" />}
          label="Total P&L"
          value={formatCurrency(metrics.totalPnL)}
          sublabel={formatPercent(metrics.totalPnL > 0 ? 2.5 : -1.8)}
          color={metrics.totalPnL >= 0 ? 'green' : 'red'}
        />
        <MetricCard
          icon={<TrendingUp className="text-purple-500" />}
          label="Positions Triggered"
          value={metrics.triggeredToday}
          sublabel="Total today"
          color="cyan"
        />
      </div>

      {/* Triggered Positions Table */}
      <div>
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-semibold text-text-primary">
              Triggered Positions Today ({triggeredPositions.length})
            </h3>
            <ExecutionModeBadge mode="LIVE" />
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <p className="flex items-center gap-1.5 text-xs text-text-tertiary whitespace-nowrap">
              <Clock3 size={14} aria-hidden="true" />
              <span>Last refreshed</span>
              <time dateTime={lastUpdated || undefined}>
                {lastUpdated
                  ? new Date(lastUpdated).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })
                  : 'Waiting'}
              </time>
              <span aria-hidden="true">·</span>
              <span>Now</span>
              <time dateTime={currentTime.toISOString()}>
                {currentTime.toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })}
              </time>
            </p>
            {triggeredPositions.length > 0 && (
              <button
                onClick={() => exportPositionsCSV(triggeredPositions)}
                className="flex items-center gap-2 px-3 py-2 text-sm font-semibold text-emerald-400 hover:text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/20 rounded transition-colors"
                title="Download positions as CSV"
              >
                <Download size={16} />
                Export CSV
              </button>
            )}
          </div>
        </div>

        {dataLoading ? (
          <div className="flex items-center justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : triggeredPositions.length === 0 ? (
          <EmptyState
            icon={<AlertCircle size={48} />}
            title="No Triggered Positions"
            description="No positions have been triggered yet today."
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-bg-tertiary">
            <table className="w-full">
              <thead>
                <tr className="bg-bg-secondary border-b border-bg-tertiary">
                  <th className="px-6 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                    Symbol
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                    Entry Price
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                    Current Price
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                    Quantity
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                    Protective SL
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                    P&L
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {triggeredPositions.map((position) => (
                  <PositionTableRow key={position.id} position={position} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Live Tick Feed */}
      {liveTickFeed.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-text-primary mb-4">
            Live Tick Feed ({liveTickFeed.length} active)
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {liveTickFeed.map((tick) => (
              <LiveTickCard key={tick.symbol} tick={tick} />
            ))}
          </div>
        </div>
      )}

      <section className="space-y-4 border-t border-bg-tertiary pt-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <h3 className="text-lg font-semibold text-text-primary">
              Test Virtual Positions ({testActivity.positions.length})
            </h3>
            <ExecutionModeBadge mode="TEST" />
          </div>
          <p className="text-sm font-mono text-amber-300">
            Test P&amp;L {formatCurrency(testActivity.summary.net_pnl)}
          </p>
        </div>
        {testLoading ? (
          <div className="flex justify-center py-8"><LoadingSpinner /></div>
        ) : testActivity.positions.length === 0 ? (
          <EmptyState
            icon={<Activity size={40} />}
            title="No Test Positions"
            description="No virtual positions are open."
          />
        ) : (
          <div className="overflow-x-auto rounded-lg border border-amber-500/40">
            <table className="w-full">
              <thead>
                <tr className="border-b border-amber-500/30 bg-amber-500/10">
                  <th className="px-4 py-3 text-left text-xs font-semibold text-amber-200">Instrument</th>
                  <th className="px-4 py-3 text-left text-xs font-semibold text-amber-200">Symbol</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-amber-200">Qty</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-amber-200">Entry</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-amber-200">LTP</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-amber-200">Stop</th>
                  <th className="px-4 py-3 text-right text-xs font-semibold text-amber-200">Unrealized P&amp;L</th>
                </tr>
              </thead>
              <tbody>
                {testActivity.positions.map((position) => (
                  <tr key={`${position.instrument_id}-${position.symbol}`} className="border-b border-bg-tertiary">
                    <td className="px-4 py-3 text-sm text-text-primary">{position.instrument_name}</td>
                    <td className="px-4 py-3 font-mono text-sm text-text-primary">{position.symbol}</td>
                    <td className="px-4 py-3 text-right font-mono text-text-primary">{position.quantity}</td>
                    <td className="px-4 py-3 text-right font-mono text-text-primary">{formatCurrency(position.average_price)}</td>
                    <td className="px-4 py-3 text-right font-mono text-text-primary">{formatCurrency(position.ltp)}</td>
                    <td className="px-4 py-3 text-right font-mono text-text-primary">
                      {position.protective_sl == null ? '—' : formatCurrency(position.protective_sl)}
                    </td>
                    <td className={clsx('px-4 py-3 text-right font-mono font-bold', getValueColor(position.unrealized_pnl))}>
                      {formatCurrency(position.unrealized_pnl)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}

export default Positions
