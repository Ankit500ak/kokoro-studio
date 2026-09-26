import { useCallback, useRef } from 'react'
import { useAppStore } from './useStore'
import { CONTENT_PRESETS } from '../types'
import { fetchWithTimeout } from '../lib/fetch'
import { emitToast } from '../components/Toast'

import { API_BASE } from '../lib/api'

export function useTTS() {
  const currentAudioRef = useRef<HTMLAudioElement | null>(null)

  const generate = useCallback(async (projectId?: string | null) => {
    const { text, voice, tuningId, speed, tone, preset, setGenerating, setGeneratedAudio, addToHistory, setError } = useAppStore.getState()

    if (!text.trim()) {
      setError('Please enter some text')
      return
    }

    setGenerating(true)
    setError(null)

    const presetConfig = CONTENT_PRESETS.find(p => p.id === preset)
    const mode = presetConfig?.mode || 'storytelling'

    try {
      console.log('[TTS] Starting generation...', { text: text.substring(0, 50), voice, speed, mode, preset, tuningId })
      const wordCount = text.split(/\s+/).length
      // Scale timeout: 10min base + 0.4s per word (very generous for long scripts)
      const ttsTimeout = Math.max(1200000, 1200000 + wordCount * 400)
      console.log(`[TTS] Timeout: ${ttsTimeout/1000}s for ${wordCount} words`)
      const response = await fetchWithTimeout(`${API_BASE}/tts/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeout: ttsTimeout,
        body: JSON.stringify({
          text,
          voice,
          tuning_id: tuningId,
          speed,
          tone,
          mode,
          preset,
          project_id: projectId || null,
          use_multi_pass: false,
          use_enhancement: true,
          enhancement_level: 'balanced',
        })
      })

      console.log('[TTS] Response received:', response.status)
      if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        throw new Error(err.detail || 'Generation failed')
      }

      const data = await response.json()
      console.log('[TTS] Data parsed:', data.id, data.duration)
      const audioData = { ...data, text, created_at: new Date().toISOString() }

      setGeneratedAudio(audioData)
      addToHistory(audioData)
      emitToast('success', 'Speech generated', `${data.duration?.toFixed(1)}s audio ready`)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Generation failed'
      console.error('[TTS] Error:', message, err)
      setError(message)
      emitToast('error', 'Generation failed', message)
    } finally {
      setGenerating(false)
    }
  }, [])

  const previewVoice = useCallback(async (voiceId: string, tuningId?: number | null) => {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause()
      currentAudioRef.current.src = ''
      currentAudioRef.current = null
    }

    const { preset, setError } = useAppStore.getState()
    const presetConfig = CONTENT_PRESETS.find(p => p.id === preset)
    const mode = presetConfig?.mode || 'storytelling'

    try {
      const response = await fetchWithTimeout(`${API_BASE}/tts/preview`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeout: 60000,
        body: JSON.stringify({
          text: 'This is a voice preview for the Kokoro Studio. Listen to how natural and human this voice sounds.',
          voice: voiceId,
          mode,
          tuning_id: tuningId || null,
        })
      })

      if (!response.ok) throw new Error('Preview failed')

      const data = await response.json()
      const audio = new Audio(`${API_BASE}/audio/${data.filename}`)
      currentAudioRef.current = audio

      audio.play().catch(() => {})
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Preview failed'
      setError(message)
    }
  }, [])

  const fetchAllVoices = useCallback(async () => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/voices`, { timeout: 8000 })
      if (!response.ok) throw new Error('Failed to fetch voices')
      const data = await response.json()
      useAppStore.getState().setVoices(data)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to fetch voices'
      useAppStore.getState().setError(message)
    }
  }, [])

  const fetchTuningVariations = useCallback(async (voiceId: string) => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/tuning/${voiceId}`, { timeout: 8000 })
      if (!response.ok) return []
      const data = await response.json()
      return data.variations || []
    } catch {
      return []
    }
  }, [])

  return { generate, previewVoice, fetchAllVoices, fetchTuningVariations }
}
