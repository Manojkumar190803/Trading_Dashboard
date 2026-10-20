/**
 * Simple Express API server for React dashboard
 * Handles analytics reset and file operations
 */

import express from 'express'
import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const app = express()
const PORT = 4000

// Determine LOGS_DIR: check env var, then default to ../logs (project root)
const LOGS_DIR = process.env.LOGS_DIR || path.join(__dirname, '..', 'logs')

// Ensure logs directory exists
if (!fs.existsSync(LOGS_DIR)) {
  console.error(`❌ LOGS_DIR does not exist: ${LOGS_DIR}`)
  console.error(`Please set LOGS_DIR environment variable or ensure ../logs directory exists`)
} else {
  console.log(`✅ LOGS_DIR configured: ${LOGS_DIR}`)
}

app.use(express.json())

// CORS middleware - handle preflight requests and set CORS headers on all responses
app.use((req, res, next) => {
  res.setHeader('Access-Control-Allow-Origin', '*')
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS, PUT, DELETE')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization')
  res.setHeader('Access-Control-Max-Age', '3600')
  
  // Handle preflight OPTIONS request
  if (req.method === 'OPTIONS') {
    res.status(200).end()
    return
  }
  
  next()
})

/**
 * Serve log files (.txt, .csv, .json) from the logs directory
 * This enables React frontend to fetch strategy data files
 */
app.get('/logs/:filename', (req, res) => {
  try {
    const { filename } = req.params
    
    // Only allow .txt, .csv, and .json files
    if (!filename.match(/\.(txt|csv|json)$/)) {
      res.status(403).json({ error: 'Invalid file type' })
      return
    }
    
    const filePath = path.join(LOGS_DIR, filename)
    
    // Security: ensure the file is within LOGS_DIR (prevent path traversal)
    const normalizedPath = path.normalize(filePath)
    const normalizedLogsDir = path.normalize(LOGS_DIR)
    if (!normalizedPath.startsWith(normalizedLogsDir)) {
      res.status(403).json({ error: 'Access denied' })
      return
    }
    
    // Check if file exists
    if (!fs.existsSync(filePath)) {
      console.log(`[logs] File not found: ${filename}`)
      res.status(404).json({ error: 'File not found' })
      return
    }
    
    // Read and serve the file
    const content = fs.readFileSync(filePath, 'utf-8')
    
    // Set appropriate content type
    let contentType = 'application/json'
    if (filename.endsWith('.txt')) contentType = 'text/plain'
    if (filename.endsWith('.csv')) contentType = 'text/csv'
    
    // CORS headers to allow requests from React (port 3000)
    res.setHeader('Access-Control-Allow-Origin', '*')
    res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS')
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type')
    res.setHeader('Content-Type', contentType)
    res.setHeader('Cache-Control', 'no-cache, no-store, must-revalidate')
    res.setHeader('Pragma', 'no-cache')
    res.setHeader('Expires', '0')
    
    console.log(`[logs] Serving ${filename} (${content.length} bytes)`)
    res.send(content)
  } catch (error) {
    console.error('[logs] Error serving file:', error)
    res.status(500).json({ error: 'Error reading file' })
  }
})

/**
 * Health check endpoint
 */
app.get('/health', (req, res) => {
  res.json({ status: 'ok', timestamp: new Date().toISOString() })
})

/**
 * Reset analytics by clearing the analytics_trades.csv file and writing reset timestamp
 * This prevents the Streamlit backend from regenerating old trades
 */
app.post('/api/analytics/reset', (req, res) => {
  try {
    const analyticsFile = path.join(LOGS_DIR, 'analytics_trades.csv')
    const resetTimestampFile = path.join(LOGS_DIR, 'analytics_reset.txt')
    const now = new Date()
    const isoTime = now.toISOString()

    // Clear the analytics file - write header only
    const header = 'timestamp,strategy,pnl,source,message\n'
    fs.writeFileSync(analyticsFile, header, 'utf8')
    console.log(`Analytics file cleared at ${isoTime}`)

    // Write reset timestamp in format: YYYY-MM-DD HH:MM:SS
    // This matches the Streamlit backend's expected format
    const year = now.getUTCFullYear()
    const month = String(now.getUTCMonth() + 1).padStart(2, '0')
    const day = String(now.getUTCDate()).padStart(2, '0')
    const hours = String(now.getUTCHours()).padStart(2, '0')
    const minutes = String(now.getUTCMinutes()).padStart(2, '0')
    const seconds = String(now.getUTCSeconds()).padStart(2, '0')
    const resetTimestamp = `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`
    
    fs.writeFileSync(resetTimestampFile, resetTimestamp, 'utf8')
    console.log(`Reset timestamp written: "${resetTimestamp}" at ${isoTime}`)

    res.json({
      success: true,
      message: 'Analytics data cleared successfully',
      timestamp: isoTime,
    })
  } catch (error) {
    console.error('Error resetting analytics:', error)
    res.status(500).json({
      success: false,
      error: error instanceof Error ? error.message : 'Failed to reset analytics',
    })
  }
})

/** Return the durable cutoff used to hide previously triggered CSV alerts. */
app.get('/api/alerts/reset-status', (req, res) => {
  try {
    const resetFile = path.join(LOGS_DIR, 'triggered_alerts_reset.json')
    const resetState = fs.existsSync(resetFile)
      ? JSON.parse(fs.readFileSync(resetFile, 'utf8'))
      : { resetAt: '', dismissedIds: [] }
    res.json({
      success: true,
      resetAt: resetState.resetAt || '',
      dismissedIds: Array.isArray(resetState.dismissedIds) ? resetState.dismissedIds : [],
    })
  } catch (error) {
    console.error('Error reading triggered-alert reset marker:', error)
    res.status(500).json({ success: false, error: 'Failed to read triggered-alert reset marker' })
  }
})

/** Hide existing triggered alerts without deleting their CSV audit history. */
app.post('/api/alerts/reset', (req, res) => {
  try {
    const alertsFile = path.join(LOGS_DIR, 'ema21_triggered_alerts.json')
    const resetFile = path.join(LOGS_DIR, 'triggered_alerts_reset.json')
    const resetAt = new Date().toISOString()
    const dismissedIds = Array.isArray(req.body?.alertIds)
      ? [...new Set(req.body.alertIds.filter((id) => typeof id === 'string'))]
      : []

    fs.writeFileSync(resetFile, JSON.stringify({ resetAt, dismissedIds }, null, 2), 'utf8')
    const emptyAlerts = { alerts: [] }
    fs.writeFileSync(alertsFile, JSON.stringify(emptyAlerts, null, 2), 'utf8')
    console.log(`Triggered alerts hidden from ${resetAt}`)

    res.json({
      success: true,
      message: 'Existing triggered alerts hidden successfully',
      resetAt,
      dismissedIds,
    })
  } catch (error) {
    console.error('Error resetting alerts:', error)
    res.status(500).json({
      success: false,
      error: error instanceof Error ? error.message : 'Failed to reset alerts',
    })
  }
})

/**
 * Export instruments config to JSON file for Python backend to consume
 * This creates the bridge between React dashboard and Python strategy engine
 */
app.post('/api/instruments/export', (req, res) => {
  try {
    const instruments = req.body.instruments || []
    const configFile = path.join(LOGS_DIR, 'instruments_config.json')
    
    const config = {
      exported_at: new Date().toISOString(),
      trailingStopsConfig: req.body.trailingStopsConfig || {},
      instruments: instruments.map(inst => ({
        id: inst.id,
        name: inst.name,
        brokerSymbol: inst.brokerSymbol,
        strategy: inst.strategy,
        status: inst.status,
        premiumMinPrice: inst.premiumMinPrice,
        premiumMaxPrice: inst.premiumMaxPrice,
        maxInitialRiskPoints: inst.maxInitialRiskPoints,
        calculatedLotSize: inst.calculatedLotSize,
        lotSizeAdjustment: inst.lotSizeAdjustment,
        entryCutoffTime: inst.entryCutoffTime,
        monitoringStartTime: inst.monitoringStartTime,
        monitoringEndTime: inst.monitoringEndTime,
      }))
    }
    
    fs.writeFileSync(configFile, JSON.stringify(config, null, 2), 'utf8')
    console.log(`Instruments config exported at ${config.exported_at}`)
    
    res.json({
      success: true,
      message: 'Instruments exported successfully',
      count: instruments.length,
      timestamp: config.exported_at,
    })
  } catch (error) {
    console.error('Error exporting instruments:', error)
    res.status(500).json({
      success: false,
      error: error instanceof Error ? error.message : 'Failed to export instruments',
    })
  }
})

/**
 * Get running strategies status from a status file
 * Updated by the Python daemon
 */
app.get('/api/instruments/status', (req, res) => {
  try {
    const statusFile = path.join(LOGS_DIR, 'strategies_status.json')
    
    if (fs.existsSync(statusFile)) {
      const status = JSON.parse(fs.readFileSync(statusFile, 'utf8'))
      res.json(status)
    } else {
      res.json({
        updated_at: new Date().toISOString(),
        running_strategies: {},
        message: 'No strategies running'
      })
    }
  } catch (error) {
    console.error('Error reading strategies status:', error)
    res.status(500).json({
      success: false,
      error: error instanceof Error ? error.message : 'Failed to read status',
    })
  }
})

/**
 * Proxy endpoint to serve logs
 */
app.get('/api/logs/:filename', (req, res) => {
  try {
    const filename = req.params.filename
    // Security: only allow alphanumeric, dots, underscores, and hyphens
    if (!/^[a-zA-Z0-9._-]+$/.test(filename)) {
      return res.status(400).json({ error: 'Invalid filename' })
    }

    const filepath = path.resolve(LOGS_DIR, filename)

    // Security: prevent directory traversal
    if (!filepath.startsWith(path.resolve(LOGS_DIR))) {
      return res.status(403).json({ error: 'Access denied' })
    }

    if (fs.existsSync(filepath)) {
      res.sendFile(filepath)
    } else {
      res.status(404).json({ error: 'File not found' })
    }
  } catch (error) {
    console.error('Error serving log file:', error)
    res.status(500).json({ error: 'Internal server error' })
  }
})

/**
 * Proxy analytics endpoints to strategy_worker backend
 */
app.get('/api/analytics/summary', async (req, res) => {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://strategy_worker:5003'
    const response = await fetch(`${backendUrl}/api/analytics/summary`)
    const data = await response.json()
    res.json(data)
  } catch (error) {
    console.error('Error proxying analytics/summary:', error)
    res.status(500).json({ error: 'Failed to fetch analytics summary' })
  }
})

app.get('/api/analytics/daily', async (req, res) => {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://strategy_worker:5003'
    const query = new URLSearchParams()
    if (typeof req.query.year === 'string') query.set('year', req.query.year)
    if (typeof req.query.month === 'string') query.set('month', req.query.month)
    const suffix = query.size ? `?${query.toString()}` : ''
    const response = await fetch(`${backendUrl}/api/analytics/daily${suffix}`)
    const data = await response.json()
    res.json(data)
  } catch (error) {
    console.error('Error proxying analytics/daily:', error)
    res.status(500).json({ error: 'Failed to fetch daily analytics' })
  }
})

app.post('/api/analytics/daily/reset', async (req, res) => {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://strategy_worker:5003'
    const query = new URLSearchParams()
    if (typeof req.query.year === 'string') query.set('year', req.query.year)
    if (typeof req.query.month === 'string') query.set('month', req.query.month)
    const suffix = query.size ? `?${query.toString()}` : ''
    const response = await fetch(`${backendUrl}/api/analytics/daily/reset${suffix}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body),
    })
    const data = await response.json()
    res.json(data)
  } catch (error) {
    console.error('Error proxying analytics/daily/reset:', error)
    res.status(500).json({ error: 'Failed to reset daily analytics' })
  }
})

app.get('/api/symbols/search', async (req, res) => {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://strategy_worker:5003'
    const query = req.query.q || ''
    const strategy = req.query.strategy || ''
    const response = await fetch(`${backendUrl}/api/symbols/search?q=${query}&strategy=${strategy}`)
    const data = await response.json()
    res.json(data)
  } catch (error) {
    console.error('Error proxying symbols/search:', error)
    res.status(500).json({ error: 'Failed to search symbols' })
  }
})

app.post('/api/symbols/validate', async (req, res) => {
  try {
    const backendUrl = process.env.BACKEND_URL || 'http://strategy_worker:5003'
    const response = await fetch(`${backendUrl}/api/symbols/validate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req.body),
    })
    const data = await response.json()
    res.json(data)
  } catch (error) {
    console.error('Error proxying symbols/validate:', error)
    res.status(500).json({ error: 'Failed to validate symbol' })
  }
})

app.listen(PORT, () => {
  console.log(`Analytics API server running on port ${PORT}`)
  console.log(`Logs directory: ${LOGS_DIR}`)
})
