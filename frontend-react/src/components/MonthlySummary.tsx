import React from 'react'
import { formatCurrency } from '@/utils/format'
import { clsx } from 'clsx'

interface MonthlySummaryProps {
  monthSummary: {
    total_pnl: number
    best_day: { day: number | null; pnl: number }
    worst_day: { day: number | null; pnl: number }
    winning_days: number
    losing_days: number
    total_trading_days: number
  } | null
}

const MetricCard: React.FC<{
  label: string
  value: string | number
  subLabel?: string
  color?: 'green' | 'red' | 'neutral'
  icon?: React.ReactNode
}> = ({ label, value, subLabel, color = 'neutral', icon }) => {
  const colorClasses = {
    green: 'text-green-400',
    red: 'text-red-400',
    neutral: 'text-cyan-400',
  }

  return (
    <div className="bg-gray-700 rounded-lg p-4 border border-gray-600">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-xs text-gray-400 mb-2">{label}</p>
          <p className={clsx('text-xl font-bold', colorClasses[color])}>
            {value}
          </p>
          {subLabel && <p className="text-xs text-gray-500 mt-1">{subLabel}</p>}
        </div>
        {icon && <div className="text-2xl opacity-50">{icon}</div>}
      </div>
    </div>
  )
}

const MonthlySummary: React.FC<MonthlySummaryProps> = ({ monthSummary }) => {
  if (!monthSummary) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 text-gray-400">
        Loading monthly summary...
      </div>
    )
  }

  const isProfitable = monthSummary.total_pnl >= 0

  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700 space-y-4">
      {/* Title */}
      <h3 className="text-lg font-bold text-white mb-4">Monthly Summary</h3>

      {/* Total Month P&L - Prominent */}
      <div
        className={clsx(
          'rounded-lg p-4 border-2 text-center',
          isProfitable
            ? 'bg-green-900/20 border-green-600 '
            : 'bg-red-900/20 border-red-600'
        )}
      >
        <p className="text-xs text-gray-400 mb-1">Total Month P&L</p>
        <p
          className={clsx(
            'text-3xl font-bold',
            isProfitable ? 'text-green-400' : 'text-red-400'
          )}
        >
          {formatCurrency(monthSummary.total_pnl)}
        </p>
      </div>

      {/* Grid of metrics */}
      <div className="grid grid-cols-2 gap-3">
        {/* Best Day */}
        <MetricCard
          label="Best Day"
          value={
            monthSummary.best_day.day
              ? `Day ${monthSummary.best_day.day}`
              : 'N/A'
          }
          subLabel={
            monthSummary.best_day.pnl > 0
              ? formatCurrency(monthSummary.best_day.pnl)
              : '-'
          }
          color={monthSummary.best_day.pnl > 0 ? 'green' : 'neutral'}
          icon="📈"
        />

        {/* Worst Day */}
        <MetricCard
          label="Worst Day"
          value={
            monthSummary.worst_day.day
              ? `Day ${monthSummary.worst_day.day}`
              : 'N/A'
          }
          subLabel={
            monthSummary.worst_day.pnl < 0
              ? formatCurrency(monthSummary.worst_day.pnl)
              : '-'
          }
          color={monthSummary.worst_day.pnl < 0 ? 'red' : 'neutral'}
          icon="📉"
        />

        {/* Winning Days */}
        <MetricCard
          label="Winning Days"
          value={monthSummary.winning_days}
          subLabel={
            monthSummary.total_trading_days > 0
              ? `${((monthSummary.winning_days / monthSummary.total_trading_days) * 100).toFixed(0)}% of trading days`
              : 'No trades'
          }
          color="green"
          icon="✅"
        />

        {/* Losing Days */}
        <MetricCard
          label="Losing Days"
          value={monthSummary.losing_days}
          subLabel={
            monthSummary.total_trading_days > 0
              ? `${((monthSummary.losing_days / monthSummary.total_trading_days) * 100).toFixed(0)}% of trading days`
              : 'No trades'
          }
          color="red"
          icon="❌"
        />
      </div>

      {/* Trading Days Summary */}
      <div className="bg-gray-700 rounded-lg p-3 border border-gray-600 text-center">
        <p className="text-xs text-gray-400">Total Trading Days</p>
        <p className="text-2xl font-bold text-cyan-400">
          {monthSummary.total_trading_days}
        </p>
      </div>
    </div>
  )
}

export default MonthlySummary
