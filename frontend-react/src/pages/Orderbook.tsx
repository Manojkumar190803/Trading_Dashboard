import { useState } from 'react'
import { AlertCircle, Check, Clock, X } from 'lucide-react'
import {
  Card,
  SectionTitle,
  EmptyState,
  Table,
  TableRow,
  TableCell,
  Badge,
} from '@/components/UI'
import { formatCurrency, formatTime } from '@/utils/format'

interface Order {
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

const Orderbook: React.FC = () => {
  const [orders] = useState<Order[]>([
    {
      order_id: 'ORD001',
      symbol: 'NIFTY25SEP26000CE',
      side: 'BUY',
      quantity: 5,
      order_type: 'LIMIT',
      status: 'FILLED',
      price: 145.5,
      timestamp: '2026-10-06T09:35:42',
      message: 'Order filled at ₹145.50',
    },
    {
      order_id: 'ORD002',
      symbol: 'NIFTY25SEP26100CE',
      side: 'BUY',
      quantity: 3,
      order_type: 'LIMIT',
      status: 'FILLED',
      price: 92.75,
      timestamp: '2026-10-06T10:12:15',
      message: 'Order filled at ₹92.75',
    },
    {
      order_id: 'ORD003',
      symbol: 'NIFTY25SEP26000CE',
      side: 'SELL',
      quantity: 5,
      order_type: 'STOP_LIMIT',
      status: 'OPEN',
      price: 150.0,
      timestamp: '2026-10-06T10:45:30',
      message: 'Waiting for trigger at ₹150.00',
    },
    {
      order_id: 'ORD004',
      symbol: 'NIFTY25SEP26100CE',
      side: 'SELL',
      quantity: 3,
      order_type: 'STOP_LIMIT',
      status: 'OPEN',
      price: 90.0,
      timestamp: '2026-10-06T11:20:45',
      message: 'Stop loss order active',
    },
  ])

  const [cancellingOrder, setCancellingOrder] = useState<string | null>(null)

  const getStatusIcon = (status: Order['status']) => {
    switch (status) {
      case 'FILLED':
        return <Check size={16} className="text-accent-green" />
      case 'OPEN':
        return <Clock size={16} className="text-accent-yellow" />
      case 'CANCELLED':
        return <X size={16} className="text-accent-red" />
      case 'REJECTED':
        return <AlertCircle size={16} className="text-accent-red" />
    }
  }



  const openOrders = orders.filter((o) => o.status === 'OPEN')
  const filledOrders = orders.filter((o) => o.status === 'FILLED')
  const cancelledOrders = orders.filter((o) =>
    ['CANCELLED', 'REJECTED'].includes(o.status)
  )

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <SectionTitle subtitle="Track all orders placed this session">
          Order Management
        </SectionTitle>
      </div>

      {/* Open Orders */}
      <div>
        <div className="mb-4">
          <h3 className="text-lg font-semibold text-text-primary">
            Open Orders ({openOrders.length})
          </h3>
        </div>

        {openOrders.length === 0 ? (
          <Card>
            <EmptyState
              icon={<AlertCircle size={40} />}
              title="No Open Orders"
              description="All orders have been executed or cancelled"
            />
          </Card>
        ) : (
          <Card>
            <div className="space-y-3">
              {openOrders.map((order) => (
                <div
                  key={order.order_id}
                  className="flex items-center justify-between p-3 bg-bg-secondary/50 rounded-lg border border-accent-yellow/30 hover:border-accent-yellow/50 transition-colors"
                >
                  <div className="flex-1 grid grid-cols-2 md:grid-cols-5 gap-4">
                    <div>
                      <p className="text-xs uppercase text-text-secondary font-semibold mb-1">
                        Order ID
                      </p>
                      <p className="font-mono font-bold text-text-primary">
                        {order.order_id}
                      </p>
                    </div>
                    <div>
                      <p className="text-xs uppercase text-text-secondary font-semibold mb-1">
                        Symbol
                      </p>
                      <p className="font-mono text-text-primary text-sm">{order.symbol}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase text-text-secondary font-semibold mb-1">
                        Action
                      </p>
                      <Badge
                        size="sm"
                        variant={order.side === 'BUY' ? 'success' : 'danger'}
                      >
                        {order.side} {order.quantity}
                      </Badge>
                    </div>
                    <div>
                      <p className="text-xs uppercase text-text-secondary font-semibold mb-1">
                        Type
                      </p>
                      <p className="text-sm text-text-primary">{order.order_type}</p>
                    </div>
                    <div>
                      <p className="text-xs uppercase text-text-secondary font-semibold mb-1">
                        Price
                      </p>
                      <p className="font-mono font-bold text-accent-yellow">
                        {formatCurrency(order.price)}
                      </p>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 ml-4">
                    <button
                      onClick={() => setCancellingOrder(order.order_id)}
                      disabled={cancellingOrder === order.order_id}
                      className="px-3 py-1.5 bg-accent-red/10 text-accent-red text-xs font-semibold rounded hover:bg-accent-red/20 transition-colors disabled:opacity-50"
                    >
                      {cancellingOrder === order.order_id ? 'Cancelling...' : 'Cancel'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>

      {/* Filled Orders */}
      {filledOrders.length > 0 && (
        <div>
          <div className="mb-4">
            <h3 className="text-lg font-semibold text-text-primary">
              Filled Orders ({filledOrders.length})
            </h3>
          </div>

          <Card>
            <div className="overflow-x-auto">
              <Table
                headers={[
                  'Order ID',
                  'Symbol',
                  'Side',
                  'Quantity',
                  'Type',
                  'Price',
                  'Time',
                  'Status',
                ]}
              >
                {filledOrders.map((order) => (
                  <TableRow key={order.order_id}>
                    <TableCell>
                      <span className="font-mono text-sm font-bold text-text-primary">
                        {order.order_id}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="font-mono text-sm">{order.symbol}</span>
                    </TableCell>
                    <TableCell>
                      <Badge
                        size="sm"
                        variant={order.side === 'BUY' ? 'success' : 'danger'}
                      >
                        {order.side}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <span className="font-semibold">{order.quantity}</span>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-text-secondary">
                        {order.order_type}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="font-mono font-bold text-accent-green">
                        {formatCurrency(order.price)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-text-secondary">
                        {formatTime(order.timestamp)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        {getStatusIcon(order.status)}
                        <span className="text-sm font-semibold text-accent-green">
                          {order.status}
                        </span>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </Table>
            </div>
          </Card>
        </div>
      )}

      {/* Cancelled Orders */}
      {cancelledOrders.length > 0 && (
        <div>
          <div className="mb-4">
            <h3 className="text-lg font-semibold text-text-primary">
              Cancelled / Rejected ({cancelledOrders.length})
            </h3>
          </div>

          <Card>
            <div className="space-y-2">
              {cancelledOrders.map((order) => (
                <div
                  key={order.order_id}
                  className="p-3 bg-bg-secondary/50 rounded border border-accent-red/30 flex items-center justify-between"
                >
                  <div className="flex items-center gap-3">
                    {getStatusIcon(order.status)}
                    <div>
                      <p className="font-mono text-sm font-bold text-text-primary">
                        {order.order_id}
                      </p>
                      <p className="text-xs text-text-secondary">{order.message}</p>
                    </div>
                  </div>
                  <span className="text-xs font-semibold text-accent-red">
                    {order.status}
                  </span>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}

export default Orderbook
