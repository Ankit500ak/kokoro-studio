import { create } from 'zustand'
import type { Voice, GeneratedAudio, ContentPresetId } from '../types'

interface BackgroundPipeline {
  sessionId: string
  theme: string
  currentStage: number
  totalStages: number
  stageLabel: string
  isRunning: boolean
  autoPaste: boolean
  autoGenerate: boolean
}

interface AppStore {
  text: string
  voice: string
  tuningId: number | null
  speed: number
  tone: string
  preset: ContentPresetId
  isGenerating: boolean
  generatedAudio: GeneratedAudio | null
  history: GeneratedAudio[]
  voices: Voice[]
  error: string | null
  backgroundPipeline: BackgroundPipeline | null

  setText: (text: string) => void
  setVoice: (voice: string) => void
  setTuningId: (id: number | null) => void
  setSpeed: (speed: number) => void
  setTone: (tone: string) => void
  setPreset: (preset: ContentPresetId) => void
  setGenerating: (generating: boolean) => void
  setGeneratedAudio: (audio: GeneratedAudio | null) => void
  addToHistory: (audio: GeneratedAudio) => void
  setVoices: (voices: Voice[]) => void
  setError: (error: string | null) => void
  setBackgroundPipeline: (pipeline: BackgroundPipeline | null) => void
}

const loadHistory = (): GeneratedAudio[] => {
  try {
    const stored = localStorage.getItem('kokoro-history')
    return stored ? JSON.parse(stored) : []
  } catch {
    return []
  }
}

const saveHistory = (history: GeneratedAudio[]) => {
  try {
    localStorage.setItem('kokoro-history', JSON.stringify(history.slice(0, 50)))
  } catch {
    // localStorage full or unavailable
  }
}

export const useAppStore = create<AppStore>((set) => ({
  text: '',
  voice: 'am_adam',
  tuningId: null,
  speed: 1.0,
  tone: 'natural',
  preset: 'storytelling',
  isGenerating: false,
  generatedAudio: null,
  history: loadHistory(),
  voices: [],
  error: null,
  backgroundPipeline: null,

  setText: (text) => set({ text }),
  setVoice: (voice) => set({ voice, tuningId: null }),
  setTuningId: (tuningId) => set({ tuningId }),
  setSpeed: (speed) => set({ speed }),
  setTone: (tone) => set({ tone }),
  setPreset: (preset) => set({ preset }),
  setGenerating: (generating) => set({ isGenerating: generating }),
  setGeneratedAudio: (audio) => set({ generatedAudio: audio }),
  addToHistory: (audio) => set((state) => {
    const history = [audio, ...state.history].slice(0, 50)
    saveHistory(history)
    return { history }
  }),
  setVoices: (voices) => set({ voices }),
  setError: (error) => set({ error }),
  setBackgroundPipeline: (pipeline) => set({ backgroundPipeline: pipeline }),
}))
