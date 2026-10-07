import { useState } from 'react'
import { AlertCircle, X } from 'lucide-react'
import {
  Card,
  SectionTitle,
  LoadingSpinner,
  EmptyState,
  Badge,
} from '@/components/UI'
import { useStrategyAlerts } from '@/hooks'
import { formatCurrency, formatPercent, getValueColor } from '@/utils/format'
import { clsx } from 'clsx'

const Positions: React.FC = () => {
  const { alerts, isLoading } = useStrategyAlerts(true)
  const [selectedPosition, setSelectedPosition] = useState<string | null>(null)

  // Mock positions data - in production, this would come from CSV parsing
  const positions = [
    {
      id: 'pos-1',
      option_symbol: 'NIFTY25SEP26000CE',
      option_type: 'CE' as const,
      entry_price: 145.5,
      current_price: 152.25,
      quantity: 5,
      entry_time: '09:35:00',
      stop_level: 140.0,
      trailing_sl_level: 151.0,
      risk_points: 5.5,
      pnl: 33.75,
      pnl_percent: 4.62,
      progress_status: 'In Profit',
      strategy: '21 EMA',
    },
    {
      id: 'pos-2',
      option_symbol: 'NIFTY25SEP26100CE',
      option_type: 'CE' as const,
      entry_price: 92.75,
      current_price: 88.5,
      quantity: 3,
      entry_time: '10:12:00',
      stop_level: 90.0,
      trailing_sl_level: 90.5,
      risk_points: 2.75,
      pnl: -12.75,
      pnl_percent: -4.58,
      progress_status: 'At Risk',
      strategy: '2BC',
    },
  ]

  // Pending entries from alerts
  const pendingEntries = alerts
    .filter((a) => a.category === 'PENDING_ENTRY')
    .slice(0, 3)

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <SectionTitle subtitle="Monitor open positions and active entries">
          Live Positions
        </SectionTitle>
      </div>

      {/* Active Positions */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-text-primary">
            Active Positions ({positions.length})
          </h3>
          <Badge variant="success">{positions.filter((p) => p.pnl >= 0).length} Profit</Badge>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : positions.length === 0 ? (
          <EmptyState
            icon={<AlertCircle size={48} />}
            title="No Active Positions"
            description="You don't have any open trading positions at the moment."
          />
        ) : (
          <div className="space-y-3">
            {positions.map((position) => (
              <Card key={position.id} hoverable className="cursor-pointer">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-6 gap-4 items-center">
                  {/* Symbol & Type */}
                  <div>
                    <p className="text-xs uppercase text-text-secondary font-semibold mb-1">
                      Symbol
                    </p>
                    <p className="font-mono font-bold text-text-primary break-words">
                      {position.option_symbol}
                    </p>
                    <Badge
                      size="sm"
                      variant={position.option_type === 'CE' ? 'success' : 'danger'}
                      className="mt-2"
                    >
                      {position.option_type}
                    </Badge>
                  </div>

                  {/* Entry & Current Price */}
                  <div>
                    <p className="text-xs uppercase text-text-secondary font-semibold mb-1">
                      Entry Price
                    </p>
                    <p className="font-mono font-bold text-text-primary">
                      {formatCurrency(position.entry_price)}
                    </p>
                    <p className="text-xs text-text-tertiary mt-1">
                      Current: {formatCurrency(position.current_price)}
                    </p>
                  </div>

                  {/* Qty & Stop Level */}
                  <div>
                    <p className="text-xs uppercase text-text-secondary font-semibold mb-1">
                      Qty
                    </p>
                    <p className="font-bold text-text-primary text-lg">{position.quantity}</p>
                    <p className="text-xs text-text-tertiary mt-1">
                      SL: {formatCurrency(position.stop_level)}
                    </p>
                  </div>

                  {/* P&L */}
                  <div>
                    <p className="text-xs uppercase text-text-secondary font-semibold mb-1">
                      P&L (₹)
                    </p>
                    <p className={clsx('font-bold text-lg', getValueColor(position.pnl))}>
                      {formatCurrency(position.pnl)}
                    </p>
                    <p className={clsx('text-xs', getValueColor(position.pnl))}>
                      {formatPercent(position.pnl_percent)}
                    </p>
                  </div>

                  {/* Status */}
                  <div>
                    <p className="text-xs uppercase text-text-secondary font-semibold mb-1">
                      Status
                    </p>
                    <Badge
                      size="sm"
                      variant={position.pnl >= 0 ? 'success' : 'danger'}
                    >
                      {position.progress_status}
                    </Badge>
                    <p className="text-xs text-text-tertiary mt-2">
                      Entered: {position.entry_time}
                    </p>
                  </div>

                  {/* Action */}
                  <div className="flex justify-end">
                    <button
                      onClick={() =>
                        setSelectedPosition(
                          selectedPosition === position.id ? null : position.id
                        )
                      }
                      className="p-2 hover:bg-accent-red/20 rounded transition-colors text-accent-red"
                      title="Close position"
                    >
                      <X size={20} />
                    </button>
                  </div>
                </div>

                {/* Expanded Details */}
                {selectedPosition === position.id && (
                  <div className="mt-4 pt-4 border-t border-bg-tertiary/50 grid grid-cols-2 md:grid-cols-4 gap-4">
                    <div>
                      <p className="text-xs uppercase text-text-secondary font-semibold mb-1">
                        Trailing SL
                      </p>
                      <p className="font-mono text-text-primary">
                        {formatCurrency(position.trailing_sl_level)}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase text-text-secondary font-semibold mb-1">
                        Risk Points
                      </p>
                      <p className="font-mono text-text-primary">
                        {position.risk_points}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase text-text-secondary font-semibold mb-1">
                        Strategy
                      </p>
                      <Badge size="sm" variant="info">
                        {position.strategy}
                      </Badge>
                    </div>
                    <div className="flex justify-end gap-2">
                      <button className="px-3 py-1.5 bg-accent-red/10 text-accent-red rounded text-xs font-semibold hover:bg-accent-red/20 transition-colors">
                        Close
                      </button>
                      <button className="px-3 py-1.5 bg-accent-yellow/10 text-accent-yellow rounded text-xs font-semibold hover:bg-accent-yellow/20 transition-colors">
                        Adjust SL
                      </button>
                    </div>
                  </div>
                )}
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Pending Entries */}
      {pendingEntries.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-text-primary mb-4">
            Pending Entries ({pendingEntries.length})
          </h3>
          <div className="space-y-3">
            {pendingEntries.map((entry, idx) => (
              <Card key={idx} className="border-accent-yellow/50">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="font-semibold text-text-primary mb-1">
                      {entry.message.split(' ').slice(0, 3).join(' ')}
                    </p>
                    <p className="text-sm text-text-secondary">{entry.message}</p>
                  </div>
                  <Badge variant="warning">PENDING</Badge>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default Positions
