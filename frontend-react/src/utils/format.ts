import Papa from 'papaparse'

/**
 * Format a number as currency (INR)
 */
export const formatCurrency = (value: number, decimals = 0): string => {
  const formatted = new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value)
  return formatted
}

/**
 * Format a number with commas
 */
export const formatNumber = (value: number, decimals = 2): string => {
  return new Intl.NumberFormat('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value)
}

/**
 * Format percentage
 */
export const formatPercent = (value: number, decimals = 2): string => {
  return `${formatNumber(value, decimals)}%`
}

/**
 * Determine color class for a numeric value (red if negative, green if positive)
 */
export const getValueColor = (value: number): 'text-accent-red' | 'text-accent-green' | 'text-text-secondary' => {
  if (value > 0) return 'text-accent-green'
  if (value < 0) return 'text-accent-red'
  return 'text-text-secondary'
}

/**
 * Determine background color class for a numeric value
 */
export const getValueBgColor = (value: number): string => {
  if (value > 0) return 'bg-accent-green/10 border-accent-green/30'
  if (value < 0) return 'bg-accent-red/10 border-accent-red/30'
  return 'bg-bg-surface border-bg-tertiary'
}

/**
 * Get status badge color
 */
export const getStatusColor = (
  status: string
): { bg: string; text: string; dot: string } => {
  const statusMap: Record<string, { bg: string; text: string; dot: string }> = {
    running: {
      bg: 'bg-accent-green/10',
      text: 'text-accent-green',
      dot: 'bg-accent-green',
    },
    paused: {
      bg: 'bg-accent-yellow/10',
      text: 'text-accent-yellow',
      dot: 'bg-accent-yellow',
    },
    stopped: {
      bg: 'bg-accent-red/10',
      text: 'text-accent-red',
      dot: 'bg-accent-red',
    },
    Ready: {
      bg: 'bg-accent-green/10',
      text: 'text-accent-green',
      dot: 'bg-accent-green',
    },
    READY: {
      bg: 'bg-accent-green/10',
      text: 'text-accent-green',
      dot: 'bg-accent-green',
    },
    active: {
      bg: 'bg-accent-green/10',
      text: 'text-accent-green',
      dot: 'bg-accent-green',
    },
    inactive: {
      bg: 'bg-accent-red/10',
      text: 'text-accent-red',
      dot: 'bg-accent-red',
    },
    WARNING: {
      bg: 'bg-accent-yellow/10',
      text: 'text-accent-yellow',
      dot: 'bg-accent-yellow',
    },
    FAILED: {
      bg: 'bg-accent-red/10',
      text: 'text-accent-red',
      dot: 'bg-accent-red',
    },
  }

  return statusMap[status] || {
    bg: 'bg-accent-red/10',
    text: 'text-accent-red',
    dot: 'bg-accent-red',
  }
}

/**
 * Get alert category color
 */
export const getAlertCategoryColor = (category: string): string => {
  const categoryColorMap: Record<string, string> = {
    ENTRY: 'bg-accent-green/10 border-accent-green/30 text-accent-green',
    EXIT: 'bg-accent-green/10 border-accent-green/30 text-accent-green',
    TARGET: 'bg-accent-green/10 border-accent-green/30 text-accent-green',
    PENDING_ENTRY: 'bg-accent-yellow/10 border-accent-yellow/30 text-accent-yellow',
    ORDER: 'bg-accent-blue/10 border-accent-blue/30 text-accent-blue',
    PROTECTIVE_SL: 'bg-accent-yellow/10 border-accent-yellow/30 text-accent-yellow',
    TSL: 'bg-accent-yellow/10 border-accent-yellow/30 text-accent-yellow',
    CANCEL: 'bg-accent-red/10 border-accent-red/30 text-accent-red',
    SL: 'bg-accent-red/10 border-accent-red/30 text-accent-red',
    RISK: 'bg-accent-red/10 border-accent-red/30 text-accent-red',
    REJECT: 'bg-accent-red/10 border-accent-red/30 text-accent-red',
    FAILED: 'bg-accent-red/10 border-accent-red/30 text-accent-red',
    ERROR: 'bg-accent-red/10 border-accent-red/30 text-accent-red',
    UNCERTAIN_ENTRY: 'bg-accent-red/10 border-accent-red/30 text-accent-red',
    SIGNAL: 'bg-accent-cyan/10 border-accent-cyan/30 text-accent-cyan',
  }

  return categoryColorMap[category] || 'bg-bg-surface border-bg-tertiary text-text-secondary'
}

/**
 * Parse CSV string into objects
 */
export const parseCSV = async (csvText: string): Promise<Record<string, any>[]> => {
  return new Promise((resolve, reject) => {
    Papa.parse(csvText, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => {
        resolve(results.data as Record<string, any>[])
      },
      error: (error: any) => {
        reject(error)
      },
    })
  })
}

/**
 * Format timestamp to readable format
 */
export const formatTime = (timestamp: string): string => {
  try {
    const date = new Date(timestamp)
    return date.toLocaleTimeString('en-IN', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    })
  } catch {
    return timestamp
  }
}

/**
 * Format full datetime
 */
export const formatDateTime = (timestamp: string): string => {
  try {
    const date = new Date(timestamp)
    return date.toLocaleString('en-IN', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
    })
  } catch {
    return timestamp
  }
}

/**
 * Truncate text with ellipsis
 */
export const truncateText = (text: string, maxLength: number = 50): string => {
  if (text.length <= maxLength) return text
  return text.slice(0, maxLength) + '...'
}

/**
 * Convert snake_case to Title Case
 */
export const toTitleCase = (text: string): string => {
  return text
    .replace(/_/g, ' ')
    .split(' ')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ')
}
