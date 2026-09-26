import { useState } from 'react'
import { uploadToYouTube, type YouTubeUpload } from '../lib/youtubeApi'
import { Youtube, Upload, Loader2, CheckCircle2, XCircle, Eye, EyeOff, Lock, Globe, ExternalLink, AlertTriangle } from 'lucide-react'
import { useToast } from './Toast'

interface YouTubeUploadButtonProps {
  renderOutputId: string
  niche?: string
  topic?: string
  videoTitle?: string
  onUploadComplete?: (upload: YouTubeUpload) => void
  compact?: boolean
}

export function YouTubeUploadButton({
  renderOutputId,
  niche = 'psychology',
  topic = '',
  videoTitle,
  onUploadComplete,
  compact = false,
}: YouTubeUploadButtonProps) {
  const [showModal, setShowModal] = useState(false)
  const [privacy, setPrivacy] = useState<'public' | 'unlisted' | 'private'>('public')
  const [customTitle, setCustomTitle] = useState(videoTitle || '')
  const [useAutoMeta, setUseAutoMeta] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<YouTubeUpload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const toast = useToast()

  const handleUpload = async () => {
    setUploading(true)
    setError(null)
    const toastId = toast.loading('Uploading to YouTube...')
    try {
      const upload = await uploadToYouTube({
        render_output_id: renderOutputId,
        privacy_status: privacy,
        auto_metadata: useAutoMeta,
        title: useAutoMeta ? undefined : customTitle,
        niche,
        topic,
      })
      setResult(upload)
      onUploadComplete?.(upload)
      toast.updateToast(toastId, { type: 'success', message: 'Uploaded to YouTube', detail: upload.video_id ? `Video ID: ${upload.video_id}` : undefined })
      setTimeout(() => toast.removeToast(toastId), 3000)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Upload failed'
      setError(msg)
      toast.updateToast(toastId, { type: 'error', message: 'YouTube upload failed', detail: msg })
    } finally {
      setUploading(false)
    }
  }

  if (compact) {
    return (
      <>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-red-500/10 text-red-400 text-[10px] font-medium hover:bg-red-500/20 transition-colors"
          title="Upload to YouTube"
        >
          <Youtube size={11} />
          YouTube
        </button>

        {showModal && (
          <YouTubeUploadModal
            privacy={privacy}
            setPrivacy={setPrivacy}
            customTitle={customTitle}
            setCustomTitle={setCustomTitle}
            useAutoMeta={useAutoMeta}
            setUseAutoMeta={setUseAutoMeta}
            uploading={uploading}
            result={result}
            error={error}
            onUpload={handleUpload}
            onClose={() => { setShowModal(false); setResult(null); setError(null) }}
          />
        )}
      </>
    )
  }

  return (
    <>
      <button
        onClick={() => setShowModal(true)}
        className="flex items-center justify-center gap-2 py-2 rounded-lg bg-red-600 text-white text-[11px] font-medium hover:bg-red-700 transition-colors"
      >
        <Youtube size={14} />
        Upload to YouTube
      </button>

      {showModal && (
        <YouTubeUploadModal
          privacy={privacy}
          setPrivacy={setPrivacy}
          customTitle={customTitle}
          setCustomTitle={setCustomTitle}
          useAutoMeta={useAutoMeta}
          setUseAutoMeta={setUseAutoMeta}
          uploading={uploading}
          result={result}
          error={error}
          onUpload={handleUpload}
          onClose={() => { setShowModal(false); setResult(null); setError(null) }}
        />
      )}
    </>
  )
}

function YouTubeUploadModal({
  privacy, setPrivacy,
  customTitle, setCustomTitle,
  useAutoMeta, setUseAutoMeta,
  uploading, result, error,
  onUpload, onClose,
}: {
  privacy: 'public' | 'unlisted' | 'private'
  setPrivacy: (v: 'public' | 'unlisted' | 'private') => void
  customTitle: string
  setCustomTitle: (v: string) => void
  useAutoMeta: boolean
  setUseAutoMeta: (v: boolean) => void
  uploading: boolean
  result: YouTubeUpload | null
  error: string | null
  onUpload: () => void
  onClose: () => void
}) {
  const PRIVACY_OPTIONS = [
    { value: 'public' as const, label: 'Public', icon: <Globe size={12} />, desc: 'Visible to everyone' },
    { value: 'unlisted' as const, label: 'Unlisted', icon: <Eye size={12} />, desc: 'Only visible with link' },
    { value: 'private' as const, label: 'Private', icon: <Lock size={12} />, desc: 'Only you can see' },
  ]

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div className="bg-surface-elevated rounded-xl border border-border w-full max-w-md mx-4 overflow-hidden shadow-2xl" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="px-4 py-3 border-b border-border/50 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Youtube size={16} className="text-red-500" />
            <span className="text-sm font-semibold text-text-primary">Upload to YouTube</span>
          </div>
          <button onClick={onClose} className="text-text-muted hover:text-text-primary text-lg">&times;</button>
        </div>

        <div className="p-4 space-y-4">
          {result ? (
            <div className="space-y-3">
              <div className="flex items-center gap-3 p-3 bg-green-500/10 rounded-lg border border-green-500/20">
                <CheckCircle2 size={20} className="text-green-400" />
                <div>
                  <div className="text-[12px] font-medium text-green-400">Upload Queued!</div>
                  <div className="text-[10px] text-text-muted">{result.title}</div>
                </div>
              </div>
              {result.video_url && (
                <a
                  href={result.video_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-[11px] text-blue-400 hover:text-blue-300"
                >
                  <ExternalLink size={11} /> Open on YouTube
                </a>
              )}
              <button onClick={onClose} className="w-full py-2 rounded-lg bg-surface hover:bg-surface-hover text-[11px] text-text-primary">Close</button>
            </div>
          ) : (
            <>
              {/* Privacy */}
              <div>
                <label className="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1.5 block">Visibility</label>
                <div className="grid grid-cols-3 gap-1.5">
                  {PRIVACY_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => setPrivacy(opt.value)}
                      className={`flex flex-col items-center gap-1 p-2 rounded-lg border transition-all ${
                        privacy === opt.value
                          ? 'bg-accent/15 border-accent/30 text-accent'
                          : 'bg-surface border-border/30 text-text-muted hover:text-text-primary'
                      }`}
                    >
                      {opt.icon}
                      <span className="text-[10px] font-medium">{opt.label}</span>
                      <span className="text-[8px] opacity-70">{opt.desc}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* Auto metadata toggle */}
              <div className="flex items-center justify-between p-2 bg-surface rounded-lg">
                <div>
                  <div className="text-[11px] font-medium text-text-primary">Auto-generate metadata</div>
                  <div className="text-[9px] text-text-muted">Title, description, tags via AI</div>
                </div>
                <button
                  onClick={() => setUseAutoMeta(!useAutoMeta)}
                  className={`w-10 h-5 rounded-full transition-colors ${useAutoMeta ? 'bg-accent' : 'bg-surface-hover'}`}
                >
                  <div className={`w-4 h-4 rounded-full bg-white shadow transition-transform ${useAutoMeta ? 'translate-x-5' : 'translate-x-0.5'}`} />
                </button>
              </div>

              {/* Custom title */}
              {!useAutoMeta && (
                <div>
                  <label className="text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1 block">Title</label>
                  <input
                    type="text"
                    value={customTitle}
                    onChange={(e) => setCustomTitle(e.target.value)}
                    placeholder="Enter video title..."
                    className="w-full bg-surface border border-border/30 rounded-lg px-3 py-2 text-[12px] text-text-primary outline-none focus:border-accent"
                    maxLength={100}
                  />
                  <div className="text-[9px] text-text-muted mt-1">{customTitle.length}/100</div>
                </div>
              )}

              {error && (
                <div className={`flex items-center gap-2 p-2 rounded-lg text-[11px] ${
                  error.includes('quota') || error.includes('429')
                    ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                    : 'bg-red-500/10 text-red-400'
                }`}>
                  {error.includes('quota') || error.includes('429')
                    ? <AlertTriangle size={12} />
                    : <XCircle size={12} />
                  }
                  {error}
                </div>
              )}

              {/* Upload button */}
              <button
                onClick={onUpload}
                disabled={uploading}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-red-600 text-white text-[12px] font-medium hover:bg-red-700 disabled:opacity-50 transition-colors"
              >
                {uploading ? (
                  <><Loader2 size={14} className="animate-spin" /> Uploading...</>
                ) : (
                  <><Upload size={14} /> Upload Video</>
                )}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
