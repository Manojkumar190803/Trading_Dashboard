import { parseCSV } from './format'

/**
 * Fetch file from public/logs directory or relative path
 */
export const fetchLogFile = async (filePath: string): Promise<string> => {
  try {
    // Try fetching from public/logs first
    let response = await fetch(`/logs/${filePath}`)
    
    if (!response.ok) {
      // Fallback to relative path
      response = await fetch(`/../../logs/${filePath}`)
    }
    
    if (!response.ok) {
      throw new Error(`File not found: ${filePath}`)
    }
    
    return await response.text()
  } catch (error) {
    console.error(`Error fetching ${filePath}:`, error)
    throw error
  }
}

/**
 * Fetch and parse CSV file
 */
export const fetchAndParseCSV = async (
  filePath: string
): Promise<Record<string, any>[]> => {
  const csvText = await fetchLogFile(filePath)
  return parseCSV(csvText)
}

/**
 * Fetch and parse JSON file
 */
export const fetchJSON = async (filePath: string): Promise<any> => {
  try {
    let response = await fetch(`/logs/${filePath}`)
    
    if (!response.ok) {
      response = await fetch(`/../../logs/${filePath}`)
    }
    
    if (!response.ok) {
      throw new Error(`File not found: ${filePath}`)
    }
    
    return await response.json()
  } catch (error) {
    console.error(`Error fetching JSON ${filePath}:`, error)
    throw error
  }
}

/**
 * Get today's date formatted as YYYYMMDD
 */
export const getTodayDateString = (): string => {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}${month}${day}`
}

/**
 * Get today's date in YYYY-MM-DD format
 */
export const getTodayFormatted = (): string => {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/**
 * Retry failed fetch with exponential backoff
 */
export const fetchWithRetry = async (
  filePath: string,
  maxRetries = 3,
  delayMs = 100
): Promise<string> => {
  let lastError: any

  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fetchLogFile(filePath)
    } catch (error) {
      lastError = error
      if (i < maxRetries - 1) {
        await new Promise((resolve) => setTimeout(resolve, delayMs * Math.pow(2, i)))
      }
    }
  }

  throw lastError
}

/**
 * Watch file for changes (polling-based)
 * Returns cleanup function to stop watching
 */
export const watchFile = (
  filePath: string,
  callback: (data: string) => void,
  intervalMs = 2000
): (() => void) => {
  let lastContent = ''
  let isRunning = true

  const poll = async () => {
    if (!isRunning) return

    try {
      const content = await fetchLogFile(filePath)
      if (content !== lastContent) {
        lastContent = content
        callback(content)
      }
    } catch (error) {
      console.debug(`Error polling ${filePath}:`, error)
    }

    if (isRunning) {
      setTimeout(poll, intervalMs)
    }
  }

  poll()

  return () => {
    isRunning = false
  }
}
