import { API_BASE } from '../lib/api'
import { fetchWithTimeout } from '../lib/fetch'

// Each backend endpoint runs 2 pipeline stages. Backend allows STORY_STAGE_TIMEOUT
//(240s) per stage, so the client must wait longer than that before aborting.
const STAGE_TIMEOUT = 540000

export interface StoryClassification {
  category: string
  sub_category: string
  tone: string
  target_audience: string
}

export interface ColdOpenHook {
  id: string
  text: string
  hook_category: string
  psychological_trigger: string
  pattern_formula: string
  score: number
  selected: boolean
}

export interface RetentionPlanItem {
  hook_type: string
  placement: string
  timecode: string
  purpose: string
}

export interface StoryBeat {
  beat_number: number
  timecode_start: string
  timecode_end: string
  purpose: string
  content: string
  word_count: number
  emotion: string
  micro_hook: string
}

export interface AudienceTarget {
  persona: string
  age_range: string
  gender_skew: string
  interests: string[]
  why_they_watch: string
  best_posting_window: string
}

export interface ThumbnailPlan {
  headline: string
  subline: string
  badge: string
  image_path: string
}

export interface PublishPack {
  titles: string[]
  selected_title: string
  description: string
  tags: string[]
  hashtags: string[]
  audience: AudienceTarget
  thumbnail: ThumbnailPlan
}

export interface PipelineResult {
  session_id: string
  theme: string
  target_duration: number
  classification: StoryClassification | null
  cold_hooks: ColdOpenHook[]
  selected_hook: ColdOpenHook | null
  retention_plan: RetentionPlanItem[]
  architecture: StoryBeat[]
  draft: string
  hook_injected: string
  retention_optimized: string
  retention_notes: string[]
  voice_polished: string
  pause_map: Array<{ after_word: string; pause_type: string }>
  final_tightened: string
  quality_score: number
  quality_breakdown: Record<string, number>
  suggestions: string[]
  final_script: string
  word_count: number
  estimated_duration: number
  publish_pack: PublishPack | null
  current_stage: number
  completed_stages: number[]
  errors: string[]
}

export interface StageResponse {
  session_id: string
  current_stage: number
  completed_stages: number[]
  error?: string
}

export async function startPipeline(theme: string, targetDuration: number = 120): Promise<StageResponse> {
  const res = await fetchWithTimeout(`${API_BASE}/forge/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    timeout: STAGE_TIMEOUT,
    body: JSON.stringify({ theme, target_duration: targetDuration }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to start pipeline')
  }
  return res.json()
}

export async function getSession(sessionId: string): Promise<PipelineResult> {
  const res = await fetchWithTimeout(`${API_BASE}/forge/session/${sessionId}`, { timeout: 10000 })
  if (!res.ok) throw new Error('Session not found')
  return res.json()
}

export async function selectHook(sessionId: string, hookId: string): Promise<StageResponse> {
  const res = await fetchWithTimeout(`${API_BASE}/forge/select-hook`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    timeout: STAGE_TIMEOUT,
    body: JSON.stringify({ session_id: sessionId, hook_id: hookId }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to select hook')
  }
  return res.json()
}

export async function generateDraft(sessionId: string): Promise<StageResponse> {
  const res = await fetchWithTimeout(`${API_BASE}/forge/generate-draft/${sessionId}`, {
    method: 'POST',
    timeout: STAGE_TIMEOUT,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to generate draft')
  }
  return res.json()
}

export async function retentionPass(sessionId: string): Promise<StageResponse> {
  const res = await fetchWithTimeout(`${API_BASE}/forge/retention-pass/${sessionId}`, {
    method: 'POST',
    timeout: STAGE_TIMEOUT,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed retention pass')
  }
  return res.json()
}

export async function qualityScore(sessionId: string): Promise<StageResponse> {
  const res = await fetchWithTimeout(`${API_BASE}/forge/quality-score/${sessionId}`, {
    method: 'POST',
    timeout: STAGE_TIMEOUT,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed quality scoring')
  }
  return res.json()
}

export async function runFullPipeline(theme: string, targetDuration: number = 120): Promise<PipelineResult> {
  // Scale timeout with duration: 10 min base + 20s per target second
  const pipelineTimeout = Math.max(600000, 600000 + targetDuration * 20000)
  const res = await fetchWithTimeout(`${API_BASE}/forge/run-all`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    timeout: pipelineTimeout,
    body: JSON.stringify({ theme, target_duration: targetDuration }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Pipeline failed')
  }
  return res.json()
}

export type StageProgressCallback = (stage: number, label: string) => void

export async function regeneratePublishPack(sessionId: string): Promise<PublishPack> {
  const res = await fetchWithTimeout(`${API_BASE}/forge/publish-pack/${sessionId}`, {
    method: 'POST',
    timeout: STAGE_TIMEOUT,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to build publish pack')
  }
  return res.json()
}

export function publishThumbnailUrl(sessionId: string, version?: number | string): string {
  const bust = version != null ? `?v=${version}` : ''
  return `${API_BASE}/forge/publish-pack/${sessionId}/thumbnail${bust}`
}

export async function checkThemeDuplicate(theme: string): Promise<{ is_used: boolean; message: string }> {
  const res = await fetchWithTimeout(`${API_BASE}/forge/check-theme`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    timeout: 10000,
    body: JSON.stringify({ theme }),
  })
  if (!res.ok) return { is_used: false, message: 'Could not check' }
  return res.json()
}

export async function getUsedThemes(limit: number = 50): Promise<{ total: number; themes: Array<{ theme: string; created_at: string }> }> {
  const res = await fetchWithTimeout(`${API_BASE}/forge/used-themes?limit=${limit}`, { timeout: 10000 })
  if (!res.ok) return { total: 0, themes: [] }
  return res.json()
}

export async function runFullAuto(
  theme: string,
  onProgress: StageProgressCallback,
  targetDuration: number = 120,
): Promise<PipelineResult> {
  const stageLabels = [
    '',
    'Classifying story & generating hooks...',
    'Planning retention hooks...',
    'Building architecture...',
    'Writing draft...',
    'Injecting micro-hooks...',
    'Optimizing retention...',
    'Polishing voice...',
    'Final polish...',
    'Scoring quality...',
    'Building publish pack...',
  ]

  // Stage 1-2: Start pipeline (classification + hooks)
  onProgress(1, stageLabels[1])
  const startResult = await startPipeline(theme, targetDuration)
  let result = await getSession(startResult.session_id)

  // Auto-select first hook
  if (result.cold_hooks && result.cold_hooks.length > 0) {
    const firstHook = result.cold_hooks[0]
    onProgress(2, stageLabels[2])
    await selectHook(result.session_id, firstHook.id)
    result = await getSession(result.session_id)
  }

  // Stage 3-4: Draft + micro-hooks
  onProgress(4, stageLabels[4])
  await generateDraft(result.session_id)
  result = await getSession(result.session_id)

  // Stage 5-6: Retention + voice
  onProgress(7, stageLabels[7])
  await retentionPass(result.session_id)
  result = await getSession(result.session_id)

  // Stage 7: Quality
  onProgress(9, stageLabels[9])
  await qualityScore(result.session_id)
  result = await getSession(result.session_id)

  // Stage 12: publish pack (titles, description, tags, audience, thumbnail)
  try {
    onProgress(10, stageLabels[10])
    await regeneratePublishPack(result.session_id)
    result = await getSession(result.session_id)
  } catch {
    // Publish pack is optional - return the story even if it failed.
  }

  onProgress(0, 'Complete!')
  return result
}
