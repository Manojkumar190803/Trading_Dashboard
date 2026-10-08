/**
 * CSV Export Utilities
 * Generate and download CSV files from data arrays
 */

export interface CSVExportOptions {
  filename: string
  headers: string[]
  rows: (string | number)[][]
}

/**
 * Convert data to CSV format and trigger download
 */
export const downloadCSV = (options: CSVExportOptions) => {
  const { filename, headers, rows } = options

  // Convert headers and rows to CSV format
  const csvContent = [
    headers.map((h) => `"${h}"`).join(','),
    ...rows.map((row) =>
      row
        .map((cell) => {
          // Escape quotes and wrap in quotes if contains comma or quote
          const str = String(cell)
          if (str.includes(',') || str.includes('"') || str.includes('\n')) {
            return `"${str.replace(/"/g, '""')}"`
          }
          return `"${str}"`
        })
        .join(',')
    ),
  ].join('\n')

  // Create blob and download
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const link = document.createElement('a')
  const url = URL.createObjectURL(blob)

  link.setAttribute('href', url)
  link.setAttribute('download', `${filename}_${new Date().toISOString().split('T')[0]}.csv`)
  link.style.visibility = 'hidden'

  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

/**
 * Export positions data as CSV
 */
export const exportPositionsCSV = (positions: any[]) => {
  if (positions.length === 0) {
    alert('No positions to export')
    return
  }

  const headers = ['Symbol', 'Entry Price', 'Current Price', 'Quantity', 'P&L', 'P&L %', 'Status']

  const rows = positions.map((p) => [
    p.symbol,
    p.entryPrice,
    p.currentPrice,
    p.quantity,
    p.pnl,
    p.pnlPercent,
    p.pnl > 0 ? 'PROFIT' : 'LOSS',
  ])

  downloadCSV({
    filename: 'positions',
    headers,
    rows,
  })
}

/**
 * Export execution log data as CSV
 */
export const exportExecutionLogCSV = (executions: any[]) => {
  if (executions.length === 0) {
    alert('No executions to export')
    return
  }

  const headers = ['Timestamp', 'Order ID', 'Symbol', 'Action', 'Quantity', 'Price', 'Type', 'Status']

  const rows = executions.map((e) => [
    e.timestamp,
    e.orderId,
    e.symbol,
    e.action,
    e.quantity,
    e.price,
    e.type,
    e.status,
  ])

  downloadCSV({
    filename: 'execution-log',
    headers,
    rows,
  })
}

/**
 * Export live orders data as CSV
 */
export const exportOrdersCSV = (orders: any[]) => {
  if (orders.length === 0) {
    alert('No orders to export')
    return
  }

  const headers = [
    'Symbol',
    'Action',
    'Quantity',
    'Filled Qty',
    'Price',
    'Trigger Price',
    'Broker Order ID',
    'Status',
    'Timestamp',
  ]

  const rows = orders.map((o) => [
    o.symbol,
    o.action,
    o.quantity,
    o.filledQuantity,
    o.price,
    o.triggerPrice,
    o.orderId,
    o.status,
    o.timestamp,
  ])

  downloadCSV({
    filename: 'orders',
    headers,
    rows,
  })
}

/**
 * Export analytics summary and trades data as CSV
 */
export const exportAnalyticsCSV = (summary: any, trades: any[]) => {
  if (trades.length === 0) {
    alert('No trade data to export')
    return
  }

  const headers = [
    'Timestamp',
    'Strategy',
    'P&L',
    'Source',
    'Message',
    'Winning',
    'Win Rate %',
    'Profit Factor',
    'Avg P&L/Trade',
  ]

  const rows = trades.map((trade, index) => [
    trade.timestamp,
    trade.strategy,
    trade.pnl,
    trade.source,
    trade.message,
    trade.pnl > 0 ? 'YES' : 'NO',
    summary.win_rate.toFixed(2),
    summary.profit_factor.toFixed(2),
    summary.expectancy.toFixed(2),
  ])

  downloadCSV({
    filename: 'analytics-report',
    headers,
    rows,
  })
}

/**
 * Reset analytics by clearing the analytics file
 * Returns success status and also clears browser cache for analytics data
 */
export const resetAnalytics = async (): Promise<boolean> => {
  try {
    const confirmed = window.confirm(
      'Are you sure you want to reset all analytics data? This action cannot be undone.'
    )
    if (!confirmed) return false

    // Add cache-busting parameter to ensure fresh data
    const timestamp = Date.now()
    const response = await fetch(`/api/analytics/reset?t=${timestamp}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      cache: 'no-store', // Force no caching
    })

    if (response.ok) {
      console.log('Analytics data reset successfully')
      return true
    }
    throw new Error('Failed to reset analytics')
  } catch (error) {
    console.error('Analytics reset error:', error)
    alert('Failed to reset analytics. Please try again.')
    return false
  }
}

/**
 * Reset logs by clearing the logs data (local state management)
 * Used for clearing logs from the logs page
 */
export const resetLogs = async (): Promise<boolean> => {
  try {
    const confirmed = window.confirm(
      'Are you sure you want to clear all logs? This action cannot be undone.'
    )
    if (!confirmed) return false

    // Logs are managed in local state, so clearing is done in the component
    // This function provides confirmation dialog consistency with analytics reset
    console.log('Logs reset initiated')
    return true
  } catch (error) {
    console.error('Logs reset error:', error)
    alert('Failed to reset logs. Please try again.')
    return false
  }
}
