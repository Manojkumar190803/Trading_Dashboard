/**
 * Market Hours Utility
 * Handles IST-based trading hours (9:15 AM - 3:30 PM, Mon-Fri)
 */

/**
 * Check if current time is within market hours (IST)
 * Market hours: 9:15 AM - 3:30 PM, Monday-Friday
 * @returns true if market is open, false otherwise
 */
export const isMarketOpen = (): boolean => {
  const parts = getISTDateTimeParts(new Date())
  const hours = Number(parts.hour)
  const minutes = Number(parts.minute)
  const dayOfWeek = weekdayNumber(parts.weekday)
  
  // Check if it's a weekday (Mon-Fri = 1-5)
  const isWeekday = dayOfWeek >= 1 && dayOfWeek <= 5
  
  if (!isWeekday) return false
  
  // Check if time is between 9:15 AM and 3:30 PM
  // Market opens at 9:15 AM
  if (hours < 9) return false
  if (hours === 9 && minutes < 15) return false
  
  // Market closes at 3:30 PM (15:30)
  if (hours > 15) return false
  if (hours === 15 && minutes > 30) return false
  
  return true
}

/**
 * Get seconds until market opens (next trading day, 9:15 AM IST)
 * @returns number of seconds until market opens
 */
export const getSecondsUntilMarketOpen = (): number => {
  const now = new Date()
  const parts = getISTDateTimeParts(now)
  const currentIST = Date.UTC(
    Number(parts.year), Number(parts.month) - 1, Number(parts.day),
    Number(parts.hour), Number(parts.minute), Number(parts.second), now.getMilliseconds()
  )
  const nextOpen = new Date(Date.UTC(
    Number(parts.year), Number(parts.month) - 1, Number(parts.day), 9, 15
  ))

  if (weekdayNumber(parts.weekday) === 0 || weekdayNumber(parts.weekday) === 6 || currentIST >= nextOpen.getTime()) {
    nextOpen.setUTCDate(nextOpen.getUTCDate() + 1)
  }
  while (nextOpen.getUTCDay() === 0 || nextOpen.getUTCDay() === 6) {
    nextOpen.setUTCDate(nextOpen.getUTCDate() + 1)
  }

  const diffMs = nextOpen.getTime() - currentIST
  return Math.max(0, Math.floor(diffMs / 1000))
}

/**
 * Get current market status with message
 * @returns object with status, message, and seconds
 */
export const getMarketStatus = (): { 
  isOpen: boolean
  message: string
  secondsUntilChange: number
} => {
  const now = new Date()
  const parts = getISTDateTimeParts(now)
  const open = isMarketOpen()
  
  if (!open) {
    const secondsUntil = getSecondsUntilMarketOpen()
    const hours = Math.floor(secondsUntil / 3600)
    const mins = Math.floor((secondsUntil % 3600) / 60)
    
    return {
      isOpen: false,
      message: `Market closed. Opens in ${hours}h ${mins}m`,
      secondsUntilChange: secondsUntil,
    }
  }
  
  // Calculate seconds until market close (3:30 PM)
  const currentIST = Date.UTC(
    Number(parts.year), Number(parts.month) - 1, Number(parts.day),
    Number(parts.hour), Number(parts.minute), Number(parts.second), now.getMilliseconds()
  )
  const closeTime = Date.UTC(Number(parts.year), Number(parts.month) - 1, Number(parts.day), 15, 30)
  const secondsUntil = Math.max(0, Math.floor((closeTime - currentIST) / 1000))
  const mins = Math.floor(secondsUntil / 60)
  
  return {
    isOpen: true,
    message: `Market open. Closes in ${mins} minutes`,
    secondsUntilChange: secondsUntil,
  }
}

/**
 * Format time until market change
 * @param seconds - number of seconds
 * @returns formatted string like "2h 30m" or "45m"
 */
export const formatTimeUntilMarketChange = (seconds: number): string => {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  
  if (hours > 0) {
    return `${hours}h ${minutes}m`
  }
  return `${minutes}m`
}

const getISTDateTimeParts = (date: Date): Record<string, string> => {
  return Object.fromEntries(
    new Intl.DateTimeFormat('en-GB', {
      timeZone: 'Asia/Kolkata',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      weekday: 'short',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(date).map(({ type, value }) => [type, value])
  )
}

const weekdayNumber = (weekday: string): number => {
  return ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(weekday)
}
