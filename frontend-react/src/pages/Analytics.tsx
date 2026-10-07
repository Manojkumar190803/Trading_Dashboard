import { useMemo } from 'react'
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
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
import { TrendingUp, Target, Trophy, Zap } from 'lucide-react'
import {
  Card,
  MetricCard,
  SectionTitle,
  EmptyState,
  Table,
  TableRow,
  TableCell,
  Badge,
} from '@/components/UI'
import { useAnalyticsTrades, useAnalyticsSummary, useEquityCurve } from '@/hooks'
import { formatCurrency, formatPercent, getValueColor, formatNumber } from '@/utils/format'
import { clsx } from 'clsx'

const Analytics: React.FC = () => {
  const { trades } = useAnalyticsTrades()
  const summary = useAnalyticsSummary(trades)
  const curve = useEquityCurve(trades)

  // Generate sample equity curve data if no trades
  const equityCurveData = useMemo(() => {
    if (curve.length === 0) {
      return [
        { datetime: '09:30', total_pnl: 0 },
        { datetime: '10:00', total_pnl: 500 },
        { datetime: '10:30', total_pnl: -200 },
        { datetime: '11:00', total_pnl: 800 },
        { datetime: '11:30', total_pnl: 1200 },
        { datetime: '12:00', total_pnl: 1500 },
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

  // Daily performance data
  const dailyData = useMemo(() => {
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
      <div>
        <SectionTitle subtitle="Performance intelligence and trade metrics">
          Analytics Dashboard
        </SectionTitle>
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
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Equity Curve */}
        <div className="lg:col-span-2">
          <div className="mb-4">
            <h3 className="text-lg font-semibold text-text-primary">Equity Curve</h3>
            <p className="text-xs text-text-secondary mt-1">
              Cumulative profit/loss progression
            </p>
          </div>

          <Card>
            <div className="w-full h-64">
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
            </div>
          </Card>
        </div>

        {/* Trade Distribution */}
        <div>
          <div className="mb-4">
            <h3 className="text-lg font-semibold text-text-primary">Trade Distribution</h3>
            <p className="text-xs text-text-secondary mt-1">Wins vs Losses</p>
          </div>

          <Card className="h-64 flex items-center justify-center">
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
                  >
                    {tradeDistribution.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.fill} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0a0e27',
                      border: '1px solid rgba(255,255,255,0.1)',
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </Card>
        </div>
      </div>

      {/* Daily Performance */}
      {dailyData.length > 0 && (
        <div>
          <div className="mb-4">
            <h3 className="text-lg font-semibold text-text-primary">Daily Performance</h3>
          </div>

          <Card>
            <div className="w-full h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={dailyData}>
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
            </div>
          </Card>
        </div>
      )}

      {/* Summary Stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card>
          <h4 className="text-sm font-semibold text-text-primary mb-4">Profitability</h4>
          <div className="space-y-3">
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
          <h4 className="text-sm font-semibold text-text-primary mb-4">Statistics</h4>
          <div className="space-y-3">
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

      {/* Recent Trades */}
      {trades.length > 0 && (
        <div>
          <h3 className="text-lg font-semibold text-text-primary mb-4">Recent Trades</h3>
          <Card>
            <div className="overflow-x-auto">
              <Table headers={['Timestamp', 'Strategy', 'P&L', 'Source', 'Message']}>
                {trades.slice(0, 10).map((trade, idx) => (
                  <TableRow key={idx}>
                    <TableCell>
                      <span className="text-sm text-text-secondary">
                        {new Date(trade.timestamp).toLocaleTimeString('en-IN', {
                          hour: '2-digit',
                          minute: '2-digit',
                          second: '2-digit',
                          hour12: true,
                        })}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge size="sm" variant="info">
                        {trade.strategy}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <span
                        className={clsx(
                          'font-mono font-bold',
                          getValueColor(trade.pnl)
                        )}
                      >
                        {formatCurrency(trade.pnl)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-text-secondary">{trade.source}</span>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-text-secondary">{trade.message}</span>
                    </TableCell>
                  </TableRow>
                ))}
              </Table>
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}

export default Analytics
