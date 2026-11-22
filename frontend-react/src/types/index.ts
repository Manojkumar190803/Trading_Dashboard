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

export interface DashboardMetrics {
  net_mtm: number
  available_margin: number
  active_trades: number
  engine_status: 'running' | 'paused' | 'stopped'
  last_update: string
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
  entryCutoffTime?: string
  lotSizeAdjustment: number
  strategy: '21EMA' | 'HD' | 'CD' | 'TC' | '2BC' | 'BO'
  productType: 'INTRADAY' // Fixed, not editable
  status: boolean
  createdAt: string
  updatedAt: string
  lotSize?: number // Calculated from instrument name
  trailingStepRR?: number // Risk Ratio step for trailing (0.25, 0.5, 1.0, etc)
  premiumMinPrice?: number // Minimum premium price (non-21EMA strategies)
  premiumMaxPrice?: number // Maximum premium price (non-21EMA strategies)
  premiumOptionStrike?: number // ATM strike price for options
  maxInitialRiskPoints?: number // Maximum allowed initial risk in points (default 20, override to 23, 25, etc)
  partialBookingEnabled?: boolean
  partialBookingRR?: number
  partialBookingLots?: number
  partialBookingIntervalRR?: number
  maxLosingTradesPerDay: number
  executionMode: 'LIVE' | 'TEST'
}

export interface TestPosition {
  symbol: string
  quantity: number
  average_price: number
  ltp: number
  unrealized_pnl: number
  protective_sl?: number | null
  instrument_id: string
  instrument_name: string
  strategy: string
  execution_mode: 'TEST'
}

export interface TestOrder {
  orderid: string
  symbol: string
  action: 'BUY' | 'SELL'
  quantity: number
  pricetype: string
  price: number
  trigger_price: number
  order_status: string
  filled_quantity: number
  average_price?: number | null
  timestamp: string
  execution_mode: 'TEST'
  instrument_name: string
  strategy: string
}

export interface TestTrade {
  id: string
  symbol: string
  entry_time: string
  exit_time: string
  entry_price: number
  exit_price: number
  quantity: number
  pnl: number
  status: string
  execution_mode: 'TEST'
  instrument_name: string
  strategy: string
}

export interface TestAlert {
  id: string
  timestamp: string
  execution_mode: 'TEST'
  instrument_name: string
  strategy: string
  category: string
  message: string
}

export interface TestTradingActivity {
  execution_mode: 'TEST'
  positions: TestPosition[]
  orders: TestOrder[]
  trades: TestTrade[]
  alerts: TestAlert[]
  summary: {
    open_positions: number
    open_pnl: number
    realized_pnl: number
    net_pnl: number
    completed_trades: number
    updated_at: string
  }
}

export interface TrailingStopsConfig {
  breakEvenRR: number // Breakeven milestone in Risk Ratio (default 1.25)
  trailStepRR: number // Trailing step size in Risk Ratio (default 0.5)
  maxInitialRiskPoints: number // Maximum initial risk in points (default 20)
  createdAt: string
  updatedAt: string
}
