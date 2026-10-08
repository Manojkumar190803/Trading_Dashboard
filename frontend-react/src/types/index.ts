export interface StrategyAlert {
  timestamp: string
  category: 'SIGNAL' | 'PENDING_ENTRY' | 'ENTRY' | 'EXIT' | 'TARGET' | 'SL' | 'CANCEL' | 'ORDER' | 'PROTECTIVE_SL' | 'TSL' | 'RISK' | 'REJECT' | 'FAILED' | 'ERROR' | 'UNCERTAIN_ENTRY'
  message: string
  strategy: string
  symbol: string
}

export interface Position {
  option_symbol: string
  option_type: 'CE' | 'PE'
  quantity: number
  entry_price: number
  entry_time: string
  option_stop_level: number
  option_entry_trigger: number
  option_risk_points: number
  current_price?: number
  trailing_sl_level?: number
  progress_status: string
  pnl?: number
  pnl_percent?: number
}

export interface Trade {
  timestamp: string
  strategy: string
  pnl: number
  source: string
  message: string
}

export interface EquityCurvePoint {
  datetime: string
  total_pnl: number
}

export interface AnalyticsSummary {
  completed_trades: number
  gross_profit: number
  gross_loss: number
  winning_trades: number
  expectancy: number
  win_rate: number
  profit_factor: number
}

export interface AccountData {
  timestamp: string
  mode?: 'live' | 'analyzer'
  engine_status?: string
  positions: any[]
  orders: any[]
  account: Record<string, any>
}

export interface DashboardMetrics {
  net_mtm: number
  available_margin: number
  active_trades: number
  engine_status: string
  openalgo_mode?: 'live' | 'analyzer'
}

export interface Order {
  order_id: string
  symbol: string
  side: 'BUY' | 'SELL'
  quantity: number
  order_type: 'STOP_LIMIT' | 'MARKET' | 'LIMIT'
  status: 'OPEN' | 'FILLED' | 'CANCELLED' | 'REJECTED'
  price: number
  timestamp: string
  message?: string
}

export interface LogEntry {
  timestamp: string
  level: 'INFO' | 'WARNING' | 'ERROR' | 'SUCCESS'
  message: string
  category?: string
  strategy?: string
}

export interface PreMarketCheck {
  name: string
  status: 'READY' | 'WARNING' | 'FAILED'
  message?: string
}

export interface Instrument {
  id: string
  name: string
  brokerSymbol: string
  monitoringStartTime: string
  monitoringEndTime: string
  lotSizeAdjustment: number
  strikeStep: number
  strategy: '21EMA' | 'HD' | 'CD' | 'TC' | '2BC' | 'BO'
  productType: 'INTRADAY' // Fixed, not editable
  status: boolean
  createdAt: string
  updatedAt: string
  lotSize?: number // Calculated from instrument name
  atmPrice?: number // Locked ATM price for 21EMA strategy
  minPremium?: number // Minimum premium range for HD, CD, TC, 2BC, BO
  maxPremium?: number // Maximum premium range for HD, CD, TC, 2BC, BO
  // Trailing Stoploss Mechanism (applied to all strategies)
  breakeven_rr?: number // Move stop to entry at 1R milestone (default: 1.0)
  trail_step_rr?: number // Advance stop by this amount at each 0.5R milestone (default: 0.5)
  max_initial_risk_points?: number // Max allowed initial risk in premium points (default: 20.0)
}
