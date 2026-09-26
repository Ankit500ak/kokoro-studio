import { useState, useEffect, useCallback, useRef } from 'react'
import { Film, Download, Clock, CheckCircle2, XCircle, RefreshCw, Play, AlertTriangle, Trash2 } from 'lucide-react'
import type { RenderJob, RenderOutput } from '../types'
import { fetchWithTimeout } from '../lib/fetch'
import { API_BASE } from '../lib/api'
import { VideoModal } from './VideoModal'
import { YouTubeUploadButton } from './YouTubeUploadButton'
import { SkeletonPanel, EmptyState } from './Skeleton'
import { useToast } from './Toast'

interface RenderHistoryItem { job: RenderJob; output?: RenderOutput }

export function RenderHistory() {
  const [renders, setRenders] = useState<RenderHistoryItem[]>([])
  const rendersRef = useRef(renders)
  rendersRef.current = renders
  const [loading, setLoading] = useState(true)
  const [videoModal, setVideoModal] = useState<{ src: string; filename?: string } | null>(null)
  const toast = useToast()

  const fetchRenders = useCallback(async () => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/renders/`, { timeout: 8000 })
      if (!response.ok) throw new Error('Failed')
      const data = await response.json()
      const items = Array.isArray(data?.items) ? data.items : []
      const result = await Promise.all(
        items.map(async (job: RenderJob) => {
          if (job.status === 'completed') {
            try {
              const r = await fetchWithTimeout(`${API_BASE}/renders/${job.id}/output`, { timeout: 5000 })
              if (r.ok) return { job, output: await r.json() }
            } catch {}
          }
          return { job }
        })
      )
      setRenders(result)
    } catch (err) { console.error('Failed:', err) } finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchRenders() }, [fetchRenders])

  useEffect(() => {
    const hasActive = renders.some(r => r.job.status === 'queued' || r.job.status === 'rendering')
    if (!hasActive) return

    const interval = setInterval(async () => {
      try {
        const response = await fetchWithTimeout(`${API_BASE}/renders/`, { timeout: 8000 })
        if (!response.ok) return
        const data = await response.json()
        const items = Array.isArray(data?.items) ? data.items : []
        const currentRenders = rendersRef.current
        const result = await Promise.all(
          items.map(async (job: RenderJob) => {
            const existing = currentRenders.find(r => r.job.id === job.id)
            if (job.status === 'completed' && existing && !existing.output) {
              try {
                const r = await fetchWithTimeout(`${API_BASE}/renders/${job.id}/output`, { timeout: 5000 })
                if (r.ok) return { job, output: await r.json() }
              } catch {}
            }
            return { job, output: existing?.output }
          })
        )
        setRenders(result)
      } catch {}
    }, 3000)
    return () => clearInterval(interval)
  }, [renders.some(r => r.job.status === 'queued' || r.job.status === 'rendering')])

  const handleRetry = async (job: RenderJob) => {
    const toastId = toast.loading('Retrying render...')
    try {
      const r = await fetchWithTimeout(`${API_BASE}/renders/${job.id}/retry`, { method: 'POST', timeout: 60000 })
      if (r.ok) {
        toast.updateToast(toastId, { type: 'success', message: 'Render restarted' })
        setTimeout(() => toast.removeToast(toastId), 2000)
        setRenders([]); setLoading(true); fetchRenders()
      } else {
        throw new Error('Retry failed')
      }
    } catch (err) {
      toast.updateToast(toastId, { type: 'error', message: 'Retry failed' })
      console.error('Retry failed:', err)
    }
  }

  const handleDelete = async (job: RenderJob, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      const r = await fetchWithTimeout(`${API_BASE}/renders/${job.id}`, { method: 'DELETE', timeout: 10000 })
      if (r.ok) {
        setRenders(prev => prev.filter(r => r.job.id !== job.id))
        toast.success('Render deleted')
      }
    } catch (err) {
      toast.error('Failed to delete render')
      console.error('Delete failed:', err)
    }
  }

  const handlePlay = (job: RenderJob) => {
    setVideoModal({
      src: `${API_BASE}/renders/${job.id}/file`,
      filename: `${job.id}.mp4`,
    })
  }

  const fmtDuration = (s?: number) => { if (!s) return '--'; return `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}` }

  return (
    <>
      <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
        <div className="px-3 py-2 border-b border-border/50 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Film size={13} className="text-accent" />
            <span className="text-xs font-semibold text-text-primary">Renders</span>
            <span className="text-[10px] text-text-muted">({renders.length})</span>
          </div>
          <button
            onClick={() => { setLoading(true); fetchRenders() }}
            className="p-1 rounded text-text-muted hover:text-accent hover:bg-accent/10 transition-all"
            title="Refresh"
          >
            <RefreshCw size={11} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
        <div className="p-1 space-y-0.5 max-h-[180px] overflow-y-auto custom-scrollbar">
          {loading ? (
            <SkeletonPanel rows={3} />
          ) : renders.length === 0 ? (
            <EmptyState
              icon={<Film size={20} />}
              title="No renders yet"
              description="Generate audio and click Make Short"
            />
          ) : renders.map(({ job, output }, i) => {
            const fileMissing = job.error_code === 'FILE_MISSING'
            const isFailed = job.status === 'failed'
            const isCompleted = job.status === 'completed'
            const isActive = job.status === 'queued' || job.status === 'rendering'

            return (
              <div
                key={job.id}
                className={`list-item-enter flex items-center gap-2 px-2 py-1.5 rounded-lg transition-all ${
                  isCompleted && !fileMissing ? 'hover:bg-surface-hover cursor-pointer' : ''
                }`}
                style={{ animationDelay: `${i * 30}ms` }}
                onClick={() => isCompleted && !fileMissing && handlePlay(job)}
              >
                <div className="flex-shrink-0">
                  {isCompleted && !fileMissing ? <CheckCircle2 size={11} className="text-success" /> :
                   fileMissing ? <AlertTriangle size={11} className="text-yellow-400" /> :
                   isFailed ? <XCircle size={11} className="text-red-400" /> :
                   <Clock size={11} className="text-text-muted animate-pulse" />}
                </div>
                <div className="flex-1 min-w-0">
                  <p className={`text-[10px] font-medium truncate ${
                    fileMissing ? 'text-yellow-400' : 'text-text-primary'
                  }`}>
                    {fileMissing ? 'File missing' :
                     isCompleted ? (output?.video_filename || 'Video') :
                     isFailed ? (job.error_message || 'Failed') :
                     job.current_stage || job.status}
                  </p>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    {output?.duration && <span className="text-[8px] text-text-muted">{fmtDuration(output.duration)}</span>}
                    {output?.file_size && <span className="text-[8px] text-text-muted">{(output.file_size / (1024 * 1024)).toFixed(1)}MB</span>}
                    {isActive && <span className="text-[8px] text-accent">{job.progress || 0}%</span>}
                  </div>
                </div>
                <div className="flex items-center gap-0.5">
                  {isCompleted && !fileMissing && (
                    <button onClick={(e) => { e.stopPropagation(); handlePlay(job) }} className="p-1 rounded text-text-muted hover:text-accent hover:bg-accent/10 transition-all">
                      <Play size={10} />
                    </button>
                  )}
                  {isCompleted && !fileMissing && (
                    <a href={`${API_BASE}/renders/${job.id}/file`} download onClick={(e) => e.stopPropagation()} className="p-1 rounded text-text-muted hover:text-accent hover:bg-accent/10 transition-all">
                      <Download size={10} />
                    </a>
                  )}
                  {isCompleted && !fileMissing && output && (
                    <YouTubeUploadButton
                      renderOutputId={output.id}
                      compact
                    />
                  )}
                  {(isFailed || fileMissing) && (
                    <button onClick={(e) => { e.stopPropagation(); handleRetry(job) }} className="p-1 rounded text-text-muted hover:text-accent hover:bg-accent/10 transition-all" title="Retry">
                      <RefreshCw size={10} />
                    </button>
                  )}
                  {(isFailed || fileMissing) && (
                    <button onClick={(e) => handleDelete(job, e)} className="p-1 rounded text-text-muted hover:text-red-400 hover:bg-red-500/10 transition-all" title="Delete">
                      <Trash2 size={10} />
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {videoModal && (
        <VideoModal
          src={videoModal.src}
          filename={videoModal.filename}
          onClose={() => setVideoModal(null)}
        />
      )}
    </>
  )
}
