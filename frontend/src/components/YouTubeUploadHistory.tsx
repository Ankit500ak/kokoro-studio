import { useState, useEffect, useCallback } from 'react'
import { fetchUploads, type YouTubeUpload } from '../lib/youtubeApi'
import { Youtube, ExternalLink, CheckCircle2, XCircle, Loader2, Clock, RefreshCw } from 'lucide-react'

export function YouTubeUploadHistory() {
  const [uploads, setUploads] = useState<YouTubeUpload[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<string | null>(null)

  const loadUploads = useCallback(async () => {
    try {
      const data = await fetchUploads(30, filter || undefined)
      setUploads(data.items)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }, [filter])

  useEffect(() => { loadUploads() }, [loadUploads])

  const STATUS_ICON: Record<string, React.ReactNode> = {
    pending: <Clock size={11} className="text-text-muted" />,
    queued: <Clock size={11} className="text-yellow-400" />,
    uploading: <Loader2 size={11} className="text-blue-400 animate-spin" />,
    uploaded: <CheckCircle2 size={11} className="text-green-400" />,
    failed: <XCircle size={11} className="text-red-400" />,
    retrying: <RefreshCw size={11} className="text-yellow-400 animate-spin" />,
  }

  return (
    <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Youtube size={13} className="text-red-500" />
          <span className="text-xs font-semibold text-text-primary">YouTube Uploads</span>
        </div>
        <button onClick={loadUploads} className="text-[10px] text-text-muted hover:text-text-primary">
          <RefreshCw size={10} />
        </button>
      </div>

      <div className="flex gap-1 px-3 pt-2 pb-1">
        {[null, 'uploaded', 'pending', 'failed'].map((f) => (
          <button
            key={f || 'all'}
            onClick={() => setFilter(f)}
            className={`text-[9px] px-2 py-0.5 rounded-full transition-colors ${
              filter === f ? 'bg-accent text-white' : 'bg-surface text-text-muted hover:text-text-primary'
            }`}
          >
            {f || 'All'}
          </button>
        ))}
      </div>

      <div className="max-h-64 overflow-y-auto custom-scrollbar">
        {loading ? (
          <div className="p-3 text-[11px] text-text-muted">Loading...</div>
        ) : uploads.length === 0 ? (
          <div className="p-3 text-center text-[11px] text-text-muted">No uploads yet</div>
        ) : (
          uploads.map((u) => (
            <div key={u.id} className="px-3 py-2 border-b border-border/30 last:border-b-0 hover:bg-surface-hover transition-colors">
              <div className="flex items-start gap-2">
                {STATUS_ICON[u.status] || <Clock size={11} className="text-text-muted" />}
                <div className="flex-1 min-w-0">
                  <div className="text-[11px] font-medium text-text-primary truncate">{u.title}</div>
                  <div className="flex items-center gap-2 text-[9px] text-text-muted mt-0.5">
                    <span className="capitalize">{u.privacy_status}</span>
                    {u.uploaded_at && <span>{new Date(u.uploaded_at).toLocaleDateString()}</span>}
                    {u.video_url && (
                      <a href={u.video_url} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:text-blue-300 flex items-center gap-0.5">
                        <ExternalLink size={8} /> link
                      </a>
                    )}
                  </div>
                  {u.error_message && (
                    <div className="text-[9px] text-red-400 mt-0.5 truncate">{u.error_message}</div>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
