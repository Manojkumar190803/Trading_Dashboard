import { useMemo, useState, useCallback } from 'react'
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from 'recharts'
import { TrendingUp, Target, Trophy, Zap, Download, RotateCcw, BarChart3, Activity } from 'lucide-react'
import {
  Card,
  MetricCard,
  SectionTitle,
  EmptyState,
} from '@/components/UI'
import DailyPnLCalendar from '@/components/DailyPnLCalendar'
import MonthlySummary from '@/components/MonthlySummary'
import { useAnalyticsTrades, useAnalyticsSummary, useEquityCurve, useAnalyticsSummaryFromAPI, useDailyPnL } from '@/hooks'
import { formatCurrency, formatPercent, getValueColor, formatNumber } from '@/utils/format'
import { exportAnalyticsCSV, resetAnalytics } from '@/utils/csv-export'
import { clsx } from 'clsx'

const Analytics: React.FC = () => {
  const { trades, refetch } = useAnalyticsTrades()
  const tradesSummary = useAnalyticsSummary(trades)
  const { summary: apiSummary } = useAnalyticsSummaryFromAPI()
  const { dailyData, reset: resetDaily } = useDailyPnL()
  
  // Use API summary if available, otherwise fall back to trades-based summary
  const summary = apiSummary.trades_completed > 0 ? {
    completed_trades: apiSummary.trades_completed,
    gross_profit: apiSummary.gross_profit,
    gross_loss: apiSummary.gross_loss,
    winning_trades: apiSummary.winning_trades,
    expectancy: apiSummary.expectancy,
    win_rate: apiSummary.win_rate,
    profit_factor: apiSummary.profit_factor,
  } : tradesSummary
  
  const curve = useEquityCurve(trades)
  const [isResetting, setIsResetting] = useState(false)
  const [equityChartType, setEquityChartType] = useState<'area' | 'bar' | 'line'>('area')
  const [performanceChartType, setPerformanceChartType] = useState<'bar' | 'line'>('bar')

  const handleExportAnalytics = useCallback(() => {
    exportAnalyticsCSV(summary, trades)
  }, [summary, trades])

  const handleResetAnalytics = useCallback(async () => {
    setIsResetting(true)
    try {
      const success = await resetAnalytics()
      if (success) {
        // Perform multiple refetches with increasing delays
        // to ensure fresh data after reset
        setTimeout(() => {
          refetch()
          console.log('First refetch after reset (500ms)')
        }, 500)
        
        setTimeout(() => {
          refetch()
          console.log('Second refetch after reset (1500ms)')
        }, 1500)
        
        setTimeout(() => {
          refetch()
          console.log('Third refetch after reset (2500ms)')
        }, 2500)
      }
    } finally {
      setIsResetting(false)
    }
  }, [refetch])

  // Generate equity curve data - flat when no trades
  const equityCurveData = useMemo(() => {
    if (curve.length === 0) {
      // Flat equity curve when no trades
      return [
        { datetime: '09:30', total_pnl: 0 },
        { datetime: '10:00', total_pnl: 0 },
        { datetime: '10:30', total_pnl: 0 },
        { datetime: '11:00', total_pnl: 0 },
        { datetime: '11:30', total_pnl: 0 },
        { datetime: '12:00', total_pnl: 0 },
      ]
    }
    return curve.map((c) => ({
      ...c,
      datetime: new Date(c.datetime).toLocaleTimeString('en-IN', {
        hour: '2-digit',
        minute: '2-digit',
        hour12: true,
      }),
    }))
  }, [curve])

  // Trade distribution by result
  const tradeDistribution = [
    { name: 'Winning', value: summary.winning_trades, fill: '#27d48a' },
    {
      name: 'Losing',
      value: summary.completed_trades - summary.winning_trades,
      fill: '#ff5f6d',
    },
  ]

  // Performance data for daily charts (calculated from trades)
  const performanceData = useMemo(() => {
    if (trades.length === 0) {
      return []
    }

    const grouped: Record<string, number> = {}
    trades.forEach((trade) => {
      const date = new Date(trade.timestamp).toLocaleDateString('en-IN')
      grouped[date] = (grouped[date] || 0) + trade.pnl
    })

    return Object.entries(grouped).map(([date, pnl]) => ({
      date,
      pnl,
      gain: pnl > 0 ? pnl : 0,
      loss: pnl < 0 ? Math.abs(pnl) : 0,
    }))
  }, [trades])

  const CustomTooltip = ({ active, payload }: any) => {
    if (active && payload && payload.length) {
      return (
        <div className="bg-bg-surface border border-bg-tertiary rounded p-2 text-xs">
          <p className="font-semibold text-text-primary">{payload[0].payload.datetime}</p>
          <p className={clsx('font-mono', getValueColor(payload[0].value))}>
            ₹{formatNumber(payload[0].value, 0)}
          </p>
        </div>
      )
    }
    return null
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <SectionTitle subtitle="Performance intelligence and trade metrics">
            Analytics Dashboard
          </SectionTitle>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={handleExportAnalytics}
            disabled={trades.length === 0}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-emerald-400 hover:text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/20 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="Download analytics report as CSV"
          >
            <Download size={16} />
            Export CSV
          </button>
          <button
            onClick={handleResetAnalytics}
            disabled={isResetting || trades.length === 0}
            className="flex items-center gap-2 px-4 py-2 text-sm font-semibold text-red-400 hover:text-red-300 bg-red-500/10 hover:bg-red-500/20 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            title="Reset all analytics data"
          >
            <RotateCcw size={16} className={isResetting ? 'animate-spin' : ''} />
            Reset
          </button>
        </div>
      </div>

      {/* Key Metrics */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard
          label="Net Profit/Loss"
          value={formatCurrency(summary.gross_profit - summary.gross_loss)}
          sublabel="Total P&L today"
          icon={<TrendingUp size={16} />}
          color={summary.gross_profit >= summary.gross_loss ? 'green' : 'red'}
          trend={
            summary.gross_profit >= summary.gross_loss ? 'up' : 'down'
          }
        />
        <MetricCard
          label="Win Rate"
          value={formatPercent(summary.win_rate)}
          sublabel="Winning trades"
          icon={<Trophy size={16} />}
          color={summary.win_rate > 50 ? 'green' : 'yellow'}
        />
        <MetricCard
          label="Profit Factor"
          value={formatNumber(summary.profit_factor, 2)}
          sublabel="Gross Profit / Loss"
          icon={<Zap size={16} />}
          color={summary.profit_factor > 1 ? 'green' : 'yellow'}
        />
        <MetricCard
          label="Trades Completed"
          value={summary.completed_trades}
          sublabel="Closed positions"
          icon={<Target size={16} />}
          color="cyan"
        />
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Equity Curve */}
        <div className="lg:col-span-2">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-text-primary">Equity Curve</h3>
              <p className="text-xs text-text-secondary mt-1">
                Cumulative profit/loss progression
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setEquityChartType('area')}
                className={clsx(
                  'p-2 rounded transition-colors',
                  equityChartType === 'area'
                    ? 'bg-cyan-500/20 text-cyan-400'
                    : 'bg-bg-secondary text-text-secondary hover:bg-bg-tertiary'
                )}
                title="Area Chart"
              >
                <Activity size={16} />
              </button>
              <button
                onClick={() => setEquityChartType('bar')}
                className={clsx(
                  'p-2 rounded transition-colors',
                  equityChartType === 'bar'
                    ? 'bg-cyan-500/20 text-cyan-400'
                    : 'bg-bg-secondary text-text-secondary hover:bg-bg-tertiary'
                )}
                title="Bar Chart"
              >
                <BarChart3 size={16} />
              </button>
              <button
                onClick={() => setEquityChartType('line')}
                className={clsx(
                  'p-2 rounded transition-colors',
                  equityChartType === 'line'
                    ? 'bg-cyan-500/20 text-cyan-400'
                    : 'bg-bg-secondary text-text-secondary hover:bg-bg-tertiary'
                )}
                title="Line Chart"
              >
                <TrendingUp size={16} />
              </button>
            </div>
          </div>

          <Card>
            <div className="w-full h-48">
              {equityChartType === 'area' && (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={equityCurveData}>
                    <defs>
                      <linearGradient id="colorPnl" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#59d0ff" stopOpacity={0.8} />
                        <stop offset="95%" stopColor="#59d0ff" stopOpacity={0} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="rgba(255,255,255,0.1)"
                    />
                    <XAxis
                      dataKey="datetime"
                      stroke="rgba(255,255,255,0.3)"
                      style={{ fontSize: '12px' }}
                    />
                    <YAxis
                      stroke="rgba(255,255,255,0.3)"
                      style={{ fontSize: '12px' }}
                      tickFormatter={(value) => `₹${(value / 1000).toFixed(0)}k`}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Area
                      type="monotone"
                      dataKey="total_pnl"
                      stroke="#59d0ff"
                      fillOpacity={1}
                      fill="url(#colorPnl)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
              {equityChartType === 'bar' && (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={equityCurveData}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="rgba(255,255,255,0.1)"
                    />
                    <XAxis
                      dataKey="datetime"
                      stroke="rgba(255,255,255,0.3)"
                      style={{ fontSize: '12px' }}
                    />
                    <YAxis
                      stroke="rgba(255,255,255,0.3)"
                      style={{ fontSize: '12px' }}
                      tickFormatter={(value) => `₹${(value / 1000).toFixed(0)}k`}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Bar dataKey="total_pnl" fill="#59d0ff" />
                  </BarChart>
                </ResponsiveContainer>
              )}
              {equityChartType === 'line' && (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={equityCurveData}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="rgba(255,255,255,0.1)"
                    />
                    <XAxis
                      dataKey="datetime"
                      stroke="rgba(255,255,255,0.3)"
                      style={{ fontSize: '12px' }}
                    />
                    <YAxis
                      stroke="rgba(255,255,255,0.3)"
                      style={{ fontSize: '12px' }}
                      tickFormatter={(value) => `₹${(value / 1000).toFixed(0)}k`}
                    />
                    <Tooltip content={<CustomTooltip />} />
                    <Line
                      type="monotone"
                      dataKey="total_pnl"
                      stroke="#59d0ff"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
          </Card>
        </div>

        {/* Trade Distribution */}
        <div>
          <div className="mb-3">
            <h3 className="text-lg font-semibold text-text-primary">Trade Distribution</h3>
            <p className="text-xs text-text-secondary mt-1">Wins vs Losses</p>
          </div>

          <Card className="h-48 flex items-center justify-center">
            {summary.completed_trades === 0 ? (
              <EmptyState title="No trades yet" />
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={tradeDistribution}
                    cx="50%"
                    cy="50%"
                    innerRadius={40}
                    outerRadius={80}
                    paddingAngle={2}
                    dataKey="value"
                    label={false}
                    isAnimationActive={false}
                  >
                    {tradeDistribution.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip
                    cursor={{ fill: 'rgba(255,255,255,0.1)' }}
                    contentStyle={{
                      backgroundColor: '#0a0e27',
                      border: '1px solid rgba(255,255,255,0.2)',
                      borderRadius: '6px',
                      padding: '8px 12px',
                      boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
                    }}
                    formatter={(value: any) => [
                      <span key="value" style={{ color: '#ffffff', fontWeight: 'bold' }}>
                        {value} trades
                      </span>,
                    ]}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </Card>
        </div>
      </div>

      {/* Daily Performance */}
      {performanceData.length > 0 && (
        <div className="w-full">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <h3 className="text-lg font-semibold text-text-primary">Daily Performance</h3>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPerformanceChartType('bar')}
                className={clsx(
                  'p-2 rounded transition-colors',
                  performanceChartType === 'bar'
                    ? 'bg-cyan-500/20 text-cyan-400'
                    : 'bg-bg-secondary text-text-secondary hover:bg-bg-tertiary'
                )}
                title="Bar Chart"
              >
                <BarChart3 size={16} />
              </button>
              <button
                onClick={() => setPerformanceChartType('line')}
                className={clsx(
                  'p-2 rounded transition-colors',
                  performanceChartType === 'line'
                    ? 'bg-cyan-500/20 text-cyan-400'
                    : 'bg-bg-secondary text-text-secondary hover:bg-bg-tertiary'
                )}
                title="Line Chart"
              >
                <TrendingUp size={16} />
              </button>
            </div>
          </div>

          <Card>
            <div className="w-full h-48">
              {performanceChartType === 'bar' && (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={performanceData}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="rgba(255,255,255,0.1)"
                    />
                    <XAxis dataKey="date" stroke="rgba(255,255,255,0.3)" />
                    <YAxis stroke="rgba(255,255,255,0.3)" />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#0a0e27',
                        border: '1px solid rgba(255,255,255,0.1)',
                      }}
                    />
                    <Legend />
                    <Bar dataKey="gain" stackId="a" fill="#27d48a" name="Gains" />
                    <Bar dataKey="loss" stackId="a" fill="#ff5f6d" name="Losses" />
                  </BarChart>
                </ResponsiveContainer>
              )}
              {performanceChartType === 'line' && (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={performanceData}>
                    <CartesianGrid
                      strokeDasharray="3 3"
                      stroke="rgba(255,255,255,0.1)"
                    />
                    <XAxis dataKey="date" stroke="rgba(255,255,255,0.3)" />
                    <YAxis stroke="rgba(255,255,255,0.3)" />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: '#0a0e27',
                        border: '1px solid rgba(255,255,255,0.1)',
                      }}
                    />
                    <Legend />
                    <Line type="monotone" dataKey="gain" stroke="#27d48a" strokeWidth={2} name="Gains" />
                    <Line type="monotone" dataKey="loss" stroke="#ff5f6d" strokeWidth={2} name="Losses" />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </div>
          </Card>
        </div>
      )}

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <Card>
          <h4 className="text-sm font-semibold text-text-primary mb-3">Profitability</h4>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Gross Profit</span>
              <span className="font-bold text-accent-green">
                ₹{formatNumber(summary.gross_profit)}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Gross Loss</span>
              <span className="font-bold text-accent-red">
                -₹{formatNumber(summary.gross_loss)}
              </span>
            </div>
            <div className="border-t border-bg-tertiary/50 pt-3 flex items-center justify-between">
              <span className="text-sm font-semibold text-text-primary">Net P&L</span>
              <span
                className={clsx(
                  'font-bold text-lg',
                  summary.gross_profit >= summary.gross_loss
                    ? 'text-accent-green'
                    : 'text-accent-red'
                )}
              >
                ₹{formatNumber(summary.gross_profit - summary.gross_loss)}
              </span>
            </div>
          </div>
        </Card>

        <Card>
          <h4 className="text-sm font-semibold text-text-primary mb-3">Risk Metrics</h4>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Total Trades</span>
              <span className="font-bold">{summary.completed_trades}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Expectancy</span>
              <span className="font-bold text-accent-cyan">
                ₹{formatNumber(summary.expectancy)}
              </span>
            </div>
            <div className="border-t border-bg-tertiary/50 pt-3 flex items-center justify-between">
              <span className="text-sm font-semibold text-text-primary">Avg P&L/Trade</span>
              <span
                className={clsx(
                  'font-bold',
                  summary.expectancy >= 0 ? 'text-accent-green' : 'text-accent-red'
                )}
              >
                ₹{formatNumber(summary.expectancy)}
              </span>
            </div>
          </div>
        </Card>
      </div>

      {/* Daily P&L Calendar & Monthly Summary */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <DailyPnLCalendar
          dailyData={dailyData}
          onExport={() => {
            // Export daily P&L data
            if (dailyData) {
              const csvContent = [
                'Day,P&L,Trades',
                ...Object.entries(dailyData.days).map(
                  ([day, data]) => `${day},${data.pnl},${data.trades}`
                ),
              ].join('\n')

              const blob = new Blob([csvContent], { type: 'text/csv' })
              const url = window.URL.createObjectURL(blob)
              const a = document.createElement('a')
              a.href = url
              a.download = `daily_pnl_${dailyData.month.replace(' ', '_')}.csv`
              a.click()
              window.URL.revokeObjectURL(url)
            }
          }}
          onReset={resetDaily}
        />

        <MonthlySummary monthSummary={dailyData?.month_summary || null} />
      </div>
    </div>
  )
}

export default Analytics
