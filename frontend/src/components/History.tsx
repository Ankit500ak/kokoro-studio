import { useAppStore } from '../hooks/useStore'
import { Play, Download, Clock } from 'lucide-react'
import { useRef, useCallback } from 'react'
import { API_BASE } from '../lib/api'
import { EmptyState } from './Skeleton'

export function History() {
  const history = useAppStore((s) => s.history)
  const audioRefs = useRef<Map<string, HTMLAudioElement>>(new Map())

  const playAudio = useCallback((item: { id: string; filename: string }) => {
    audioRefs.current.forEach((a) => a.pause())
    const existing = audioRefs.current.get(item.id)
    if (existing) { existing.pause(); audioRefs.current.delete(item.id); return }
    const audio = new Audio(`${API_BASE}/audio/${item.filename}`)
    audioRefs.current.set(item.id, audio); audio.play().catch(() => {})
  }, [])

  if (history.length === 0) {
    return (
      <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
        <div className="px-3 py-2 border-b border-border/50 flex items-center gap-2">
          <Clock size={13} className="text-accent" />
          <span className="text-xs font-semibold text-text-primary">History</span>
        </div>
        <EmptyState
          icon={<Clock size={20} />}
          title="No history yet"
          description="Generated audio will appear here"
        />
      </div>
    )
  }

  return (
    <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border/50 flex items-center gap-2">
        <Clock size={13} className="text-accent" />
        <span className="text-xs font-semibold text-text-primary">History</span>
        <span className="text-[10px] text-text-muted">({history.length})</span>
      </div>
      <div className="p-1 space-y-0.5 max-h-[150px] overflow-y-auto custom-scrollbar">
        {history.map((item, i) => (
          <div key={item.id} className="list-item-enter group flex items-center gap-2 px-2 py-1 rounded-lg hover:bg-surface-hover transition-all" style={{ animationDelay: `${i * 30}ms` }}>
            <button onClick={() => playAudio(item)} className="w-6 h-6 rounded bg-accent/10 hover:bg-accent/20 flex items-center justify-center text-accent transition-all flex-shrink-0">
              <Play size={9} className="ml-px" />
            </button>
            <div className="flex-1 min-w-0">
              <p className="text-[10px] font-medium text-text-primary truncate">{item.voice}</p>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className="text-[8px] text-text-muted">{item.word_count}w</span>
                {item.duration && <span className="text-[8px] text-text-muted">{Math.round(item.duration)}s</span>}
              </div>
            </div>
            <a href={`${API_BASE}/audio/${item.filename}`} download={item.filename} className="p-0.5 rounded text-text-muted hover:text-accent opacity-0 group-hover:opacity-100 transition-all" title="Download">
              <Download size={9} />
            </a>
          </div>
        ))}
      </div>
    </div>
  )
}
