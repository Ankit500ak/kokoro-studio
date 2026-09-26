import { useEffect, useState } from 'react'
import { useAppStore } from '../hooks/useStore'
import { useTTS } from '../hooks/useTTS'
import { Sparkles, Loader2, AlertCircle, X, Clock } from 'lucide-react'

interface GenerateButtonProps {
  projectId?: string | null
}

export function GenerateButton({ projectId }: GenerateButtonProps) {
  const text = useAppStore((s) => s.text)
  const isGenerating = useAppStore((s) => s.isGenerating)
  const error = useAppStore((s) => s.error)
  const setError = useAppStore((s) => s.setError)
  const { generate } = useTTS()
  const [elapsed, setElapsed] = useState(0)

  const canGenerate = !isGenerating && text.trim()

  useEffect(() => {
    if (!isGenerating) { setElapsed(0); return }
    const t = setInterval(() => setElapsed(p => p + 1), 1000)
    return () => clearInterval(t)
  }, [isGenerating])

  const fmtTime = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`

  const wordCount = text.trim().split(/\s+/).filter(Boolean).length
  const estTotal = Math.max(5, Math.ceil(wordCount * 0.4))
  const progress = isGenerating ? Math.min(95, Math.round((elapsed / estTotal) * 100)) : 0
  const remaining = Math.max(0, estTotal - elapsed)

  return (
    <div className="space-y-2">
      <button
        data-generate-btn
        onClick={() => generate(projectId)}
        disabled={!canGenerate}
        className={`w-full py-2.5 px-4 rounded-xl font-medium text-sm flex items-center justify-center gap-2 transition-all ${
          canGenerate
            ? 'bg-gradient-to-r from-accent to-accent-hover text-white shadow-md shadow-accent/20 hover:shadow-glow active:scale-[0.98]'
            : 'bg-surface border border-border text-text-muted cursor-not-allowed'
        }`}
      >
        {isGenerating ? (
          <><Loader2 size={15} className="animate-spin" /><span>Generating...</span></>
        ) : (
          <><Sparkles size={15} className={canGenerate ? 'text-white' : ''} /><span>Generate Speech</span></>
        )}
      </button>

      {isGenerating && (
        <div className="bg-surface rounded-lg px-3 py-2.5 border border-border/50 space-y-2">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-1.5">
              <div className="w-1.5 h-1.5 bg-accent rounded-full animate-pulse" />
              <span className="text-[10px] font-medium text-text-primary">Synthesizing voice</span>
            </div>
            <span className="text-[10px] text-text-muted font-mono flex items-center gap-1">
              <Clock size={9} />{fmtTime(elapsed)}
            </span>
          </div>

          <div className="space-y-1">
            <div className="h-1.5 bg-border rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-accent to-accent-hover rounded-full transition-all duration-1000 ease-out relative overflow-hidden progress-shine"
                style={{ width: `${progress}%` }}
              />
            </div>
            <div className="flex items-center justify-between text-[9px] text-text-muted tabular-nums">
              <span>{wordCount} words</span>
              <span>{progress}% · ~{fmtTime(remaining)} left</span>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="bg-red-500/5 border border-red-500/20 rounded-lg px-3 py-2 flex items-start gap-2">
          <AlertCircle size={13} className="text-red-400 mt-0.5 flex-shrink-0" />
          <div className="flex-1 min-w-0">
            <p className="text-[11px] font-medium text-text-primary">Failed</p>
            <p className="text-[10px] text-text-secondary">{error}</p>
          </div>
          <button onClick={() => setError(null)} className="p-0.5 text-text-muted hover:text-text-primary"><X size={11} /></button>
        </div>
      )}
    </div>
  )
}
