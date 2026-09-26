import { useAppStore } from '../hooks/useStore'
import { useTTS } from '../hooks/useTTS'
import { useMemo, useState, useEffect, useCallback, useRef } from 'react'
import { Play, Filter, Volume2, Sliders } from 'lucide-react'
import type { Voice } from '../types'

interface TuningVariation {
  id: number
  name: string
  speed: number
}

export function VoiceSelector() {
  const voices = useAppStore((s) => s.voices)
  const voice = useAppStore((s) => s.voice)
  const tuningId = useAppStore((s) => s.tuningId)
  const setVoice = useAppStore((s) => s.setVoice)
  const setTuningId = useAppStore((s) => s.setTuningId)
  const { previewVoice, fetchTuningVariations } = useTTS()
  const [filter, setFilter] = useState<'all' | 'male' | 'female' | 'youthful'>('all')
  const [showFilters, setShowFilters] = useState(false)
  const [tuningVariations, setTuningVariations] = useState<TuningVariation[]>([])
  const [showTuning, setShowTuning] = useState(false)

  const filteredVoices = useMemo(() => {
    return voices.filter((v: Voice) => {
      if (filter === 'all') return true
      if (filter === 'youthful') return v.tags?.includes('youthful')
      if (filter === 'male') return v.gender === 'Male'
      if (filter === 'female') return v.gender === 'Female'
      return true
    })
  }, [voices, filter])

  const tuningRequestIdRef = useRef(0)

  const loadTuning = useCallback(async (voiceId: string) => {
    const thisRequestId = ++tuningRequestIdRef.current
    const vars = await fetchTuningVariations(voiceId)
    if (thisRequestId === tuningRequestIdRef.current) {
      setTuningVariations(vars)
      if (vars.length > 0) setShowTuning(true)
    }
  }, [fetchTuningVariations])

  useEffect(() => {
    if (voice) loadTuning(voice)
  }, [voice, loadTuning])

  const getInitials = (name: string) => name.split('_').map(w => w[0]).join('').toUpperCase().slice(0, 2)

  return (
    <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Volume2 size={13} className="text-accent" />
          <span className="text-xs font-semibold text-text-primary">Voices</span>
          <span className="text-[10px] text-text-muted">({filteredVoices.length})</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowTuning(!showTuning)}
            className={`p-1 rounded transition-all ${showTuning ? 'bg-accent/20 text-accent' : 'text-text-muted hover:text-text-primary hover:bg-surface'}`}
            title="Voice Tuning"
          >
            <Sliders size={12} />
          </button>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`p-1 rounded transition-all ${showFilters ? 'bg-accent/20 text-accent' : 'text-text-muted hover:text-text-primary hover:bg-surface'}`}
            aria-label="Toggle filters"
          >
            <Filter size={12} />
          </button>
        </div>
      </div>

      {showFilters && (
        <div className="px-3 py-1.5 border-b border-border/50 bg-surface/30 flex flex-wrap gap-1">
          {(['all', 'male', 'female', 'youthful'] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-2 py-0.5 rounded text-[10px] font-medium transition-all ${
                filter === f ? 'bg-accent text-white' : 'bg-surface-elevated text-text-secondary hover:bg-surface-hover border border-border/30'
              }`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>
      )}

      {showTuning && tuningVariations.length > 0 && (
        <div className="px-3 py-2 border-b border-border/50 bg-surface/30">
          <div className="text-[10px] text-text-muted mb-1.5 font-medium">Voice Tuning</div>
          <div className="flex flex-wrap gap-1">
            <button
              onClick={() => setTuningId(null)}
              className={`px-2 py-0.5 rounded text-[10px] font-medium transition-all ${
                tuningId === null ? 'bg-accent text-white' : 'bg-surface-elevated text-text-secondary hover:bg-surface-hover border border-border/30'
              }`}
            >
              Default
            </button>
            {tuningVariations.map((v) => (
              <button
                key={v.id}
                onClick={() => setTuningId(v.id)}
                className={`px-2 py-0.5 rounded text-[10px] font-medium transition-all ${
                  tuningId === v.id ? 'bg-accent text-white' : 'bg-surface-elevated text-text-secondary hover:bg-surface-hover border border-border/30'
                }`}
                title={v.name}
              >
                {v.id}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="p-1.5 space-y-0.5 max-h-[280px] overflow-y-auto custom-scrollbar">
        {filteredVoices.map((v: Voice) => {
          const isFemale = v.gender === 'Female'
          const isSelected = voice === v.id
          return (
            <div
              key={v.id}
              role="button"
              tabIndex={0}
              aria-label={`Select voice ${v.name}`}
              onClick={() => setVoice(v.id)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setVoice(v.id) } }}
              className={`flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer transition-all ${
                isSelected
                  ? 'bg-accent/10 border border-accent/30'
                  : 'hover:bg-surface-hover border border-transparent'
              }`}
            >
              <div className={`w-7 h-7 rounded-lg flex items-center justify-center text-[9px] font-bold flex-shrink-0 ${
                isSelected ? 'bg-accent text-white'
                  : isFemale ? 'bg-pink-500/15 text-pink-400 border border-pink-500/20'
                  : 'bg-surface-elevated text-text-muted border border-border/30'
              }`}>
                {getInitials(v.name)}
              </div>

              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-[11px] font-medium text-text-primary truncate">{v.name}</span>
                  <span className={`text-[8px] px-1 py-px rounded ${isFemale ? 'bg-pink-500/15 text-pink-400' : 'bg-blue-500/15 text-blue-400'}`}>
                    {isFemale ? 'F' : 'M'}
                  </span>
                  {v.recommended && <span className="text-[8px] px-1 py-px bg-accent/20 text-accent rounded">★</span>}
                </div>
                <p className="text-[9px] text-text-muted truncate">{v.accent} · {v.style}</p>
              </div>

              <button
                onClick={(e) => { e.stopPropagation(); previewVoice(v.id, tuningId) }}
                className="p-1 rounded text-text-muted hover:text-accent hover:bg-accent/10 transition-all flex-shrink-0"
                title="Preview"
              >
                <Play size={11} />
              </button>
            </div>
          )
        })}
      </div>
    </div>
  )
}
