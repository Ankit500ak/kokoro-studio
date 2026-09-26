import { useState, useEffect, useCallback, useRef } from 'react'
import {
  fetchYouTubeStatus,
  startYouTubeAuth,
  disconnectYouTube,
  directUploadToYouTube,
  type YouTubeStatus,
  type YouTubeUpload,
} from '../lib/youtubeApi'
import {
  Youtube,
  CheckCircle2,
  XCircle,
  Loader2,
  Upload,
  Globe,
  Eye,
  Lock,
  FileVideo,
  X,
  ArrowRight,
  AlertTriangle,
} from 'lucide-react'

interface YouTubePanelProps {
  onUploadComplete?: (upload: YouTubeUpload) => void
}

export function YouTubePanel({ onUploadComplete }: YouTubePanelProps) {
  const [status, setStatus] = useState<YouTubeStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [connecting, setConnecting] = useState(false)

  // Upload state
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [privacy, setPrivacy] = useState<'public' | 'unlisted' | 'private'>('public')
  const [customTitle, setCustomTitle] = useState('')
  const [useAutoMeta, setUseAutoMeta] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [result, setResult] = useState<YouTubeUpload | null>(null)
  const [error, setError] = useState<string | null>(null)

  const fileInputRef = useRef<HTMLInputElement>(null)
  const dropZoneRef = useRef<HTMLDivElement>(null)

  const checkStatus = useCallback(async () => {
    try {
      const s = await fetchYouTubeStatus()
      setStatus(s)
    } catch {
      setStatus({ connected: false, channel_title: null, channel_id: null, expires_at: null })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { checkStatus() }, [checkStatus])

  // Poll status after connecting
  useEffect(() => {
    if (connecting) {
      const interval = setInterval(checkStatus, 3000)
      const timeout = setTimeout(() => clearInterval(interval), 120000)
      return () => {
        clearInterval(interval)
        clearTimeout(timeout)
      }
    }
  }, [connecting, checkStatus])

  const handleConnect = async () => {
    setConnecting(true)
    try {
      const { auth_url } = await startYouTubeAuth()
      window.open(auth_url, '_blank', 'width=600,height=700')
    } catch (err) {
      console.error(err)
      setConnecting(false)
    }
  }

  const handleDisconnect = async () => {
    try {
      await disconnectYouTube()
      setStatus({ connected: false, channel_title: null, channel_id: null, expires_at: null })
    } catch (err) {
      console.error(err)
    }
  }

  const handleFileSelect = (file: File) => {
    if (!file.type.startsWith('video/')) {
      setError('Please select a video file')
      return
    }
    setSelectedFile(file)
    setCustomTitle(file.name.replace(/\.[^/.]+$/, ''))
    setError(null)
    setResult(null)

    // Create preview
    const url = URL.createObjectURL(file)
    setPreviewUrl(url)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dropZoneRef.current?.classList.remove('border-accent', 'bg-accent/5')

    const files = e.dataTransfer.files
    if (files.length > 0) {
      handleFileSelect(files[0])
    }
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dropZoneRef.current?.classList.add('border-accent', 'bg-accent/5')
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    dropZoneRef.current?.classList.remove('border-accent', 'bg-accent/5')
  }

  const handleUpload = async () => {
    if (!selectedFile) return

    setUploading(true)
    setError(null)
    try {
      const upload = await directUploadToYouTube({
        video: selectedFile,
        privacy_status: privacy,
        auto_metadata: useAutoMeta,
        title: useAutoMeta ? undefined : customTitle,
        niche: 'psychology',
        topic: customTitle,
      })
      setResult(upload)
      onUploadComplete?.(upload)
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const resetUpload = () => {
    setSelectedFile(null)
    if (previewUrl) URL.revokeObjectURL(previewUrl)
    setPreviewUrl(null)
    setCustomTitle('')
    setResult(null)
    setError(null)
  }

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const PRIVACY_OPTIONS = [
    { value: 'public' as const, label: 'Public', icon: <Globe size={12} /> },
    { value: 'unlisted' as const, label: 'Unlisted', icon: <Eye size={12} /> },
    { value: 'private' as const, label: 'Private', icon: <Lock size={12} /> },
  ]

  if (loading) {
    return (
      <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
        <div className="px-3 py-2 border-b border-border/50 flex items-center gap-2">
          <Youtube size={13} className="text-red-500" />
          <span className="text-xs font-semibold text-text-primary">YouTube</span>
        </div>
        <div className="p-3 text-[11px] text-text-muted">Checking connection...</div>
      </div>
    )
  }

  return (
    <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Youtube size={13} className="text-red-500" />
          <span className="text-xs font-semibold text-text-primary">YouTube</span>
        </div>
        {status?.connected && (
          <div className="flex items-center gap-1">
            <CheckCircle2 size={11} className="text-green-400" />
            <span className="text-[9px] text-green-400">Connected</span>
          </div>
        )}
      </div>

      <div className="p-3">
        {/* Step 1: Connect */}
        {!status?.connected ? (
          <div className="space-y-3">
            <p className="text-[10px] text-text-muted">
              Connect your YouTube channel to upload videos directly.
            </p>

            {connecting ? (
              <div className="flex items-center gap-2 p-3 bg-surface rounded-lg">
                <Loader2 size={14} className="text-blue-400 animate-spin" />
                <div>
                  <div className="text-[11px] font-medium text-text-primary">Waiting for authorization...</div>
                  <div className="text-[9px] text-text-muted">Complete the popup to connect</div>
                </div>
              </div>
            ) : (
              <button
                onClick={handleConnect}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-red-600 text-white text-[11px] font-medium hover:bg-red-700 transition-colors"
              >
                <Youtube size={13} />
                Connect YouTube
                <ArrowRight size={12} />
              </button>
            )}
          </div>
        ) : result ? (
          /* Step 3: Success */
          <div className="space-y-3">
            <div className="flex items-center gap-3 p-3 bg-green-500/10 rounded-lg border border-green-500/20">
              <CheckCircle2 size={18} className="text-green-400" />
              <div>
                <div className="text-[11px] font-medium text-green-400">Upload Queued!</div>
                <div className="text-[9px] text-text-muted">{result.title}</div>
              </div>
            </div>
            <button
              onClick={resetUpload}
              className="w-full py-2 rounded-lg bg-surface hover:bg-surface-hover text-[11px] text-text-primary transition-colors"
            >
              Upload Another Video
            </button>
          </div>
        ) : selectedFile ? (
          /* Step 2b: File Selected - Show Options */
          <div className="space-y-3">
            {/* File Preview */}
            <div className="relative bg-surface rounded-lg overflow-hidden">
              {previewUrl && (
                <video
                  src={previewUrl}
                  className="w-full h-32 object-cover"
                  controls
                  preload="metadata"
                />
              )}
              <button
                onClick={resetUpload}
                className="absolute top-2 right-2 p-1 rounded-full bg-black/60 text-white hover:bg-black/80"
              >
                <X size={12} />
              </button>
              <div className="p-2 flex items-center gap-2">
                <FileVideo size={12} className="text-text-muted" />
                <span className="text-[10px] text-text-primary truncate flex-1">{selectedFile.name}</span>
                <span className="text-[9px] text-text-muted">{formatFileSize(selectedFile.size)}</span>
              </div>
            </div>

            {/* Connected Channel */}
            <div className="flex items-center gap-2 p-2 bg-surface rounded-lg">
              <div className="w-6 h-6 rounded-full bg-red-500/20 flex items-center justify-center">
                <Youtube size={10} className="text-red-500" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-[10px] font-medium text-text-primary truncate">{status?.channel_title || 'Unknown'}</div>
              </div>
              <button
                onClick={handleDisconnect}
                className="text-[9px] text-text-muted hover:text-red-400"
              >
                Disconnect
              </button>
            </div>

            {/* Privacy */}
            <div>
              <label className="text-[9px] font-semibold text-text-muted uppercase tracking-wider mb-1 block">
                Visibility
              </label>
              <div className="grid grid-cols-3 gap-1">
                {PRIVACY_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setPrivacy(opt.value)}
                    className={`flex items-center justify-center gap-1 py-1.5 rounded-lg border text-[10px] transition-all ${
                      privacy === opt.value
                        ? 'bg-accent/15 border-accent/30 text-accent'
                        : 'bg-surface border-border/30 text-text-muted hover:text-text-primary'
                    }`}
                  >
                    {opt.icon}
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Auto metadata toggle */}
            <div className="flex items-center justify-between p-2 bg-surface rounded-lg">
              <div>
                <div className="text-[10px] font-medium text-text-primary">Auto-generate metadata</div>
                <div className="text-[8px] text-text-muted">Title, description, tags via AI</div>
              </div>
              <button
                onClick={() => setUseAutoMeta(!useAutoMeta)}
                className={`w-9 h-5 rounded-full transition-colors ${useAutoMeta ? 'bg-accent' : 'bg-surface-hover'}`}
              >
                <div className={`w-3.5 h-3.5 rounded-full bg-white shadow transition-transform ${useAutoMeta ? 'translate-x-4.5' : 'translate-x-0.5'}`} />
              </button>
            </div>

            {/* Custom title */}
            {!useAutoMeta && (
              <div>
                <label className="text-[9px] font-semibold text-text-muted uppercase tracking-wider mb-1 block">
                  Title
                </label>
                <input
                  type="text"
                  value={customTitle}
                  onChange={(e) => setCustomTitle(e.target.value)}
                  placeholder="Enter video title..."
                  className="w-full bg-surface border border-border/30 rounded-lg px-2 py-1.5 text-[11px] text-text-primary outline-none focus:border-accent"
                  maxLength={100}
                />
                <div className="text-[8px] text-text-muted mt-0.5">{customTitle.length}/100</div>
              </div>
            )}

            {error && (
              <div className={`flex items-center gap-1.5 p-2 rounded-lg text-[10px] ${
                error.includes('quota') || error.includes('429')
                  ? 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                  : 'bg-red-500/10 text-red-400'
              }`}>
                {error.includes('quota') || error.includes('429')
                  ? <AlertTriangle size={11} />
                  : <XCircle size={11} />
                }
                {error}
              </div>
            )}

            {/* Upload button */}
            <button
              onClick={handleUpload}
              disabled={uploading || !selectedFile}
              className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-red-600 text-white text-[11px] font-medium hover:bg-red-700 disabled:opacity-50 transition-colors"
            >
              {uploading ? (
                <><Loader2 size={12} className="animate-spin" /> Uploading...</>
              ) : (
                <><Upload size={12} /> Upload to YouTube</>
              )}
            </button>
          </div>
        ) : (
          /* Step 2a: Drag & Drop Zone */
          <div className="space-y-2">
            <p className="text-[10px] text-text-muted">
              Drop a video file to upload to YouTube.
            </p>

            <div
              ref={dropZoneRef}
              onDrop={handleDrop}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onClick={() => fileInputRef.current?.click()}
              className="flex flex-col items-center justify-center gap-2 p-6 border-2 border-dashed border-border/50 rounded-lg cursor-pointer hover:border-border transition-colors"
            >
              <div className="w-10 h-10 rounded-full bg-surface flex items-center justify-center">
                <FileVideo size={20} className="text-text-muted" />
              </div>
              <div className="text-center">
                <div className="text-[11px] font-medium text-text-primary">
                  Drag & drop video here
                </div>
                <div className="text-[9px] text-text-muted mt-0.5">
                  or click to browse
                </div>
              </div>
              <div className="text-[8px] text-text-muted">
                MP4, MOV, AVI, WebM (max 128GB)
              </div>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept="video/*"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0]
                if (file) handleFileSelect(file)
              }}
            />

            <div className="flex items-center gap-2">
              <button
                onClick={handleDisconnect}
                className="text-[9px] text-text-muted hover:text-red-400"
              >
                Disconnect
              </button>
              <span className="text-[8px] text-text-muted">•</span>
              <span className="text-[9px] text-text-muted truncate">{status?.channel_title || 'Unknown'}</span>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
