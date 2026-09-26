import { useState } from 'react'
import { Film, Loader2, AlertCircle } from 'lucide-react'
import type { Project, GeneratedAudio, RenderJob } from '../types'
import { fetchWithTimeout } from '../lib/fetch'
import { API_BASE } from '../lib/api'
import { useToast } from './Toast'

interface MakeShortButtonProps {
  project: Project | null
  generatedAudio: GeneratedAudio | null
  onRenderStart: (job: RenderJob) => void
  videoFolders?: string[]
}

export function MakeShortButton({ project, generatedAudio, onRenderStart, videoFolders }: MakeShortButtonProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const toast = useToast()

  const isDisabled = !project || !generatedAudio || loading

  const handleMakeShort = async () => {
    if (!project || !generatedAudio) return
    setLoading(true); setError(null)
    const toastId = toast.loading('Starting render...')
    try {
      const response = await fetchWithTimeout(`${API_BASE}/renders/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: project.id,
          generated_audio_id: generatedAudio.id,
          video_folders: videoFolders && videoFolders.length > 0 ? videoFolders : null,
        }),
        timeout: 30000,
      })
      if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        throw new Error(err.detail || 'Failed to start render')
      }
      onRenderStart(await response.json())
      toast.updateToast(toastId, { type: 'success', message: 'Render started' })
      setTimeout(() => toast.removeToast(toastId), 2000)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to start render'
      setError(msg)
      toast.updateToast(toastId, { type: 'error', message: 'Render failed', detail: msg })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-1.5">
      <button
        onClick={handleMakeShort}
        disabled={isDisabled}
        className={`w-full py-2.5 px-4 rounded-xl font-medium text-sm flex items-center justify-center gap-2 transition-all ${
          isDisabled
            ? 'bg-surface text-text-muted border border-border cursor-not-allowed'
            : 'bg-gradient-to-r from-accent to-accent-hover text-white shadow-md shadow-accent/20 hover:shadow-glow active:scale-[0.98]'
        }`}
      >
        {loading ? (
          <><Loader2 size={15} className="animate-spin" /><span>Rendering...</span></>
        ) : (
          <><Film size={15} /><span>Make Short</span></>
        )}
      </button>
      {error && (
        <div className="flex items-center gap-1.5 text-[10px] text-red-400 bg-red-500/10 px-2 py-1 rounded-lg">
          <AlertCircle size={10} /><span>{error}</span>
        </div>
      )}
      {!project && <p className="text-[10px] text-text-muted text-center">Select a project first</p>}
      {project && !generatedAudio && <p className="text-[10px] text-text-muted text-center">Generate voice first</p>}
    </div>
  )
}
