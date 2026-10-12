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
  const now = new Date()
  
  // Get IST time (UTC+5:30)
  const istTime = new Date(now.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }))
  
  const hours = istTime.getHours()
  const minutes = istTime.getMinutes()
  const dayOfWeek = istTime.getDay() // 0 = Sunday, 1 = Monday, ..., 5 = Friday, 6 = Saturday
  
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
  const istTime = new Date(now.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }))
  
  // Create market open time for tomorrow or today
  let nextOpen = new Date(istTime)
  nextOpen.setHours(9, 15, 0, 0)
  
  // If today is after market close or it's weekend, set to next weekday
  const dayOfWeek = istTime.getDay()
  
  if (istTime.getTime() > nextOpen.getTime()) {
    // After market close today, move to tomorrow
    nextOpen.setDate(nextOpen.getDate() + 1)
  }
  
  // Skip weekends
  const daysToAdd = nextOpen.getDay() === 0 ? 1 : (nextOpen.getDay() === 6 ? 2 : 0)
  if (daysToAdd > 0) {
    nextOpen.setDate(nextOpen.getDate() + daysToAdd)
  }
  
  const diffMs = nextOpen.getTime() - now.getTime()
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
  const istTime = new Date(now.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }))
  
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
  const closeTime = new Date(istTime)
  closeTime.setHours(15, 30, 0, 0)
  const secondsUntil = Math.max(0, Math.floor((closeTime.getTime() - now.getTime()) / 1000))
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
