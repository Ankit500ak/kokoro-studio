import { useState, useEffect, useCallback } from 'react'
import { Upload, Film, Trash2, Clock, Play, X } from 'lucide-react'
import type { VideoAsset } from '../types'
import { fetchWithTimeout } from '../lib/fetch'
import { API_BASE } from '../lib/api'
import { VideoModal } from './VideoModal'
import { SkeletonPanel, EmptyState } from './Skeleton'
import { useToast } from './Toast'

interface MediaLibraryProps {
  onSelectAsset: (asset: VideoAsset) => void
  selectedAssetId?: string | null
}

export function MediaLibrary({ onSelectAsset, selectedAssetId }: MediaLibraryProps) {
  const [assets, setAssets] = useState<VideoAsset[]>([])
  const [totalCount, setTotalCount] = useState(0)
  const [loading, setLoading] = useState(true)
  const [uploading, setUploading] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [dragActive, setDragActive] = useState(false)
  const [videoModal, setVideoModal] = useState<{ src: string; filename?: string } | null>(null)
  const toast = useToast()

  const fetchAssets = useCallback(async () => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/media/`, { timeout: 8000 })
      if (!response.ok) throw new Error('Failed')
      const data = await response.json()
      setAssets(Array.isArray(data?.items) ? data.items : [])
      setTotalCount(data?.total || 0)
    } catch (err) { console.error('Failed to fetch assets:', err) } finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchAssets() }, [fetchAssets])

  useEffect(() => {
    const interval = setInterval(fetchAssets, 10000)
    return () => clearInterval(interval)
  }, [fetchAssets])

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    const file = files[0]
    if (!file.type.startsWith('video/')) return
    setUploading(true)
    setUploadProgress(0)
    const toastId = toast.loading(`Uploading ${file.name}...`)
    try {
      // Simulate progress during upload
      const progressInterval = setInterval(() => {
        setUploadProgress(prev => Math.min(prev + Math.random() * 15, 90))
      }, 500)

      const formData = new FormData(); formData.append('file', file)
      const response = await fetchWithTimeout(`${API_BASE}/media/upload`, { method: 'POST', body: formData, timeout: 60000 })
      clearInterval(progressInterval)
      setUploadProgress(100)

      if (!response.ok) throw new Error('Upload failed')
      const newAsset = await response.json()
      setAssets(prev => [newAsset, ...prev])
      setTotalCount(prev => prev + 1)
      toast.updateToast(toastId, { type: 'success', message: 'Video uploaded', detail: file.name })
      setTimeout(() => toast.removeToast(toastId), 2000)
    } catch (err) {
      toast.updateToast(toastId, { type: 'error', message: 'Upload failed', detail: err instanceof Error ? err.message : undefined })
      console.error('Upload failed:', err)
    } finally {
      setUploading(false)
      setTimeout(() => setUploadProgress(0), 500)
    }
  }

  const deleteAsset = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Delete this video?')) return
    try {
      await fetchWithTimeout(`${API_BASE}/media/${id}`, { method: 'DELETE' })
      setAssets(prev => prev.filter(a => a.id !== id))
      setTotalCount(prev => Math.max(0, prev - 1))
      toast.success('Video deleted')
    } catch {
      toast.error('Failed to delete video')
    }
  }

  const handlePlay = (asset: VideoAsset, e: React.MouseEvent) => {
    e.stopPropagation()
    setVideoModal({
      src: `${API_BASE}/media/${asset.id}/file`,
      filename: asset.original_name || asset.filename,
    })
  }

  const fmtDuration = (s?: number) => { if (!s) return '--'; return `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}` }

  return (
    <>
      <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
        <div className="px-3 py-2 border-b border-border/50 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Film size={13} className="text-accent" />
            <span className="text-xs font-semibold text-text-primary">Media</span>
            <span className="text-[10px] text-text-muted">({totalCount})</span>
          </div>
          <label className="flex items-center gap-1 px-2 py-0.5 bg-accent/10 hover:bg-accent/20 text-accent text-[10px] font-medium rounded transition-all cursor-pointer">
            <Upload size={9} />Upload
            <input type="file" accept="video/*" className="hidden" onChange={(e) => handleUpload(e.target.files)} disabled={uploading} />
          </label>
        </div>

        <div
          className={`mx-2 mt-2 border border-dashed rounded-lg transition-all ${dragActive ? 'border-accent bg-accent/5 p-3' : 'border-border/30 hover:border-border p-2'}`}
          onDrop={(e) => { e.preventDefault(); setDragActive(false); handleUpload(e.dataTransfer.files) }}
          onDragOver={(e) => { e.preventDefault(); setDragActive(true) }}
          onDragLeave={() => setDragActive(false)}
        >
          {uploading && uploadProgress > 0 && (
            <div className="mb-2">
              <div className="h-1 bg-surface rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-accent to-accent-hover rounded-full transition-all duration-500 ease-out"
                  style={{ width: `${uploadProgress}%` }}
                />
              </div>
              <p className="text-[9px] text-accent text-center mt-1">{Math.round(uploadProgress)}%</p>
            </div>
          )}
          <label className="flex flex-col items-center gap-1 cursor-pointer">
            <Upload size={14} className={dragActive ? 'text-accent' : 'text-text-muted/40'} />
            <span className="text-[9px] text-text-muted text-center">
              {uploading ? <span className="text-accent">Uploading...</span> : dragActive ? <span className="text-accent">Drop here</span> : 'Drop or click'}
            </span>
            <input type="file" accept="video/*" className="hidden" onChange={(e) => handleUpload(e.target.files)} disabled={uploading} />
          </label>
        </div>

        <div className="p-1 space-y-0.5 max-h-[180px] overflow-y-auto custom-scrollbar">
          {loading ? (
            <SkeletonPanel rows={3} />
          ) : assets.length === 0 ? (
            <EmptyState
              icon={<Film size={20} />}
              title="No videos yet"
              description="Upload or drag a video to get started"
            />
          ) : assets.map((asset, i) => (
            <div
              key={asset.id}
              onClick={() => onSelectAsset(asset)}
              className={`list-item-enter group flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer transition-all ${
                selectedAssetId === asset.id ? 'bg-accent/10 border border-accent/30' : 'hover:bg-surface-hover border border-transparent'
              }`}
              style={{ animationDelay: `${i * 30}ms` }}
            >
              <div className="w-10 h-7 bg-surface rounded flex items-center justify-center flex-shrink-0 relative overflow-hidden">
                <Film size={10} className="text-text-muted/30" />
                <button
                  onClick={(e) => handlePlay(asset, e)}
                  className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity bg-black/30"
                >
                  <Play size={8} className="text-white" />
                </button>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-[10px] font-medium text-text-primary truncate">{asset.original_name || asset.filename}</p>
                <div className="flex items-center gap-1.5 mt-0.5">
                  <span className="text-[8px] text-text-muted flex items-center gap-0.5"><Clock size={6} />{fmtDuration(asset.duration)}</span>
                  <span className="text-[8px] text-text-muted">{asset.width && asset.height ? `${asset.width}x${asset.height}` : '--'}</span>
                </div>
              </div>
              <button onClick={(e) => deleteAsset(asset.id, e)} className="p-0.5 rounded text-text-muted hover:text-red-400 hover:bg-red-500/10 opacity-0 group-hover:opacity-100 transition-all">
                <Trash2 size={8} />
              </button>
            </div>
          ))}
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
