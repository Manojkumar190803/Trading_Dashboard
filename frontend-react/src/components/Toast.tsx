import React, { createContext, useContext, useState, useCallback } from 'react'
import { AlertCircle, CheckCircle2, AlertTriangle, Info, X } from 'lucide-react'

export type ToastType = 'success' | 'error' | 'warning' | 'info'

export interface Toast {
  id: string
  type: ToastType
  title: string
  message: string
  duration?: number
  action?: {
    label: string
    onClick: () => void
  }
}

interface ToastContextType {
  toasts: Toast[]
  addToast: (toast: Omit<Toast, 'id'>) => string
  removeToast: (id: string) => void
  clearAll: () => void
}

const ToastContext = createContext<ToastContextType | undefined>(undefined)

/**
 * Toast Provider Component - Must wrap your app
 */
export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = useCallback((toast: Omit<Toast, 'id'>) => {
    const id = `toast-${Date.now()}-${Math.random()}`
    const newToast: Toast = {
      ...toast,
      id,
      duration: toast.duration ?? 5000,
    }

    setToasts((prev) => [...prev, newToast])

    // Auto-remove toast after duration
    if (newToast.duration && newToast.duration > 0) {
      setTimeout(() => {
        removeToast(id)
      }, newToast.duration)
    }

    return id
  }, [])

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const clearAll = useCallback(() => {
    setToasts([])
  }, [])

  return (
    <ToastContext.Provider value={{ toasts, addToast, removeToast, clearAll }}>
      {children}
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </ToastContext.Provider>
  )
}

/**
 * Hook to use toast notifications
 */
export const useToast = () => {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within ToastProvider')
  }
  return context
}

/**
 * Toast Container Component - Renders all toasts
 */
const ToastContainer: React.FC<{
  toasts: Toast[]
  onRemove: (id: string) => void
}> = ({ toasts, onRemove }) => {
  return (
    <div className="fixed bottom-4 right-4 space-y-2 z-50 max-w-sm pointer-events-none">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onRemove={onRemove} />
      ))}
    </div>
  )
}

/**
 * Individual Toast Item Component
 */
const ToastItem: React.FC<{
  toast: Toast
  onRemove: (id: string) => void
}> = ({ toast, onRemove }) => {
  const iconMap = {
    success: <CheckCircle2 className="w-5 h-5 text-green-400" />,
    error: <AlertCircle className="w-5 h-5 text-red-400" />,
    warning: <AlertTriangle className="w-5 h-5 text-yellow-400" />,
    info: <Info className="w-5 h-5 text-blue-400" />,
  }

  const bgMap = {
    success: 'bg-green-900/40 border-green-500/30 backdrop-blur-lg',
    error: 'bg-red-900/40 border-red-500/30 backdrop-blur-lg',
    warning: 'bg-yellow-900/40 border-yellow-500/30 backdrop-blur-lg',
    info: 'bg-blue-900/40 border-blue-500/30 backdrop-blur-lg',
  }

  return (
    <div
      className={`
        pointer-events-auto
        border rounded-lg p-4 flex items-start gap-3 
        ${bgMap[toast.type]}
        animate-in slide-in-from-right-full duration-300
      `}
    >
      {iconMap[toast.type]}
      <div className="flex-1 min-w-0">
        {toast.title && (
          <p className="font-semibold text-text-primary text-sm">
            {toast.title}
          </p>
        )}
        <p className="text-text-secondary text-sm mt-1">
          {toast.message}
        </p>
        {toast.action && (
          <button
            onClick={() => {
              toast.action?.onClick()
              onRemove(toast.id)
            }}
            className="text-xs mt-2 px-3 py-1 bg-white/10 hover:bg-white/20 rounded transition-colors"
          >
            {toast.action.label}
          </button>
        )}
      </div>
      <button
        onClick={() => onRemove(toast.id)}
        className="flex-shrink-0 text-text-secondary hover:text-text-primary transition-colors"
        aria-label="Close notification"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}
