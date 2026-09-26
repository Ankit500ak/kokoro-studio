import { useEffect, useState } from 'react'
import { Loader2, CheckCircle2, XCircle, Download, RefreshCw, Clock, AlertTriangle } from 'lucide-react'
import type { RenderJob, RenderOutput } from '../types'
import { fetchWithTimeout } from '../lib/fetch'
import { API_BASE } from '../lib/api'

interface RenderProgressProps {
  job: RenderJob
  onRetry: (job: RenderJob) => void
}

const STAGE_CONFIG: Record<string, { label: string; progress: number }> = {
  queued: { label: 'Queued', progress: 5 },
  preparing: { label: 'Preparing', progress: 10 },
  analyzing_audio: { label: 'Analyzing Audio', progress: 20 },
  building_captions: { label: 'Building Captions', progress: 35 },
  selecting_clips: { label: 'Selecting B-roll', progress: 45 },
  rendering: { label: 'Rendering Video', progress: 65 },
  validating_output: { label: 'Validating Output', progress: 90 },
  completed: { label: 'Done', progress: 100 },
  failed: { label: 'Failed', progress: 0 },
}

export function RenderProgress({ job: initialJob, onRetry }: RenderProgressProps) {
  const [job, setJob] = useState<RenderJob>(initialJob)
  const [output, setOutput] = useState<RenderOutput | null>(null)
  const [elapsedTime, setElapsedTime] = useState(0)

  const isDone = job.status === 'completed' || job.status === 'failed'

  useEffect(() => {
    if (isDone) return
    const interval = setInterval(async () => {
      try {
        const r = await fetchWithTimeout(`${API_BASE}/renders/${initialJob.id}`, { timeout: 5000 })
        if (r.ok) {
          const updated: RenderJob = await r.json()
          setJob(updated)
          if (updated.status === 'completed' || updated.status === 'failed') {
            try {
              const o = await fetchWithTimeout(`${API_BASE}/renders/${initialJob.id}/output`, { timeout: 5000 })
              if (o.ok) setOutput(await o.json())
            } catch {}
          }
        }
      } catch {}
    }, 2000)
    return () => clearInterval(interval)
  }, [initialJob.id, isDone])

  useEffect(() => {
    if (isDone) return
    const t = setInterval(() => setElapsedTime(p => p + 1), 1000)
    return () => clearInterval(t)
  }, [isDone])

  const stage = STAGE_CONFIG[job.current_stage || job.status] || STAGE_CONFIG.preparing
  const progress = job.progress ?? stage.progress
  const fmtElapsed = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toString().padStart(2, '0')}`

  return (
    <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          {job.status === 'completed' ? <CheckCircle2 size={13} className="text-success" /> :
           job.status === 'failed' ? <XCircle size={13} className="text-red-400" /> :
           <Loader2 size={13} className="text-accent animate-spin" />}
          <span className="text-xs font-semibold text-text-primary">
            {job.status === 'completed' ? 'Video Ready' : job.status === 'failed' ? 'Failed' : stage.label}
          </span>
        </div>
        {!isDone && (
          <span className="text-[10px] text-text-muted font-mono tabular-nums flex items-center gap-1"><Clock size={9} />{fmtElapsed(elapsedTime)}</span>
        )}
      </div>

      <div className="px-3 py-2.5 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-[11px] text-text-secondary">{stage.label}</span>
          <span className="text-[10px] text-text-muted font-mono">{progress}%</span>
        </div>
        <div className="h-1.5 bg-surface rounded-full overflow-hidden">
          <div className={`h-full rounded-full transition-all duration-700 relative overflow-hidden ${
            job.status === 'failed' ? 'bg-red-500' : job.status === 'completed' ? 'bg-success' : 'bg-gradient-to-r from-accent to-accent-hover'
          } ${!isDone ? 'progress-shine' : ''}`} style={{ width: `${progress}%` }} />
        </div>

        {job.status === 'failed' && job.error_message && (
          <div className="p-2 bg-red-500/10 border border-red-500/20 rounded-lg flex items-start gap-2">
            <AlertTriangle size={11} className="text-red-400 mt-0.5 flex-shrink-0" />
            <p className="text-[10px] text-red-400">{job.error_message}</p>
          </div>
        )}

        {job.status === 'completed' && output && (
          <div className="space-y-2">
            <a href={`${API_BASE}/renders/${job.id}/file`} download={output.video_filename}
              className="flex items-center justify-center gap-2 w-full py-2 bg-gradient-to-r from-success to-emerald-600 text-white rounded-lg text-xs font-medium transition-all hover:shadow-lg active:scale-[0.98]">
              <Download size={12} />Download Video
            </a>
            <div className="flex items-center justify-around text-center">
              <div><p className="text-[8px] text-text-muted">Duration</p><p className="text-[10px] font-medium text-text-primary">{output.duration ? `${output.duration.toFixed(1)}s` : '--'}</p></div>
              <div><p className="text-[8px] text-text-muted">Resolution</p><p className="text-[10px] font-medium text-text-primary">{output.width && output.height ? `${output.width}x${output.height}` : '--'}</p></div>
              <div><p className="text-[8px] text-text-muted">Size</p><p className="text-[10px] font-medium text-text-primary">{output.file_size ? `${(output.file_size / (1024 * 1024)).toFixed(1)}MB` : '--'}</p></div>
            </div>
          </div>
        )}

        {job.status === 'failed' && (
          <button onClick={() => onRetry(job)} className="flex items-center justify-center gap-1.5 w-full py-2 bg-surface hover:bg-surface-hover text-text-secondary rounded-lg text-[11px] font-medium transition-all border border-border">
            <RefreshCw size={10} />Retry
          </button>
        )}
      </div>
    </div>
  )
}
