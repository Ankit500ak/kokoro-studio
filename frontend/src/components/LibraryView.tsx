import { useState, useEffect, useCallback, useRef } from 'react'
import { Play, Download, Clock, Hash, Volume2, Trash2, Library, Search, ChevronLeft, ChevronRight } from 'lucide-react'
import { fetchWithTimeout } from '../lib/fetch'
import { API_BASE } from '../lib/api'
import { SkeletonPanel, EmptyState } from './Skeleton'
import { useToast } from './Toast'

interface AudioItem {
  id: string; filename: string; voice: string; mode: string; preset: string; text: string
  word_count: number; duration: number | null; speed: number | null; tone: string | null
  file_size: number | null; created_at: string | null
}

const PRESET_COLORS: Record<string, string> = {
  shorts: 'from-pink-500 to-rose-500', storytelling: 'from-amber-500 to-orange-500',
  mystery: 'from-violet-500 to-purple-600', documentary: 'from-blue-500 to-cyan-500',
  horror: 'from-red-600 to-rose-700', romantic: 'from-pink-400 to-rose-400',
  educational: 'from-emerald-500 to-teal-500', news: 'from-slate-500 to-gray-600',
}

export function LibraryView() {
  const [audioList, setAudioList] = useState<AudioItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [search, setSearch] = useState('')
  const [filterVoice, setFilterVoice] = useState<string | null>(null)
  const [filterPreset, setFilterPreset] = useState<string | null>(null)
  const audioRefs = useRef<Map<string, HTMLAudioElement>>(new Map())
  const perPage = 8
  const toast = useToast()

  const fetchLibrary = useCallback(async () => {
    setLoading(true)
    try {
      const params = new URLSearchParams()
      params.set('page', String(page)); params.set('per_page', String(perPage))
      if (filterVoice) params.set('voice', filterVoice)
      if (filterPreset) params.set('preset', filterPreset)
      if (search) params.set('search', search)
      const r = await fetchWithTimeout(`${API_BASE}/library/?${params}`, { timeout: 8000 })
      if (!r.ok) throw new Error('Failed')
      const d = await r.json(); setAudioList(Array.isArray(d?.items) ? d.items : []); setTotal(d?.total || 0)
    } catch (err) { console.error('Failed:', err) } finally { setLoading(false) }
  }, [page, filterVoice, filterPreset, search])

  useEffect(() => { fetchLibrary() }, [fetchLibrary])

  const playAudio = (item: AudioItem) => {
    audioRefs.current.forEach((a) => a.pause())
    const existing = audioRefs.current.get(item.id)
    if (existing) { existing.pause(); audioRefs.current.delete(item.id); return }
    const audio = new Audio(`${API_BASE}/library/${item.id}/file`)
    audioRefs.current.set(item.id, audio); audio.play().catch(() => {})
  }

  const deleteAudio = async (id: string) => {
    try {
      await fetchWithTimeout(`${API_BASE}/library/${id}`, { method: 'DELETE', timeout: 5000 })
      setTotal(prev => Math.max(0, prev - 1))
      setAudioList(prev => prev.filter(a => a.id !== id))
      toast.success('Audio deleted')
    } catch {
      toast.error('Failed to delete audio')
    }
  }

  const uniqueVoices = [...new Set(audioList.map((a) => a.voice))]
  const totalPages = Math.ceil(total / perPage)

  return (
    <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border/50">
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-2">
            <Library size={13} className="text-accent" />
            <span className="text-xs font-semibold text-text-primary">Library</span>
            <span className="text-[10px] text-text-muted">({total})</span>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="relative flex-1">
            <Search size={10} className="absolute left-2 top-1/2 -translate-y-1/2 text-text-muted" />
            <input
              type="text" placeholder="Search..." value={search}
              onChange={(e) => { setSearch(e.target.value); setPage(1) }}
              className="w-full pl-6 pr-2 py-1 text-[10px] bg-surface border border-border/30 rounded focus:outline-none focus:ring-1 focus:ring-accent/50 text-text-primary"
            />
          </div>
          <select value={filterVoice || ''} onChange={(e) => { setFilterVoice(e.target.value || null); setPage(1) }}
            className="px-1.5 py-1 text-[10px] bg-surface border border-border/30 rounded text-text-primary focus:outline-none">
            <option value="">Voice</option>
            {uniqueVoices.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </div>
      </div>

      <div className="p-1 space-y-0.5 max-h-[180px] overflow-y-auto custom-scrollbar">
          {loading ? (
            <SkeletonPanel rows={3} />
          ) : audioList.length === 0 ? (
            <EmptyState
              icon={<Volume2 size={20} />}
              title="No audio yet"
              description="Generate speech to see files here"
            />
        ) : audioList.map((item, i) => (
          <div key={item.id} className="list-item-enter group flex items-center gap-2 px-2 py-1 rounded-lg hover:bg-surface-hover transition-all" style={{ animationDelay: `${i * 30}ms` }}>
            <button onClick={() => playAudio(item)} className="w-6 h-6 rounded bg-accent/10 hover:bg-accent/20 flex items-center justify-center text-accent transition-all flex-shrink-0">
              <Play size={9} className="ml-px" />
            </button>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-1.5">
                <p className="text-[10px] font-medium text-text-primary truncate">{item.voice}</p>
                <span className={`text-[7px] bg-gradient-to-r ${PRESET_COLORS[item.preset] || 'from-gray-500 to-gray-600'} text-white px-1 py-px rounded font-medium`}>{item.preset}</span>
              </div>
              <p className="text-[9px] text-text-muted truncate">{item.text.slice(0, 40)}...</p>
            </div>
            <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
              <a href={`${API_BASE}/library/${item.id}/file`} download={item.filename} className="p-0.5 rounded text-text-muted hover:text-accent transition-all"><Download size={9} /></a>
              <button onClick={() => deleteAudio(item.id)} className="p-0.5 rounded text-text-muted hover:text-red-400 transition-all"><Trash2 size={9} /></button>
            </div>
          </div>
        ))}
      </div>

      {totalPages > 1 && (
        <div className="px-3 py-1.5 border-t border-border/50 flex items-center justify-between">
          <span className="text-[9px] text-text-muted">{page}/{totalPages}</span>
          <div className="flex items-center gap-0.5">
            <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1} className="p-0.5 rounded text-text-muted hover:text-text-primary disabled:opacity-30"><ChevronLeft size={10} /></button>
            <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages} className="p-0.5 rounded text-text-muted hover:text-text-primary disabled:opacity-30"><ChevronRight size={10} /></button>
          </div>
        </div>
      )}
    </div>
  )
}
