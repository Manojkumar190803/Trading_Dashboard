import clsx from 'clsx'

interface ExecutionModeBadgeProps {
  mode: 'LIVE' | 'TEST'
  className?: string
}

const ExecutionModeBadge: React.FC<ExecutionModeBadgeProps> = ({ mode, className }) => (
  <span
    className={clsx(
      'inline-flex min-w-16 justify-center rounded px-2.5 py-1 text-[11px] font-black ring-2',
      mode === 'TEST'
        ? 'bg-amber-300 text-black ring-amber-100'
        : 'bg-emerald-400 text-black ring-emerald-200',
      className,
    )}
  >
    {mode}
  </span>
)

export default ExecutionModeBadge