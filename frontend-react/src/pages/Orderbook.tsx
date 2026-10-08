import { useMemo } from 'react'
import { AlertCircle, Clock, X, TrendingUp, Activity, Download } from 'lucide-react'
import {
  Card,
  SectionTitle,
  LoadingSpinner,
  EmptyState,
  Badge,
  MetricCard,
} from '@/components/UI'
import { useRealAccountData } from '@/hooks'
import { formatCurrency, formatTime } from '@/utils/format'
import { exportExecutionLogCSV, exportOrdersCSV } from '@/utils/csv-export'
import { clsx } from 'clsx'

const Orderbook: React.FC = () => {
  // Fetch real OpenAlgo order data - poll every 5 seconds
  const { data: accountData, isLoading: dataLoading } = useRealAccountData(true, 5000)

  // Memoize order statistics and data
  const { orderStats, executionLog, liveOrders } = useMemo(() => {
    if (!accountData?.orders?.orders) {
      return {
        orderStats: {
          buyOrders: 0,
          sellOrders: 0,
          completed: 0,
          open: 0,
          rejected: 0,
        },
        executionLog: [],
        liveOrders: [],
      }
    }

    const orders = accountData.orders.orders

    // Calculate order statistics
    let buyCount = 0
    let sellCount = 0
    let completedCount = 0
    let openCount = 0
    let rejectedCount = 0

    orders.forEach((order: any) => {
      if (order.action === 'BUY') buyCount++
      if (order.action === 'SELL') sellCount++
      if (order.order_status === 'complete') completedCount++
      if (order.order_status === 'open') openCount++
      if (order.order_status === 'rejected') rejectedCount++
    })

    // Prepare execution log (completed and cancelled orders with P&L)
    const execLog = orders
      .filter((o: any) => ['complete', 'cancelled'].includes(o.order_status))
      .map((o: any) => ({
        id: o.orderid,
        timestamp: o.timestamp,
        orderId: o.orderid,
        symbol: o.symbol,
        action: o.action,
        quantity: o.quantity,
        price: o.average_price || o.price,
        status: o.order_status,
        type: o.pricetype,
        category: o.order_status === 'complete' ? 'ORDER' : 'CANCELLED',
      }))
      .sort((a: any, b: any) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime())

    // Prepare live orders (all orders for broker orderbook)
    const live = orders.map((o: any) => ({
      id: o.orderid,
      symbol: o.symbol,
      action: o.action,
      quantity: o.quantity,
      price: o.price,
      triggerPrice: o.trigger_price,
      orderId: o.orderid,
      status: o.order_status,
      timestamp: o.timestamp,
      filledQuantity: o.filled_quantity,
      averagePrice: o.average_price,
    }))

    return {
      orderStats: {
        buyOrders: buyCount,
        sellOrders: sellCount,
        completed: completedCount,
        open: openCount,
        rejected: rejectedCount,
      },
      executionLog: execLog,
      liveOrders: live,
    }
  }, [accountData?.orders?.orders])

  const getStatusBadgeVariant = (status: string) => {
    switch (status) {
      case 'complete':
        return 'success'
      case 'open':
        return 'warning'
      case 'cancelled':
        return 'danger'
      case 'rejected':
        return 'danger'
      default:
        return 'secondary'
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'complete':
        return 'text-green-400'
      case 'open':
        return 'text-amber-400'
      case 'cancelled':
        return 'text-red-400'
      case 'rejected':
        return 'text-red-400'
      default:
        return 'text-text-secondary'
    }
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <SectionTitle subtitle="Watch every trigger, fill, cancellation, and rejection from OpenAlgo in one place.">
          Order Book
        </SectionTitle>
      </div>

      {/* Order Status Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <MetricCard
          icon={<TrendingUp className="text-emerald-500" />}
          label="Buy orders"
          value={orderStats.buyOrders}
          subLabel="Total buy orders"
          color="emerald"
        />
        <MetricCard
          icon={<TrendingUp className="text-red-500 transform rotate-180" />}
          label="Sell orders"
          value={orderStats.sellOrders}
          subLabel="Total sell orders"
          color="red"
        />
        <MetricCard
          icon={<Activity className="text-green-500" />}
          label="Completed"
          value={orderStats.completed}
          subLabel="Filled orders"
          color="emerald"
        />
        <MetricCard
          icon={<Clock className="text-amber-500" />}
          label="Open"
          value={orderStats.open}
          subLabel="Pending orders"
          color="amber"
        />
        <MetricCard
          icon={<AlertCircle className="text-red-500" />}
          label="Rejected"
          value={orderStats.rejected}
          subLabel="Rejected orders"
          color="red"
        />
      </div>

      {/* Execution Log */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-semibold text-text-primary">
              Trades executed today
            </h3>
            <p className="text-sm text-text-secondary">
              All trades executed during the current trading day.
            </p>
          </div>
          {executionLog.length > 0 && (
            <button
              onClick={() => exportExecutionLogCSV(executionLog)}
              className="flex items-center gap-2 px-3 py-2 text-sm font-semibold text-emerald-400 hover:text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/20 rounded transition-colors whitespace-nowrap"
              title="Download execution log as CSV"
            >
              <Download size={16} />
              Export CSV
            </button>
          )}
        </div>

        {dataLoading ? (
          <div className="flex items-center justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : executionLog.length === 0 ? (
          <Card className="mt-4">
            <EmptyState
              icon={<AlertCircle size={48} />}
              title="No Executions"
              description="No trades have been executed yet today."
            />
          </Card>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-bg-tertiary mt-4">
            <table className="w-full">
              <thead>
                <tr className="bg-bg-secondary border-b border-bg-tertiary">
                  <th className="px-6 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                    Timestamp
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                    Category
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                    Order Info
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-semibold text-text-secondary uppercase tracking-wider">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody>
                {executionLog.map((exec: any) => (
                  <tr
                    key={exec.id}
                    className="border-b border-bg-tertiary hover:bg-bg-secondary/50 transition-colors"
                  >
                    <td className="px-6 py-4">
                      <p className="font-mono text-sm text-text-primary">
                        {exec.timestamp}
                      </p>
                    </td>
                    <td className="px-6 py-4">
                      <Badge
                        variant={exec.category === 'ORDER' ? 'secondary' : 'danger'}
                        size="sm"
                      >
                        {exec.category}
                      </Badge>
                    </td>
                    <td className="px-6 py-4">
                      <p className="text-sm text-text-primary font-mono">
                        {exec.action} {exec.quantity} {exec.symbol} @ {formatCurrency(exec.price)}
                        {exec.type && <span className="text-xs text-text-secondary ml-2">({exec.type})</span>}
                      </p>
                    </td>
                    <td className="px-6 py-4">
                      <Badge
                        variant={getStatusBadgeVariant(exec.status)}
                        size="sm"
                      >
                        {exec.status.toUpperCase()}
                      </Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Live Orderbook */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-semibold text-text-primary">
              Orders from your broker
            </h3>
            <p className="text-sm text-text-secondary">
              Fetched live from OpenAlgo — reflects your actual broker orderbook.
            </p>
          </div>
          {liveOrders.length > 0 && (
            <button
              onClick={() => exportOrdersCSV(liveOrders)}
              className="flex items-center gap-2 px-3 py-2 text-sm font-semibold text-emerald-400 hover:text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/20 rounded transition-colors whitespace-nowrap"
              title="Download orders as CSV"
            >
              <Download size={16} />
              Export CSV
            </button>
          )}
        </div>

        {dataLoading ? (
          <div className="flex items-center justify-center py-12">
            <LoadingSpinner />
          </div>
        ) : liveOrders.length === 0 ? (
          <Card className="mt-4">
            <EmptyState
              icon={<AlertCircle size={48} />}
              title="No Orders"
              description="No orders in your broker orderbook."
            />
          </Card>
        ) : (
          <div className="space-y-3 mt-4">
            {liveOrders.map((order: any) => (
              <Card
                key={order.id}
                className={clsx(
                  'border-2',
                  order.status === 'open'
                    ? 'border-amber-500/30'
                    : order.status === 'complete'
                    ? 'border-green-500/30'
                    : 'border-red-500/30'
                )}
              >
                <div className="flex items-start justify-between">
                  {/* Instrument Info */}
                  <div className="flex-1">
                    <div className="mb-4">
                      <p className="text-sm text-text-secondary uppercase tracking-wider font-semibold">
                        Instrument
                      </p>
                      <p className="font-mono font-bold text-text-primary text-lg">
                        {order.symbol}
                      </p>
                      <p className="text-xs text-text-secondary mt-1">NFO</p>
                    </div>

                    {/* Trade Details Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                      {/* Action */}
                      <div>
                        <p className="text-xs text-text-secondary uppercase tracking-wider font-semibold mb-1">
                          Trade Details
                        </p>
                        <div className="flex items-center gap-2">
                          <Badge
                            variant={order.action === 'BUY' ? 'success' : 'danger'}
                            size="sm"
                          >
                            {order.action}
                          </Badge>
                          <p className="text-xs text-text-secondary">
                            Qty {order.quantity}
                            {order.filledQuantity > 0 && (
                              <span className="ml-1">/ Filled {order.filledQuantity}</span>
                            )}
                          </p>
                        </div>
                      </div>

                      {/* Price */}
                      <div>
                        <p className="text-xs text-text-secondary uppercase tracking-wider font-semibold mb-1">
                          Price
                        </p>
                        <p className="font-mono font-bold text-text-primary">
                          {formatCurrency(order.price)}
                        </p>
                        {order.triggerPrice > 0 && (
                          <p className="text-xs text-text-secondary">
                            Trigger {formatCurrency(order.triggerPrice)}
                          </p>
                        )}
                      </div>

                      {/* Broker Order ID */}
                      <div>
                        <p className="text-xs text-text-secondary uppercase tracking-wider font-semibold mb-1">
                          Broker Order
                        </p>
                        <p className="font-mono text-sm text-text-primary">
                          {order.orderId}
                        </p>
                      </div>

                      {/* Status & Time */}
                      <div>
                        <p className="text-xs text-text-secondary uppercase tracking-wider font-semibold mb-1">
                          Status / Time
                        </p>
                        <Badge
                          variant={getStatusBadgeVariant(order.status)}
                          size="sm"
                        >
                          {order.status.toUpperCase()}
                        </Badge>
                        <p className="text-xs text-text-secondary mt-1">
                          {formatTime(order.timestamp)}
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* Cancel Button */}
                  {order.status === 'open' && (
                    <button className="ml-4 p-2 rounded hover:bg-bg-secondary/50 transition-colors">
                      <X size={18} className="text-red-400" />
                    </button>
                  )}
                </div>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export default Orderbook
