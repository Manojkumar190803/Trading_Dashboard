import { useState, useEffect, useMemo, memo } from 'react'
import { AlertCircle, TrendingUp, Activity, DollarSign, Target, Download } from 'lucide-react'
import {
  Card,
  SectionTitle,
  LoadingSpinner,
  EmptyState,
  Badge,
  MetricCard,
} from '@/components/UI'
import { useRealAccountData } from '@/hooks'
import { formatCurrency, formatPercent, getValueColor } from '@/utils/format'
import { exportPositionsCSV } from '@/utils/csv-export'
import { clsx } from 'clsx'

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
            <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-xs text-emerald-500 font-semibold">LIVE</span>
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
  // Fetch real OpenAlgo data - poll every 1 second for live updates
  const { data: accountData, isLoading: dataLoading } = useRealAccountData(true, 1000)

  // Create a stable key from position data to only trigger updates when data actually changes
  const positionDataKey = useMemo(() => {
    if (!accountData?.positions) return 'empty'
    
    // Create a key from actual position data (symbol + quantity)
    // This only changes when positions actually change, not on every poll
    return accountData.positions
      .map((p: any) => `${p.symbol}:${p.quantity}:${p.pnl}`)
      .join('|')
  }, [accountData?.positions])

  // Memoize metrics and positions data - only update when position data actually changes
  const { metrics, triggeredPositions, liveTickFeed } = useMemo(() => {
    if (!accountData) {
      return {
        metrics: {
          openPositions: 0,
          currentStrategy: 'None',
          totalPnL: 0,
          triggeredToday: 0,
        },
        triggeredPositions: [],
        liveTickFeed: [],
      }
    }

    const positions = accountData.positions || []
    const orders = accountData.orders?.orders || []

    // Count only active positions (quantity > 0)
    const activePositions = positions.filter(
      (p: any) => parseFloat(p.quantity || 0) > 0
    )
    const openPositionsCount = activePositions.length

    // Calculate total P&L from all positions
    const totalPnL = positions.reduce(
      (sum: number, p: any) => sum + parseFloat(p.pnl || 0),
      0
    )

    // Extract active strategy from orders
    const completedOrders = orders.filter(
      (o: any) => o.order_status === 'complete'
    )
    const activeStrategy = completedOrders.length > 0 
      ? completedOrders[0].strategy?.split('_')[0] || 'Unknown'
      : 'None'

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
        currentStrategy: activeStrategy,
        totalPnL: totalPnL,
        triggeredToday: triggeredCount,
      },
      triggeredPositions: triggered,
      liveTickFeed: activeTicks,
    }
  }, [positionDataKey]) // Only depend on actual position data changes, not object reference

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <SectionTitle subtitle="Real-time position tracking and P&L analysis">
          Positions & Trades
        </SectionTitle>
      </div>

      {/* Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          icon={<Activity className="text-emerald-500" />}
          label="Open Positions"
          value={metrics.openPositions}
          subLabel="Active trades"
          color="emerald"
        />
        <MetricCard
          icon={<Target className="text-blue-500" />}
          label="Current Strategy"
          value={metrics.currentStrategy}
          subLabel="Active strategy"
          color="blue"
        />
        <MetricCard
          icon={<DollarSign className="text-amber-500" />}
          label="Total P&L"
          value={formatCurrency(metrics.totalPnL)}
          subLabel={formatPercent(metrics.totalPnL > 0 ? 2.5 : -1.8)}
          color={metrics.totalPnL >= 0 ? 'emerald' : 'red'}
        />
        <MetricCard
          icon={<TrendingUp className="text-purple-500" />}
          label="Positions Triggered"
          value={metrics.triggeredToday}
          subLabel="Total today"
          color="purple"
        />
      </div>

      {/* Triggered Positions Table */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-text-primary">
            Triggered Positions Today ({triggeredPositions.length})
          </h3>
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
    </div>
  )
}

export default Positions
