import { useState, useCallback, createContext, useContext, useEffect, useRef } from 'react'
import { CheckCircle2, AlertCircle, Info, X, Loader2, AlertTriangle } from 'lucide-react'

type ToastType = 'success' | 'error' | 'info' | 'loading' | 'warning'

// Event bridge for non-React code (e.g. Zustand stores) to trigger toasts
type ToastEvent = { type: ToastType; message: string; detail?: string }
const toastEventTarget = new EventTarget()
export function emitToast(type: ToastType, message: string, detail?: string) {
  toastEventTarget.dispatchEvent(new CustomEvent('toast', { detail: { type, message, detail } }))
}

interface Toast {
  id: string
  type: ToastType
  message: string
  detail?: string
  duration?: number
  progress?: number
  dismissible?: boolean
  onAction?: () => void
  actionLabel?: string
}

interface ToastContextType {
  toasts: Toast[]
  addToast: (type: ToastType, message: string, options?: Partial<Omit<Toast, 'id' | 'type' | 'message'>>) => string
  updateToast: (id: string, updates: Partial<Pick<Toast, 'type' | 'message' | 'detail' | 'progress'>>) => void
  removeToast: (id: string) => void
  success: (message: string, detail?: string) => string
  error: (message: string, detail?: string) => string
  info: (message: string, detail?: string) => string
  warning: (message: string, detail?: string) => string
  loading: (message: string) => string
  promise: <T>(promise: Promise<T>, messages: { loading: string; success: string; error: string }) => Promise<T>
}

const ToastContext = createContext<ToastContextType | null>(null)

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return context
}

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const addToast = useCallback((type: ToastType, message: string, options?: Partial<Omit<Toast, 'id' | 'type' | 'message'>>) => {
    const id = Math.random().toString(36).slice(2)
    const toast: Toast = { id, type, message, duration: type === 'loading' ? undefined : 4000, dismissible: true, ...options }
    setToasts((prev) => {
      const next = prev.length >= 5 ? prev.slice(1) : prev
      return [...next, toast]
    })
    return id
  }, [])

  const updateToast = useCallback((id: string, updates: Partial<Pick<Toast, 'type' | 'message' | 'detail' | 'progress'>>) => {
    setToasts((prev) => prev.map((t) => t.id === id ? { ...t, ...updates } : t))
  }, [])

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.map((t) => t.id === id ? { ...t, _removing: true } as any : t))
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, 200)
  }, [])

  const success = useCallback((message: string, detail?: string) => addToast('success', message, { detail, duration: 3000 }), [addToast])
  const error = useCallback((message: string, detail?: string) => addToast('error', message, { detail, duration: 6000 }), [addToast])
  const info = useCallback((message: string, detail?: string) => addToast('info', message, { detail }), [addToast])
  const warning = useCallback((message: string, detail?: string) => addToast('warning', message, { detail, duration: 5000 }), [addToast])
  const loading = useCallback((message: string) => addToast('loading', message, { dismissible: false }), [addToast])

  const promise = useCallback(async <T,>(p: Promise<T>, messages: { loading: string; success: string; error: string }): Promise<T> => {
    const id = loading(messages.loading)
    try {
      const result = await p
      updateToast(id, { type: 'success', message: messages.success, progress: undefined })
      setTimeout(() => removeToast(id), 3000)
      return result
    } catch (err) {
      const msg = err instanceof Error ? err.message : messages.error
      updateToast(id, { type: 'error', message: messages.error, detail: msg })
      setTimeout(() => removeToast(id), 6000)
      throw err
    }
  }, [loading, updateToast, removeToast])

  // Listen for toast events from non-React code
  useEffect(() => {
    const handler = (e: Event) => {
      const { type, message, detail } = (e as CustomEvent<ToastEvent>).detail
      addToast(type, message, { detail })
    }
    toastEventTarget.addEventListener('toast', handler)
    return () => toastEventTarget.removeEventListener('toast', handler)
  }, [addToast])

  return (
    <ToastContext.Provider value={{ toasts, addToast, updateToast, removeToast, success, error, info, warning, loading, promise }}>
      {children}
      <ToastContainer toasts={toasts} removeToast={removeToast} />
    </ToastContext.Provider>
  )
}

function ToastContainer({ toasts, removeToast }: { toasts: Toast[]; removeToast: (id: string) => void }) {
  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onRemove={() => removeToast(toast.id)} />
      ))}
    </div>
  )
}

function ToastItem({ toast, onRemove }: { toast: Toast; onRemove: () => void }) {
  const [isRemoving, setIsRemoving] = useState(false)
  const progressRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (toast.type !== 'loading' && toast.duration) {
      const timer = setTimeout(onRemove, toast.duration)
      return () => clearTimeout(timer)
    }
  }, [toast, onRemove])

  const handleRemove = () => {
    setIsRemoving(true)
    setTimeout(onRemove, 200)
  }

  const icons = {
    success: <CheckCircle2 size={16} className="text-success" />,
    error: <AlertCircle size={16} className="text-red-400" />,
    warning: <AlertTriangle size={16} className="text-yellow-400" />,
    info: <Info size={16} className="text-accent" />,
    loading: <Loader2 size={16} className="text-accent animate-spin" />,
  }

  const bgColors = {
    success: 'border-success/30 bg-gradient-to-r from-success/10 to-success/5',
    error: 'border-red-500/30 bg-gradient-to-r from-red-500/10 to-red-500/5',
    warning: 'border-yellow-500/30 bg-gradient-to-r from-yellow-500/10 to-yellow-500/5',
    info: 'border-accent/30 bg-gradient-to-r from-accent/10 to-accent/5',
    loading: 'border-border bg-surface-elevated',
  }

  const progressColors = {
    success: 'bg-success',
    error: 'bg-red-500',
    warning: 'bg-yellow-500',
    info: 'bg-accent',
    loading: 'bg-accent',
  }

  return (
    <div
      className={`relative flex items-start gap-3 px-4 py-3 rounded-xl border shadow-lg backdrop-blur-sm overflow-hidden transition-all duration-200 ${
        isRemoving ? 'opacity-0 translate-x-8 scale-95' : 'opacity-100 translate-x-0 scale-100 animate-slide-up'
      } ${bgColors[toast.type]}`}
    >
      {/* Progress bar for auto-dismiss */}
      {toast.type !== 'loading' && toast.duration && (
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-border/30">
          <div
            ref={progressRef}
            className={`h-full ${progressColors[toast.type]} transition-all ease-linear`}
            style={{
              width: '100%',
              animation: `toast-progress ${toast.duration}ms linear forwards`,
            }}
          />
        </div>
      )}

      {/* Custom progress indicator */}
      {toast.progress !== undefined && (
        <div className="absolute bottom-0 left-0 right-0 h-0.5 bg-border/30">
          <div
            className={`h-full ${progressColors[toast.type]} transition-all duration-300`}
            style={{ width: `${toast.progress}%` }}
          />
        </div>
      )}

      <div className="flex-shrink-0 mt-0.5">
        {icons[toast.type]}
      </div>

      <div className="flex-1 min-w-0">
        <p className="text-[13px] font-medium text-text-primary leading-snug">{toast.message}</p>
        {toast.detail && (
          <p className="text-[11px] text-text-muted mt-0.5 leading-snug">{toast.detail}</p>
        )}
        {toast.onAction && toast.actionLabel && (
          <button
            onClick={() => { toast.onAction?.(); handleRemove() }}
            className="mt-1.5 text-[11px] font-medium text-accent hover:text-accent-hover transition-colors"
          >
            {toast.actionLabel}
          </button>
        )}
      </div>

      {toast.dismissible !== false && (
        <button
          onClick={handleRemove}
          className="flex-shrink-0 p-1 rounded-lg text-text-muted hover:text-text-primary hover:bg-surface/50 transition-all mt-0.5"
        >
          <X size={12} />
        </button>
      )}
    </div>
  )
}
