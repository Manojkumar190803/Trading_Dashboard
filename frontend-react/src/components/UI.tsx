import { ReactNode } from 'react'
import { clsx } from 'clsx'

interface CardProps {
  children: ReactNode
  className?: string
  hoverable?: boolean
  onClick?: () => void
}

export const Card: React.FC<CardProps> = ({ children, className, hoverable = false }) => (
  <div
    className={clsx(
      'bg-gradient-to-br from-bg-surface to-bg-tertiary border border-bg-tertiary/50 rounded-xl p-4 shadow-card',
      hoverable && 'hover:shadow-card-hover hover:border-accent-cyan/50 cursor-pointer transition-all duration-300',
      className
    )}
  >
    {children}
  </div>
)

interface MetricCardProps {
  label: string
  value: string | number
  sublabel?: string
  icon?: ReactNode
  color?: 'default' | 'green' | 'red' | 'cyan' | 'yellow'
  trend?: 'up' | 'down' | 'neutral'
}

export const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  sublabel,
  icon,
  color = 'default',
  trend,
}) => {
  const colorClasses = {
    default: 'text-text-primary',
    green: 'text-accent-green',
    red: 'text-accent-red',
    cyan: 'text-accent-cyan',
    yellow: 'text-accent-yellow',
  }

  return (
    <Card>
      <div className="flex items-start justify-between mb-2">
        <div className="text-xs uppercase tracking-wider text-text-secondary font-semibold">
          {label}
        </div>
        {icon && <span className="text-text-tertiary">{icon}</span>}
      </div>
      <div className={clsx('text-3xl font-bold mb-1', colorClasses[color])}>
        {value}
      </div>
      {sublabel && (
        <div className="text-xs text-text-tertiary flex items-center gap-1">
          {trend && (
            <span className={trend === 'up' ? 'text-accent-green' : trend === 'down' ? 'text-accent-red' : ''}>
              {trend === 'up' ? '↑' : trend === 'down' ? '↓' : '→'}
            </span>
          )}
          {sublabel}
        </div>
      )}
    </Card>
  )
}

interface BadgeProps {
  children: ReactNode
  variant?: 'primary' | 'success' | 'warning' | 'danger' | 'info'
  size?: 'sm' | 'md'
  className?: string
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'primary',
  size = 'sm',
  className,
}) => {
  const variants = {
    primary: 'bg-accent-cyan/10 text-accent-cyan border-accent-cyan/30',
    success: 'bg-accent-green/10 text-accent-green border-accent-green/30',
    warning: 'bg-accent-yellow/10 text-accent-yellow border-accent-yellow/30',
    danger: 'bg-accent-red/10 text-accent-red border-accent-red/30',
    info: 'bg-accent-blue/10 text-accent-blue border-accent-blue/30',
  }

  const sizes = {
    sm: 'px-2 py-0.5 text-xs',
    md: 'px-3 py-1 text-sm',
  }

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 border rounded-full font-medium',
        variants[variant],
        sizes[size],
        className
      )}
    >
      {children}
    </span>
  )
}

interface StatusDotProps {
  status: 'active' | 'inactive' | 'warning' | 'error'
  label?: string
}

export const StatusDot: React.FC<StatusDotProps> = ({ status, label }) => {
  const statusColors = {
    active: 'bg-accent-green',
    inactive: 'bg-text-tertiary',
    warning: 'bg-accent-yellow',
    error: 'bg-accent-red',
  }

  return (
    <div className="flex items-center gap-2">
      <div className={clsx('w-2 h-2 rounded-full animate-pulse-soft', statusColors[status])} />
      {label && <span className="text-xs text-text-secondary">{label}</span>}
    </div>
  )
}

interface SectionTitleProps {
  children: ReactNode
  subtitle?: string
  action?: ReactNode
}

export const SectionTitle: React.FC<SectionTitleProps> = ({ children, subtitle, action }) => (
  <div className="flex items-start justify-between mb-6">
    <div>
      <h3 className="text-xl font-bold text-text-primary">{children}</h3>
      {subtitle && <p className="text-sm text-text-secondary mt-1">{subtitle}</p>}
    </div>
    {action}
  </div>
)

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg'
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ size = 'md' }) => {
  const sizeClasses = {
    sm: 'w-4 h-4',
    md: 'w-8 h-8',
    lg: 'w-12 h-12',
  }

  return (
    <div className={clsx('border-4 border-bg-tertiary border-t-accent-cyan rounded-full animate-spin', sizeClasses[size])} />
  )
}

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
}

export const EmptyState: React.FC<EmptyStateProps> = ({
  icon,
  title,
  description,
  action,
}) => (
  <div className="text-center py-12">
    {icon && <div className="mb-4 flex justify-center text-text-tertiary">{icon}</div>}
    <h3 className="text-lg font-semibold text-text-primary mb-2">{title}</h3>
    {description && <p className="text-sm text-text-secondary mb-6">{description}</p>}
    {action}
  </div>
)

interface TableProps {
  headers: string[]
  children: ReactNode
  className?: string
}

export const Table: React.FC<TableProps> = ({ headers, children, className }) => (
  <div className={clsx('overflow-x-auto rounded-lg border border-bg-tertiary', className)}>
    <table className="w-full">
      <thead>
        <tr className="bg-bg-secondary border-b border-bg-tertiary">
          {headers.map((header, index) => (
            <th
              key={index}
              className="px-4 py-3 text-left text-xs uppercase tracking-wider text-text-secondary font-semibold"
            >
              {header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  </div>
)

interface TableRowProps {
  children: ReactNode
  highlight?: boolean
  className?: string
}

export const TableRow: React.FC<TableRowProps> = ({ children, highlight, className }) => (
  <tr
    className={clsx(
      'border-b border-bg-tertiary hover:bg-bg-tertiary/50 transition-colors',
      highlight && 'bg-accent-cyan/5',
      className
    )}
  >
    {children}
  </tr>
)

interface TableCellProps {
  children: ReactNode
  className?: string
}

export const TableCell: React.FC<TableCellProps> = ({ children, className }) => (
  <td className={clsx('px-4 py-3 text-sm text-text-primary', className)}>
    {children}
  </td>
)
