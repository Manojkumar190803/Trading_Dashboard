import React, { useMemo } from 'react'
import { clsx } from 'clsx'

interface DailyPnLCalendarProps {
  dailyData: {
    month: string
    days: Record<string, { pnl: number; trades: number; color: string }>
  } | null
  onExport?: () => void
  onReset?: () => void
}

const DayCell: React.FC<{
  day: number
  pnl: number
  trades: number
  color: string
}> = ({ day, pnl, trades, color }) => {
  const getColorStyles = (colorType: string) => {
    switch (colorType) {
      case 'dark-red':
        return 'bg-red-900 text-red-100 border-red-700 shadow-lg'
      case 'red':
        return 'bg-red-600 text-white border-red-500'
      case 'green':
        return 'bg-green-600 text-white border-green-500'
      case 'dark-green':
        return 'bg-green-900 text-green-100 border-green-700 shadow-lg'
      default:
        return 'bg-gray-700 text-gray-300 border-gray-600'
    }
  }

  return (
    <div
      className={clsx(
        'relative w-full aspect-square rounded border-2 p-1 cursor-pointer transition-transform hover:scale-105 hover:shadow-xl flex flex-col items-center justify-center',
        getColorStyles(color)
      )}
      title={`Day ${day}: ₹${pnl.toLocaleString('en-IN')} (${trades} trades)`}
    >
      <div className="text-xs font-bold">{day}</div>
      {trades > 0 && (
        <div className="text-xs font-semibold truncate">₹{(pnl / 1000).toFixed(1)}k</div>
      )}
    </div>
  )
}

const DailyPnLCalendar: React.FC<DailyPnLCalendarProps> = ({
  dailyData,
  onExport,
  onReset,
}) => {
  const calendarWeeks = useMemo(() => {
    if (!dailyData) return []

    const days = dailyData.days
    const dayCount = Object.keys(days).length
    const firstDay = new Date(new Date().getFullYear(), new Date().getMonth(), 1).getDay()
    
    const weeks: (number | null)[] [] = []
    let currentWeek: (number | null)[] = new Array(firstDay).fill(null)

    for (let i = 1; i <= dayCount; i++) {
      currentWeek.push(i)
      if (currentWeek.length === 7) {
        weeks.push(currentWeek)
        currentWeek = []
      }
    }

    if (currentWeek.length > 0) {
      while (currentWeek.length < 7) {
        currentWeek.push(null)
      }
      weeks.push(currentWeek)
    }

    return weeks
  }, [dailyData])

  if (!dailyData) {
    return (
      <div className="bg-gray-800 rounded-lg p-4 text-gray-400">
        Loading calendar data...
      </div>
    )
  }

  return (
    <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-bold text-white">{dailyData.month}</h3>
        <div className="flex gap-2">
          {onExport && (
            <button
              onClick={onExport}
              className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white text-xs rounded transition-colors"
              title="Export daily P&L as CSV"
            >
              Export
            </button>
          )}
          {onReset && (
            <button
              onClick={onReset}
              className="px-3 py-1 bg-red-600 hover:bg-red-700 text-white text-xs rounded transition-colors"
              title="Reset daily P&L data"
            >
              Reset
            </button>
          )}
        </div>
      </div>

      {/* Day labels */}
      <div className="grid grid-cols-7 gap-2 mb-2">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day) => (
          <div key={day} className="text-center text-xs font-semibold text-gray-400 py-1">
            {day}
          </div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="space-y-2">
        {calendarWeeks.map((week, weekIdx) => (
          <div key={weekIdx} className="grid grid-cols-7 gap-2">
            {week.map((day, dayIdx) => {
              if (day === null) {
                return <div key={`empty-${dayIdx}`} className="w-full aspect-square" />
              }

              const dayData = dailyData.days[day.toString()]
              return (
                <DayCell
                  key={day}
                  day={day}
                  pnl={dayData?.pnl || 0}
                  trades={dayData?.trades || 0}
                  color={dayData?.color || 'gray'}
                />
              )
            })}
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="mt-4 pt-4 border-t border-gray-700 grid grid-cols-4 gap-2 text-xs">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-green-900 rounded border border-green-700"></div>
          <span className="text-gray-400">Big Profit</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-green-600 rounded border border-green-500"></div>
          <span className="text-gray-400">Profit</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-red-600 rounded border border-red-500"></div>
          <span className="text-gray-400">Loss</span>
        </div>
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-red-900 rounded border border-red-700"></div>
          <span className="text-gray-400">Big Loss</span>
        </div>
      </div>
    </div>
  )
}

export default DailyPnLCalendar
