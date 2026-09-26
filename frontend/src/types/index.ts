export type ContentPresetId = 
  | 'shorts' 
  | 'storytelling' 
  | 'mystery' 
  | 'documentary' 
  | 'horror' 
  | 'romantic' 
  | 'educational' 
  | 'news'

export interface ContentPreset {
  id: ContentPresetId
  name: string
  icon: string
  color: string
  gradient: string
  description: string
  defaultSpeed: number
  defaultTone: string
  mode: 'storytelling' | 'shorts'
}

export interface Voice {
  id: string
  name: string
  language: string
  accent: string
  gender: string
  style: string
  tone: string
  weight: string
  description: string
  recommended: boolean
  tags: string[]
  best_for?: ContentPresetId
}

export interface GeneratedAudio {
  id: string
  filename: string
  voice: string
  preset: ContentPresetId
  duration: number | null
  word_count: number
  status: string
  text?: string
  created_at?: string
}

export const CONTENT_PRESETS: ContentPreset[] = [
  {
    id: 'shorts',
    name: 'Shorts',
    icon: 'Zap',
    color: 'text-orange-400',
    gradient: 'from-orange-500 to-red-500',
    description: 'Fast, punchy, hook-driven. Maximum engagement in seconds.',
    defaultSpeed: 1.12,
    defaultTone: 'bright',
    mode: 'shorts',
  },
  {
    id: 'storytelling',
    name: 'Story',
    icon: 'Film',
    color: 'text-purple-400',
    gradient: 'from-purple-500 to-indigo-500',
    description: 'Dramatic pauses, emotional depth, cinematic pacing.',
    defaultSpeed: 0.95,
    defaultTone: 'natural',
    mode: 'storytelling',
  },
  {
    id: 'mystery',
    name: 'Mystery',
    icon: 'Eye',
    color: 'text-cyan-400',
    gradient: 'from-cyan-500 to-blue-600',
    description: 'Slow, suspenseful, eerie. Builds tension with every word.',
    defaultSpeed: 0.88,
    defaultTone: 'deep',
    mode: 'storytelling',
  },
  {
    id: 'documentary',
    name: 'Documentary',
    icon: 'Clapperboard',
    color: 'text-amber-400',
    gradient: 'from-amber-500 to-yellow-600',
    description: 'Measured, authoritative, serious. BBC-style gravitas.',
    defaultSpeed: 0.90,
    defaultTone: 'deep',
    mode: 'storytelling',
  },
  {
    id: 'horror',
    name: 'Horror',
    icon: 'Skull',
    color: 'text-red-500',
    gradient: 'from-red-600 to-black',
    description: 'Dark, tense, terrifying. Chilling delivery that haunts.',
    defaultSpeed: 0.82,
    defaultTone: 'deep',
    mode: 'storytelling',
  },
  {
    id: 'romantic',
    name: 'Romantic',
    icon: 'Heart',
    color: 'text-pink-400',
    gradient: 'from-pink-500 to-rose-500',
    description: 'Warm, gentle, emotional. Soft and intimate narration.',
    defaultSpeed: 0.92,
    defaultTone: 'gentle',
    mode: 'storytelling',
  },
  {
    id: 'educational',
    name: 'Educational',
    icon: 'GraduationCap',
    color: 'text-emerald-400',
    gradient: 'from-emerald-500 to-teal-500',
    description: 'Clear, friendly, paced. Easy to follow and remember.',
    defaultSpeed: 1.0,
    defaultTone: 'warm',
    mode: 'storytelling',
  },
  {
    id: 'news',
    name: 'News',
    icon: 'Newspaper',
    color: 'text-blue-400',
    gradient: 'from-blue-500 to-blue-700',
    description: 'Professional, crisp, authoritative. Breaking news style.',
    defaultSpeed: 1.05,
    defaultTone: 'crisp',
    mode: 'shorts',
  },
]

export type VoiceWeight = 'light' | 'normal' | 'heavy'
export type VoiceTone = 'natural' | 'warm' | 'deep' | 'smooth' | 'bright' | 'gentle' | 'resonant' | 'dark' | 'refined' | 'crisp'

// Project types
export interface Project {
  id: string
  name: string
  title?: string
  script_text?: string
  status: string
  created_at?: string
  updated_at?: string
}

// Video asset types
export interface VideoAsset {
  id: string
  filename: string
  original_name?: string
  storage_key: string
  duration?: number
  width?: number
  height?: number
  fps?: number
  codec?: string
  file_size?: number
  tags?: string
  category?: string
  folder?: string
  usage_count: number
  status: string
  created_at?: string
}

// Render job types
export type RenderStatus = 
  | 'queued' 
  | 'preparing' 
  | 'analyzing_audio' 
  | 'building_captions' 
  | 'selecting_clips' 
  | 'rendering' 
  | 'validating_output' 
  | 'completed' 
  | 'failed'

export interface RenderJob {
  id: string
  project_id: string
  audio_asset_id?: string
  video_folders?: string[]
  status: RenderStatus
  progress: number
  current_stage?: string
  error_code?: string
  error_message?: string
  started_at?: string
  completed_at?: string
  created_at?: string
}

export interface RenderOutput {
  id: string
  render_job_id: string
  video_filename?: string
  thumbnail_filename?: string
  duration?: number
  width?: number
  height?: number
  file_size?: number
  codec?: string
  created_at?: string
}
