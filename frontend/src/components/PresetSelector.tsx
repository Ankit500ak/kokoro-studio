import { useAppStore } from '../hooks/useStore'
import { CONTENT_PRESETS } from '../types'
import type { ContentPreset, ContentPresetId } from '../types'
import { Zap, Film, Eye, Clapperboard, Skull, Heart, GraduationCap, Newspaper } from 'lucide-react'

const ICON_MAP: Record<string, React.ReactNode> = {
  Zap: <Zap size={12} />,
  Film: <Film size={12} />,
  Eye: <Eye size={12} />,
  Clapperboard: <Clapperboard size={12} />,
  Skull: <Skull size={12} />,
  Heart: <Heart size={12} />,
  GraduationCap: <GraduationCap size={12} />,
  Newspaper: <Newspaper size={12} />,
}

export function PresetSelector() {
  const preset = useAppStore((s) => s.preset)
  const setPreset = useAppStore((s) => s.setPreset)
  const setSpeed = useAppStore((s) => s.setSpeed)
  const setTone = useAppStore((s) => s.setTone)

  const handlePresetClick = (p: ContentPreset) => {
    setPreset(p.id); setSpeed(p.defaultSpeed); setTone(p.defaultTone)
  }

  return (
    <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border/50 flex items-center gap-2">
        <Clapperboard size={13} className="text-accent" />
        <span className="text-xs font-semibold text-text-primary">Content Type</span>
      </div>
      <div className="p-2 grid grid-cols-2 gap-1">
        {CONTENT_PRESETS.map((p) => (
          <button
            key={p.id}
            onClick={() => handlePresetClick(p)}
            className={`relative p-2 rounded-lg text-left transition-all overflow-hidden active:scale-[0.97] ${
              preset === p.id
                ? 'text-white shadow-glow ring-1 ring-white/20'
                : 'bg-surface hover:bg-surface-hover border border-border/30 text-text-secondary hover:text-text-primary'
            }`}
          >
            {preset === p.id && <div className={`absolute inset-0 bg-gradient-to-br ${p.gradient} opacity-90`} />}
            <div className="relative flex items-center gap-2">
              <span className={preset === p.id ? 'text-white' : p.color}>{ICON_MAP[p.icon]}</span>
              <span className={`text-[11px] font-medium truncate ${preset === p.id ? 'text-white' : 'text-text-primary'}`}>{p.name}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}
