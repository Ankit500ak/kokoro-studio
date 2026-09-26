import { useState, useEffect, useCallback, useRef } from 'react'
import { useAppStore } from '../hooks/useStore'
import { API_BASE } from '../lib/api'
import { fetchWithTimeout } from '../lib/fetch'
import { Heart, Brain, Eye, EyeOff, Loader2, Sparkles } from 'lucide-react'

type EmotionAnalysis = {
  sentences: Array<{
    index: number
    text: string
    emotion: string
    score: number
    prosody: string
    speed: number
    pause_after: string
  }>
  distribution: Record<string, number>
  shaped_preview: string
}

const EMOTION_META: Record<string, { label: string; color: string; bg: string; emoji: string }> = {
  fear:        { label: 'Fear',        color: 'text-slate-300',  bg: 'bg-slate-500/20',   emoji: '😨' },
  suspense:    { label: 'Suspense',    color: 'text-cyan-300',   bg: 'bg-cyan-500/20',    emoji: '🔍' },
  tension:     { label: 'Tension',     color: 'text-indigo-300', bg: 'bg-indigo-500/20',  emoji: '⚡' },
  romance:     { label: 'Romance',     color: 'text-pink-300',   bg: 'bg-pink-500/20',    emoji: '💕' },
  sadness:     { label: 'Sadness',     color: 'text-blue-300',   bg: 'bg-blue-500/20',    emoji: '😢' },
  anger:       { label: 'Anger',       color: 'text-red-300',    bg: 'bg-red-500/20',     emoji: '😠' },
  surprise:    { label: 'Surprise',    color: 'text-yellow-300', bg: 'bg-yellow-500/20',  emoji: '😲' },
  joy:         { label: 'Joy',         color: 'text-orange-300', bg: 'bg-orange-500/20',  emoji: '😄' },
  humor:       { label: 'Humor',       color: 'text-lime-300',   bg: 'bg-lime-500/20',    emoji: '😏' },
  excitement:   { label: 'Excitement',  color: 'text-amber-300',  bg: 'bg-amber-500/20',   emoji: '🎉' },
  wisdom:      { label: 'Wisdom',      color: 'text-emerald-300',bg: 'bg-emerald-500/20', emoji: '💡' },
  neutral:     { label: 'Neutral',     color: 'text-gray-400',   bg: 'bg-gray-500/10',    emoji: '·'  },
}

export function EmotionDisplay() {
  const text = useAppStore((s) => s.text)
  const preset = useAppStore((s) => s.preset)
  const [analysis, setAnalysis] = useState<EmotionAnalysis | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [visible, setVisible] = useState(true)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const requestIdRef = useRef(0)

  const analyze = useCallback(async () => {
    if (!text.trim()) {
      setAnalysis(null)
      return
    }
    setLoading(true)
    setError(null)
    const thisRequestId = ++requestIdRef.current
    try {
      const res = await fetchWithTimeout(`${API_BASE}/tts/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeout: 30000,
        body: JSON.stringify({ text, preset }),
      })
      if (!res.ok) throw new Error('Analysis failed')
      const data: EmotionAnalysis = await res.json()
      if (thisRequestId === requestIdRef.current) setAnalysis(data)
    } catch (e) {
      if (thisRequestId === requestIdRef.current) setError(e instanceof Error ? e.message : 'Analysis failed')
    } finally {
      if (thisRequestId === requestIdRef.current) setLoading(false)
    }
  }, [text, preset])

  // Debounce text changes
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      analyze()
    }, 800)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [text, preset, analyze])

  if (!visible) {
    return (
      <button
        onClick={() => setVisible(true)}
        className="flex items-center gap-1.5 text-[10px] text-text-muted hover:text-text-primary px-2 py-1"
        title="Show emotion analysis"
      >
        <Eye size={11} /> Show emotions
      </button>
    )
  }

  if (!text.trim()) {
    return null
  }

  const topEmotion = analysis
    ? Object.entries(analysis.distribution).sort((a, b) => b[1] - a[1])[0]?.[0]
    : null

  return (
    <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Brain size={13} className="text-accent" />
          <span className="text-xs font-semibold text-text-primary">Emotion Analysis</span>
          {loading && <Loader2 size={10} className="animate-spin text-text-muted" />}
        </div>
        <button
          onClick={() => setVisible(false)}
          className="text-text-muted hover:text-text-primary p-0.5"
          title="Hide"
        >
          <EyeOff size={11} />
        </button>
      </div>

      {error && (
        <div className="px-3 py-2 text-[10px] text-red-400">{error}</div>
      )}

      {analysis && (
        <div className="p-2 space-y-2">
          {/* Distribution pills */}
          <div className="flex flex-wrap gap-1">
            {Object.entries(analysis.distribution)
              .sort((a, b) => b[1] - a[1])
              .map(([emo, count]) => {
                const meta = EMOTION_META[emo] || EMOTION_META.neutral
                return (
                  <span
                    key={emo}
                    className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium ${meta.color} ${meta.bg}`}
                    title={`${meta.label}: ${count} sentence${count !== 1 ? 's' : ''}`}
                  >
                    <span>{meta.emoji}</span>
                    <span>{meta.label}</span>
                    <span className="opacity-60">×{count}</span>
                  </span>
                )
              })}
          </div>

          {/* Per-sentence chips */}
          <div className="space-y-1 max-h-48 overflow-y-auto pr-1">
            {analysis.sentences.map((s) => {
              const meta = EMOTION_META[s.emotion] || EMOTION_META.neutral
              const isHook = s.index === 0 && topEmotion && s.emotion === topEmotion
              return (
                <div
                  key={s.index}
                  className={`flex items-start gap-1.5 px-1.5 py-1 rounded text-[10px] ${meta.bg}`}
                  title={`${meta.label} (score: ${s.score.toFixed(1)}) — ${s.prosody}`}
                >
                  <span className={`flex-shrink-0 ${meta.color}`}>{meta.emoji}</span>
                  <span className="text-text-secondary leading-snug line-clamp-2">
                    {s.text}
                  </span>
                  {isHook && (
                    <Sparkles size={9} className="flex-shrink-0 text-accent" />
                  )}
                </div>
              )
            })}
          </div>

          {topEmotion && (
            <div className="px-2 py-1.5 rounded-lg bg-surface border border-border/30 flex items-center gap-1.5">
              <Heart size={10} className="text-pink-400" />
              <span className="text-[10px] text-text-muted">
                Dominant mood: <span className="text-text-primary font-medium">
                  {EMOTION_META[topEmotion]?.label || topEmotion}
                </span>
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
