import { useEffect, useRef } from 'react'
import { X, Download } from 'lucide-react'
import { API_BASE } from '../lib/api'

interface VideoModalProps {
  src: string
  filename?: string
  onClose: () => void
}

export function VideoModal({ src, filename, onClose }: VideoModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handleEsc)
    return () => document.removeEventListener('keydown', handleEsc)
  }, [onClose])

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
      onClick={(e) => { if (e.target === overlayRef.current) onClose() }}
    >
      <div className="relative max-w-[90vw] max-h-[90vh] w-auto">
        <button
          onClick={onClose}
          className="absolute -top-3 -right-3 z-10 p-1.5 bg-surface-elevated rounded-full border border-border text-text-muted hover:text-text-primary hover:bg-surface-hover transition-all shadow-lg"
        >
          <X size={14} />
        </button>

        <video
          src={src}
          controls
          autoPlay
          className="rounded-xl max-h-[85vh] max-w-full shadow-2xl"
        />

        {filename && (
          <div className="absolute bottom-0 left-0 right-0 p-3 bg-gradient-to-t from-black/80 to-transparent rounded-b-xl flex items-center justify-between">
            <span className="text-xs text-white/80 truncate">{filename}</span>
            <a
              href={src}
              download={filename}
              className="p-1.5 bg-white/10 hover:bg-white/20 rounded-lg transition-all"
            >
              <Download size={12} className="text-white" />
            </a>
          </div>
        )}
      </div>
    </div>
  )
}
