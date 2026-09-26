interface SkeletonProps {
  className?: string
  count?: number
}

export function Skeleton({ className = '', count = 1 }: SkeletonProps) {
  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className={`skeleton rounded-lg ${className}`}
          aria-hidden="true"
        />
      ))}
    </>
  )
}

export function SkeletonRow() {
  return (
    <div className="flex items-center gap-2 px-2 py-1.5">
      <Skeleton className="w-6 h-6 rounded-lg flex-shrink-0" />
      <div className="flex-1 space-y-1">
        <Skeleton className="h-2.5 w-3/4 rounded" />
        <Skeleton className="h-2 w-1/2 rounded" />
      </div>
    </div>
  )
}

export function SkeletonPanel({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-0.5">
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonRow key={i} />
      ))}
    </div>
  )
}

export function Spinner({ size = 16, className = '' }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={`animate-spin ${className}`}
    >
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" className="opacity-20" />
      <path d="M12 2a10 10 0 0 1 10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  )
}

interface EmptyStateProps {
  icon: React.ReactNode
  title: string
  description?: string
  action?: React.ReactNode
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-8 px-4 text-center">
      <div className="w-12 h-12 rounded-2xl bg-surface-elevated border border-border/50 flex items-center justify-center mb-3 animate-float">
        <div className="text-text-muted">{icon}</div>
      </div>
      <p className="text-[13px] font-medium text-text-primary mb-0.5">{title}</p>
      {description && <p className="text-[11px] text-text-muted max-w-[200px] leading-relaxed">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

export function InlineSpinner({ label }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 text-text-muted">
      <Spinner size={14} className="text-accent" />
      {label && <span className="text-[11px]">{label}</span>}
    </div>
  )
}
