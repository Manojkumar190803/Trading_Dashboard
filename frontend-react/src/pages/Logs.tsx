import { useState } from 'react'
import { AlertCircle, AlertTriangle, CheckCircle2, Info } from 'lucide-react'
import {
  Card,
  SectionTitle,
  EmptyState,
  Badge,
} from '@/components/UI'
import { formatTime } from '@/utils/format'
import { clsx } from 'clsx'

interface LogEntry {
  id: string
  timestamp: string
  level: 'INFO' | 'SUCCESS' | 'WARNING' | 'ERROR'
  message: string
  category?: string
  strategy?: string
  details?: string
}

const Logs: React.FC = () => {
  const [logs, setLogs] = useState<LogEntry[]>([
    {
      id: 'log-1',
      timestamp: '2026-10-06T14:32:45',
      level: 'SUCCESS',
      message: 'Strategy initialized successfully',
      category: 'SYSTEM',
      strategy: 'All',
    },
    {
      id: 'log-2',
      timestamp: '2026-10-06T14:35:12',
      level: 'INFO',
      message: 'Pre-market checks completed',
      category: 'READINESS',
      strategy: 'All',
    },
    {
      id: 'log-3',
      timestamp: '2026-10-06T09:30:02',
      level: 'SUCCESS',
      message: 'Market open signal received',
      category: 'MARKET',
      strategy: 'All',
    },
    {
      id: 'log-4',
      timestamp: '2026-10-06T09:35:42',
      level: 'SUCCESS',
      message: 'Entry signal generated: NIFTY25SEP26000CE',
      category: 'SIGNAL',
      strategy: '21 EMA',
      details: 'Price crossed 200 EMA, Buy signal triggered',
    },
    {
      id: 'log-5',
      timestamp: '2026-10-06T09:36:15',
      level: 'SUCCESS',
      message: 'Order placed: BUY 5 NIFTY25SEP26000CE @ 145.50',
      category: 'ORDER',
      strategy: '21 EMA',
    },
    {
      id: 'log-6',
      timestamp: '2026-10-06T09:36:28',
      level: 'SUCCESS',
      message: 'Order filled at ₹145.50',
      category: 'EXECUTION',
      strategy: '21 EMA',
    },
    {
      id: 'log-7',
      timestamp: '2026-10-06T10:12:15',
      level: 'SUCCESS',
      message: 'Entry signal generated: NIFTY25SEP26100CE',
      category: 'SIGNAL',
      strategy: '2BC',
    },
    {
      id: 'log-8',
      timestamp: '2026-10-06T11:45:30',
      level: 'WARNING',
      message: 'Trailing stop loss updated at ₹151.00',
      category: 'ALERT',
      strategy: '21 EMA',
    },
    {
      id: 'log-9',
      timestamp: '2026-10-06T13:20:05',
      level: 'INFO',
      message: 'Monitoring open positions',
      category: 'MONITOR',
      strategy: 'All',
    },
  ])

  const [filterLevel, setFilterLevel] = useState<LogEntry['level'] | 'ALL'>('ALL')
  const [filterStrategy, setFilterStrategy] = useState<string>('ALL')
  const [expandedLog, setExpandedLog] = useState<string | null>(null)

  // Get unique strategies
  const strategies = Array.from(
    new Set(logs.map((l) => l.strategy).filter(Boolean))
  ) as string[]

  // Filter logs
  const filteredLogs = logs.filter((log) => {
    const levelMatch = filterLevel === 'ALL' || log.level === filterLevel
    const strategyMatch =
      filterStrategy === 'ALL' || log.strategy === filterStrategy
    return levelMatch && strategyMatch
  })

  // Get log level icon
  const getLevelIcon = (level: LogEntry['level']) => {
    switch (level) {
      case 'INFO':
        return <Info size={16} className="text-accent-cyan" />
      case 'SUCCESS':
        return <CheckCircle2 size={16} className="text-accent-green" />
      case 'WARNING':
        return <AlertTriangle size={16} className="text-accent-yellow" />
      case 'ERROR':
        return <AlertCircle size={16} className="text-accent-red" />
    }
  }

  const getLevelColor = (level: LogEntry['level']) => {
    switch (level) {
      case 'INFO':
        return 'info'
      case 'SUCCESS':
        return 'success'
      case 'WARNING':
        return 'warning'
      case 'ERROR':
        return 'danger'
    }
  }

  const getLevelBgColor = (level: LogEntry['level']) => {
    switch (level) {
      case 'INFO':
        return 'bg-accent-cyan/5 border-accent-cyan/30'
      case 'SUCCESS':
        return 'bg-accent-green/5 border-accent-green/30'
      case 'WARNING':
        return 'bg-accent-yellow/5 border-accent-yellow/30'
      case 'ERROR':
        return 'bg-accent-red/5 border-accent-red/30'
    }
  }

  const logStats = {
    total: logs.length,
    errors: logs.filter((l) => l.level === 'ERROR').length,
    warnings: logs.filter((l) => l.level === 'WARNING').length,
    success: logs.filter((l) => l.level === 'SUCCESS').length,
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <SectionTitle subtitle="Detailed strategy activity and system logs">
          System Logs
        </SectionTitle>
      </div>

      {/* Log Statistics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <Card>
          <div className="text-center">
            <p className="text-xs uppercase text-text-secondary font-semibold mb-2">
              Total Logs
            </p>
            <p className="text-3xl font-bold text-text-primary">{logStats.total}</p>
          </div>
        </Card>
        <Card>
          <div className="text-center">
            <p className="text-xs uppercase text-text-secondary font-semibold mb-2">
              Errors
            </p>
            <p className="text-3xl font-bold text-accent-red">{logStats.errors}</p>
          </div>
        </Card>
        <Card>
          <div className="text-center">
            <p className="text-xs uppercase text-text-secondary font-semibold mb-2">
              Warnings
            </p>
            <p className="text-3xl font-bold text-accent-yellow">
              {logStats.warnings}
            </p>
          </div>
        </Card>
        <Card>
          <div className="text-center">
            <p className="text-xs uppercase text-text-secondary font-semibold mb-2">
              Success
            </p>
            <p className="text-3xl font-bold text-accent-green">{logStats.success}</p>
          </div>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <div className="flex flex-col gap-4">
          <div>
            <label className="text-xs uppercase text-text-secondary font-semibold block mb-2">
              Filter by Level
            </label>
            <div className="flex flex-wrap gap-2">
              {['ALL', 'INFO', 'SUCCESS', 'WARNING', 'ERROR'].map((level) => (
                <button
                  key={level}
                  onClick={() => setFilterLevel(level as any)}
                  className={clsx(
                    'px-3 py-1.5 rounded text-xs font-medium transition-colors',
                    filterLevel === level
                      ? 'bg-accent-cyan text-bg-primary'
                      : 'bg-bg-secondary text-text-secondary hover:bg-bg-tertiary'
                  )}
                >
                  {level}
                </button>
              ))}
            </div>
          </div>

          {strategies.length > 0 && (
            <div>
              <label className="text-xs uppercase text-text-secondary font-semibold block mb-2">
                Filter by Strategy
              </label>
              <div className="flex flex-wrap gap-2">
                {['ALL', ...strategies].map((strategy) => (
                  <button
                    key={strategy}
                    onClick={() => setFilterStrategy(strategy)}
                    className={clsx(
                      'px-3 py-1.5 rounded text-xs font-medium transition-colors',
                      filterStrategy === strategy
                        ? 'bg-accent-cyan text-bg-primary'
                        : 'bg-bg-secondary text-text-secondary hover:bg-bg-tertiary'
                    )}
                  >
                    {strategy}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </Card>

      {/* Logs Display */}
      <div>
        <div className="mb-4 flex items-center justify-between">
          <h3 className="text-lg font-semibold text-text-primary">
            Activity Log ({filteredLogs.length})
          </h3>
          {filteredLogs.length > 0 && (
            <button
              onClick={() => setLogs([])}
              className="px-3 py-1.5 text-xs bg-accent-red/10 text-accent-red rounded hover:bg-accent-red/20 transition-colors font-medium"
            >
              Clear All
            </button>
          )}
        </div>

        {filteredLogs.length === 0 ? (
          <Card>
            <EmptyState
              icon={<AlertCircle size={40} />}
              title="No Logs Found"
              description="No logs match the selected filters"
            />
          </Card>
        ) : (
          <div className="space-y-2 max-h-[600px] overflow-y-auto">
            {filteredLogs.map((log) => (
              <Card
                key={log.id}
                hoverable
                className={clsx('cursor-pointer border', getLevelBgColor(log.level))}
                onClick={() =>
                  setExpandedLog(expandedLog === log.id ? null : log.id)
                }
              >
                <div className="space-y-2">
                  {/* Main Log Line */}
                  <div className="flex items-start gap-3">
                    {getLevelIcon(log.level)}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-mono text-text-secondary">
                          {formatTime(log.timestamp)}
                        </span>
                        <Badge size="sm" variant={getLevelColor(log.level)}>
                          {log.level}
                        </Badge>
                        {log.category && (
                          <Badge size="sm" variant="info">
                            {log.category}
                          </Badge>
                        )}
                        {log.strategy && (
                          <Badge size="sm" variant="primary">
                            {log.strategy}
                          </Badge>
                        )}
                      </div>
                      <p className="text-sm text-text-primary mt-2 break-words">
                        {log.message}
                      </p>
                    </div>
                  </div>

                  {/* Expanded Details */}
                  {expandedLog === log.id && log.details && (
                    <div className="mt-3 pt-3 border-t border-current/20">
                      <p className="text-xs text-text-secondary font-semibold mb-2">
                        Details:
                      </p>
                      <p className="text-sm text-text-secondary break-words bg-bg-secondary/50 p-2 rounded">
                        {log.details}
                      </p>
                    </div>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>

      {/* Log Info */}
      <Card>
        <div className="space-y-2">
          <h4 className="text-sm font-semibold text-text-primary mb-3">
            Log Information
          </h4>
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs text-text-secondary">
            <div>
              <p className="font-semibold text-text-primary">Last Update</p>
              <p className="text-text-secondary">
                {logs.length > 0
                  ? new Date(logs[0].timestamp).toLocaleString('en-IN')
                  : 'N/A'}
              </p>
            </div>
            <div>
              <p className="font-semibold text-text-primary">Log Retention</p>
              <p className="text-text-secondary">Session based</p>
            </div>
            <div>
              <p className="font-semibold text-text-primary">Auto-refresh</p>
              <p className="text-text-secondary">Every 2 seconds</p>
            </div>
          </div>
        </div>
      </Card>
    </div>
  )
}

export default Logs
