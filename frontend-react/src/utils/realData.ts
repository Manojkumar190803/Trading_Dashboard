/**
 * Real Account Data Provider - Reads actual OpenAlgo and Fyers data
 */

import { DashboardMetrics, Position, Order } from '@/types'

/**
 * Fetch real OpenAlgo account data
 */
export async function fetchOpenAlgoData(): Promise<{
  account: Record<string, any>;
  positions: Position[];
  orders: Order[];
} | null> {
  try {
    const response = await fetch('/api/logs/dashboard_data.json');
    if (!response.ok) return null;

    const data = await response.json();
    return {
      account: data.account || {},
      positions: (data.positions || []).map((p: any) => ({
        option_symbol: p.symbol || p.tradingsymbol || '',
        quantity: parseFloat(p.qty || p.quantity || 0),
        entry_price: parseFloat(p.avgprice || p.entry_price || 0),
        pnl: parseFloat(p.pnl || p.unrealizedpnl || 0),
        pnl_percent: parseFloat(p.pnlpercent || p.pnl_percent || 0),
        stop_level: parseFloat(p.stop_level || 0),
        trailing_sl_level: parseFloat(p.trailing_sl_level || 0),
      })),
      orders: (data.orders || []).map((o: any) => ({
        order_id: o.orderid || o.id || '',
        symbol: o.symbol || o.tradingsymbol || '',
        side: (o.side || o.direction || 'BUY').toUpperCase() as 'BUY' | 'SELL',
        quantity: parseFloat(o.qty || o.quantity || 0),
        status: (o.status || 'Open').charAt(0).toUpperCase() + (o.status || 'Open').slice(1),
        price: parseFloat(o.price || o.limitprice || 0),
        timestamp: o.timestamp || new Date().toISOString(),
      })),
    };
  } catch (error) {
    console.error('Error fetching OpenAlgo data:', error);
    return null;
  }
}

/**
 * Fetch real Fyers wallet data (for live mode)
 */
export async function fetchFyersWalletData(): Promise<{
  available_balance: number;
  used_margin: number;
  available_margin: number;
  pnl: number;
} | null> {
  try {
    const response = await fetch('/api/logs/wallet_data.json');
    if (!response.ok) return null;

    const data = await response.json();
    return {
      available_balance: parseFloat(data.available_balance || data.cash || 0),
      used_margin: parseFloat(data.utilisedMargin || data.used_margin || 0),
      available_margin: parseFloat(data.availableMargin || data.available_margin || 0),
      pnl: parseFloat(data.pnl || 0),
    };
  } catch (error) {
    console.error('Error fetching Fyers wallet data:', error);
    return null;
  }
}

/**
 * Build real metrics from OpenAlgo account data
 */
export function buildMetricsFromOpenAlgo(
  account: Record<string, any>,
  positions: Position[]
): DashboardMetrics {
  // Calculate P&L from positions
  const totalPnL = positions.reduce((sum, p) => sum + (p.pnl ?? 0), 0)
  
  // Get margin info from account
  const availableMargin = parseFloat(account.margin || account.availableMargin || 500000)

  return {
    net_mtm: parseFloat(account.mtm || account.pnl || totalPnL),
    available_margin: availableMargin,
    active_trades: positions.filter(p => p.quantity !== 0).length,
    engine_status: 'running' as const,
    last_update: new Date().toISOString(),
  }
}

/**
 * Build metrics from Fyers wallet (live mode)
 */
export function buildMetricsFromFyersWallet(
  wallet: Record<string, any>,
  positions: Position[]
): DashboardMetrics {
  return {
    net_mtm: wallet.pnl || 0,
    available_margin: wallet.available_balance || 0,
    active_trades: positions.filter(p => p.quantity !== 0).length,
    engine_status: 'running' as const,
    last_update: new Date().toISOString(),
  }
}

/**
 * Detect current mode from environment or running process
 */
export async function detectMode(): Promise<'analyzer' | 'live'> {
  try {
    // Check if wallet data exists (live mode) or just dashboard data (analyzer)
    const response = await fetch('/api/logs/wallet_data.json')
    if (response.ok) {
      return 'live'
    }
    return 'analyzer'
  } catch {
    return 'analyzer'
  }
}

/**
 * Hook to watch for mode changes
 */
export function watchMode(
  callback: (mode: 'analyzer' | 'live') => void,
  interval: number = 5000
): () => void {
  let lastMode: 'analyzer' | 'live' = 'analyzer';

  const checkMode = async () => {
    const mode = await detectMode();
    if (mode !== lastMode) {
      lastMode = mode;
      callback(mode);
    }
  };

  checkMode(); // Check immediately
  const timer = setInterval(checkMode, interval);

  return () => clearInterval(timer); // Cleanup function
}
