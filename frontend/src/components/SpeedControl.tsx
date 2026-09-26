import { useAppStore } from '../hooks/useStore'
import { Gauge, Music } from 'lucide-react'

export function SpeedControl() {
  const speed = useAppStore((s) => s.speed)
  const setSpeed = useAppStore((s) => s.setSpeed)
  const tone = useAppStore((s) => s.tone)
  const setTone = useAppStore((s) => s.setTone)
  const preset = useAppStore((s) => s.preset)
  const setPreset = useAppStore((s) => s.setPreset)

  const isShorts = preset === 'shorts'

  const speedPresets = [
    { label: 'Slow',   value: 0.90 },
    { label: 'Normal', value: 1.0  },
    { label: 'Fast',   value: 1.15 },
    { label: 'Shorts', value: 1.20, shortsOnly: true },
  ]

  const tonePresets = [
    { label: 'Natural',  value: 'natural',  color: 'bg-blue-400'   },
    { label: 'Warm',     value: 'warm',     color: 'bg-orange-400' },
    { label: 'Deep',     value: 'deep',     color: 'bg-purple-400' },
    { label: 'Smooth',   value: 'smooth',   color: 'bg-teal-400'   },
    { label: 'Bright',   value: 'bright',   color: 'bg-yellow-400' },
    { label: 'Gentle',   value: 'gentle',   color: 'bg-green-400'  },
    { label: 'Crisp',    value: 'crisp',    color: 'bg-sky-400'    },
    { label: 'Resonant', value: 'resonant', color: 'bg-indigo-400' },
    { label: 'Dark',     value: 'dark',     color: 'bg-slate-500'  },
    { label: 'Refined',  value: 'refined',  color: 'bg-amber-400'  },
    { label: 'Hurried',  value: 'hurried',  color: 'bg-red-400'    },
  ]

  return (
    <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      {/* Speed */}
      <div className="px-3 py-2 border-b border-border/50">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Gauge size={13} className="text-accent" />
            <span className="text-xs font-semibold text-text-primary">Speed</span>
          </div>
          <span className="text-[10px] text-text-muted">{speed.toFixed(2)}x</span>
        </div>
        <input
          type="range" min="0.5" max="1.4" step="0.05" value={speed}
          onChange={(e) => setSpeed(parseFloat(e.target.value))}
          className="w-full h-1.5 accent-accent mb-2"
          aria-label="Speech speed"
        />
        <div className="grid grid-cols-4 gap-1">
          {speedPresets.map((p) => {
            const isShortsBtn = p.shortsOnly === true
            if (isShortsBtn && !isShorts) {
              return (
                <button
                  key={p.label}
                  onClick={() => { setPreset('shorts'); setSpeed(p.value) }}
                  className="px-1 py-1.5 rounded-lg text-[10px] font-medium transition-all bg-surface border border-dashed border-accent/40 text-accent hover:bg-accent/10"
                >
                  {p.label}
                  <span className="block text-[9px] opacity-70">{p.value}x</span>
                </button>
              )
            }
            return (
              <button
                key={p.label}
                onClick={() => setSpeed(p.value)}
                className={`px-1 py-1.5 rounded-lg text-[10px] font-medium transition-all ${
                  Math.abs(speed - p.value) < 0.01
                    ? 'bg-accent text-white'
                    : 'bg-surface border border-border/30 text-text-secondary hover:text-text-primary hover:bg-surface-hover'
                }`}
              >
                {p.label}
                <span className={`block text-[9px] ${Math.abs(speed - p.value) < 0.01 ? 'text-white/60' : 'text-text-muted'}`}>{p.value}x</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Tone */}
      <div className="px-3 py-2">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2">
            <Music size={13} className="text-accent" />
            <span className="text-xs font-semibold text-text-primary">Tone</span>
          </div>
          <span className="text-[10px] text-text-muted capitalize">{tone}</span>
        </div>
        <div className="grid grid-cols-3 gap-1">
          {tonePresets.map((p) => (
            <button
              key={p.value}
              onClick={() => setTone(p.value)}
              className={`flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-[10px] font-medium transition-all ${
                tone === p.value
                  ? 'bg-accent text-white'
                  : 'bg-surface border border-border/30 text-text-secondary hover:text-text-primary hover:bg-surface-hover'
              }`}
            >
              <span className={`w-2 h-2 rounded-full flex-shrink-0 ${p.color} ${tone === p.value ? 'ring-1 ring-white/30' : ''}`} />
              <span className="truncate">{p.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
