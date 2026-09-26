import { useEffect, useRef, useState } from 'react'
import { useAppStore } from '../hooks/useStore'
import { Download, Volume2, CheckCircle, Play, Pause, SkipBack, SkipForward } from 'lucide-react'
import { API_BASE } from '../lib/api'

export function AudioPlayer() {
  const generatedAudio = useAppStore((s) => s.generatedAudio)
  const containerRef = useRef<HTMLDivElement>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)
  const [volume, setVolume] = useState(1)

  useEffect(() => {
    const audio = audioRef.current
    if (!audio) return
    const onTime = () => setCurrentTime(audio.currentTime)
    const onMeta = () => setDuration(isFinite(audio.duration) ? audio.duration : 0)
    const onEnd = () => setIsPlaying(false)
    const onPlay = () => setIsPlaying(true)
    const onPause = () => setIsPlaying(false)
    audio.addEventListener('timeupdate', onTime)
    audio.addEventListener('loadedmetadata', onMeta)
    audio.addEventListener('ended', onEnd)
    audio.addEventListener('play', onPlay)
    audio.addEventListener('pause', onPause)
    return () => {
      audio.removeEventListener('timeupdate', onTime)
      audio.removeEventListener('loadedmetadata', onMeta)
      audio.removeEventListener('ended', onEnd)
      audio.removeEventListener('play', onPlay)
      audio.removeEventListener('pause', onPause)
    }
  }, [generatedAudio])

  if (!generatedAudio) return null

  const audioUrl = `${API_BASE}/audio/${generatedAudio.filename}`
  const togglePlay = () => {
    if (audioRef.current) isPlaying ? audioRef.current.pause() : audioRef.current.play()
  }
  const skip = (s: number) => {
    if (audioRef.current) audioRef.current.currentTime = Math.max(0, Math.min(duration, audioRef.current.currentTime + s))
  }
  const handleSeek = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    if (audioRef.current && rect.width > 0 && isFinite(duration)) {
      const pct = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
      audioRef.current.currentTime = pct * duration
    }
  }
  const handleDownload = () => {
    const a = document.createElement('a'); a.href = audioUrl; a.download = generatedAudio.filename
    document.body.appendChild(a); a.click(); document.body.removeChild(a)
  }
  const fmt = (s: number) => `${Math.floor(s / 60)}:${Math.floor(s % 60).toString().padStart(2, '0')}`
  const progress = duration > 0 ? (currentTime / duration) * 100 : 0

  return (
    <div ref={containerRef} className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      <audio ref={audioRef} src={audioUrl} preload="metadata" />

      <div className="px-3 py-2.5 space-y-2">
        {/* Top row: info + download */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            <CheckCircle size={13} className="text-success flex-shrink-0" />
            <span className="text-xs font-medium text-text-primary truncate">{generatedAudio.voice}</span>
            <span className="text-[10px] text-text-muted">{generatedAudio.word_count}w</span>
            {generatedAudio.duration && <span className="text-[10px] text-text-muted">{Math.round(generatedAudio.duration)}s</span>}
          </div>
          <button onClick={handleDownload} className="p-1.5 rounded-lg text-text-muted hover:text-accent hover:bg-accent/10 transition-all" title="Download">
            <Download size={13} />
          </button>
        </div>

        {/* Waveform seek bar */}
        <div className="h-8 bg-surface rounded-lg cursor-pointer relative overflow-hidden group" onClick={handleSeek}>
          <div className="absolute inset-0 flex items-end justify-center gap-[2px] px-1.5 pb-1">
            {Array.from({ length: 60 }).map((_, i) => {
              const h = 20 + Math.sin(i * 0.5) * 15 + Math.abs(Math.sin(i * 2.1)) * 10
              const played = (i / 60) * 100 < progress
              return <div key={i} className={`w-0.5 rounded-full transition-colors duration-75 ${played ? 'bg-accent' : 'bg-border/60'}`} style={{ height: `${h}%` }} />
            })}
          </div>
          <div className="absolute inset-y-0 left-0 bg-accent/10 transition-all duration-75" style={{ width: `${progress}%` }} />
          <div className="absolute top-0 bottom-0 w-px bg-accent shadow-glow transition-all duration-75" style={{ left: `${progress}%` }} />
        </div>

        {/* Controls row */}
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-text-muted font-mono w-10">{fmt(currentTime)}</span>

          <div className="flex items-center gap-1">
            <button onClick={() => skip(-5)} className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-surface transition-all focus-visible:ring-2 focus-visible:ring-accent/50" aria-label="Skip back"><SkipBack size={13} /></button>
            <button onClick={togglePlay} className="p-2 rounded-lg bg-accent text-white hover:bg-accent-hover transition-all shadow-sm active:scale-95 focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-2" aria-label={isPlaying ? 'Pause' : 'Play'}>
              {isPlaying ? <Pause size={14} /> : <Play size={14} className="ml-px" />}
            </button>
            <button onClick={() => skip(5)} className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-surface transition-all focus-visible:ring-2 focus-visible:ring-accent/50" aria-label="Skip forward"><SkipForward size={13} /></button>
          </div>

          <div className="flex items-center gap-1.5 w-10 justify-end">
            <Volume2 size={10} className="text-text-muted" />
            <input
              type="range" min="0" max="1" step="0.1" value={volume}
              onChange={(e) => { const v = parseFloat(e.target.value); setVolume(v); if (audioRef.current) audioRef.current.volume = v }}
              className="w-10 h-1 accent-accent"
            />
          </div>
        </div>
      </div>
    </div>
  )
}
