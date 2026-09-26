import { useState, useRef, useCallback } from 'react'
import { useAppStore } from '../hooks/useStore'
import { FileText, Clock, Type, Upload, Sparkles, Copy, Trash2, Brain } from 'lucide-react'
import { API_BASE } from '../lib/api'
import { fetchWithTimeout } from '../lib/fetch'

const MAX_CHARS = 5000

export function ScriptEditor() {
  const text = useAppStore((s) => s.text)
  const setText = useAppStore((s) => s.setText)
  const isGenerating = useAppStore((s) => s.isGenerating)
  const speed = useAppStore((s) => s.speed)
  const [isDragging, setIsDragging] = useState(false)
  const [showTip, setShowTip] = useState(true)
  const [isThinking, setIsThinking] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const wordCount = text.trim() ? text.trim().split(/\s+/).length : 0
  const charCount = text.length
  const wordsPerMinute = 150 * speed || 150
  const estimatedDuration = Math.round((wordCount / wordsPerMinute) * 60)
  const charPercentage = Math.min((charCount / MAX_CHARS) * 100, 100)

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setIsDragging(true)
  }, [])

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setIsDragging(false)
  }, [])

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); e.stopPropagation(); setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file && (file.type === 'text/plain' || file.name.endsWith('.txt'))) {
      const reader = new FileReader()
      reader.onload = (ev) => {
        const content = ev.target?.result as string
        setText(content.length <= MAX_CHARS ? content : content.slice(0, MAX_CHARS))
      }
      reader.readAsText(file)
    }
  }, [setText])

  const handleClear = () => { setText(''); textareaRef.current?.focus() }

  const handleThink = async () => {
    if (!text.trim() || text.trim().split(/\s+/).length < 10) return
    setIsThinking(true)
    try {
      const response = await fetchWithTimeout(`${API_BASE}/tts/think`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        timeout: 120000,
        body: JSON.stringify({ text }),
      })
      if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        throw new Error(err.detail || 'Refinement failed')
      }
      const data = await response.json()
      setText(data.refined_text || text)
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Refinement failed'
      useAppStore.getState().setError(message)
    } finally {
      setIsThinking(false)
    }
  }

  const handlePaste = async () => {
    try {
      const clipText = await navigator.clipboard.readText()
      if (clipText) {
        const combined = text + clipText
        setText(combined.length <= MAX_CHARS ? combined : combined.slice(0, MAX_CHARS))
      }
    } catch {}
  }

  return (
    <div
      className={`bg-surface-elevated rounded-xl border overflow-hidden transition-all ${
        isDragging ? 'border-accent shadow-glow' : 'border-border'
      }`}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* Header bar */}
      <div className="px-3 py-2 border-b border-border/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText size={13} className="text-accent" />
          <span className="text-xs font-semibold text-text-primary">Script</span>
          {isDragging && <span className="text-[10px] text-accent animate-pulse">Drop .txt</span>}
        </div>
        <div className="flex items-center gap-2 text-[10px] text-text-muted">
          <span className="flex items-center gap-1"><Type size={9} />{wordCount}w</span>
          <span>{charCount}/{MAX_CHARS}</span>
          <span className="flex items-center gap-1"><Clock size={9} />~{estimatedDuration}s</span>
        </div>
      </div>

      {/* Textarea */}
      <div className="relative">
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => {
            if (e.target.value.length <= MAX_CHARS) {
              setText(e.target.value)
              if (showTip && e.target.value.length > 0) setShowTip(false)
            }
          }}
          onKeyDown={(e) => {
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
              e.preventDefault()
              document.querySelector<HTMLButtonElement>('[data-generate-btn]')?.click()
            }
          }}
          placeholder="Enter script or drag & drop .txt file..."
          className="w-full h-48 p-3 bg-transparent text-text-primary placeholder-text-muted/40 resize-none focus:outline-none text-sm leading-relaxed"
          disabled={isGenerating}
          maxLength={MAX_CHARS}
          aria-label="Script input"
        />
        {showTip && !text && (
          <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div className="text-center space-y-2 opacity-20">
              <Upload size={24} className="mx-auto text-text-muted" />
              <p className="text-xs text-text-muted">Drop .txt or start typing</p>
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-3 py-1.5 border-t border-border/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="h-1 w-16 bg-border rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-300 ${
                charPercentage > 90 ? 'bg-red-500' : charPercentage > 70 ? 'bg-warning' : 'bg-accent'
              }`}
              style={{ width: `${charPercentage}%` }}
            />
          </div>
          {text && (
            <div className="flex items-center gap-0.5">
              <button
                onClick={handleThink}
                disabled={isThinking || isGenerating || !text.trim() || text.trim().split(/\s+/).length < 10}
                className="p-1 rounded text-text-muted hover:text-purple-400 hover:bg-purple-500/10 transition-all disabled:opacity-30 disabled:cursor-not-allowed"
                title="Think — refine story with AI"
              >
                <Brain size={10} className={isThinking ? 'animate-pulse text-purple-400' : ''} />
              </button>
              <button onClick={handlePaste} className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-surface transition-all" title="Paste">
                <Copy size={10} />
              </button>
              <button onClick={handleClear} className="p-1 rounded text-text-muted hover:text-red-400 hover:bg-red-500/10 transition-all" title="Clear">
                <Trash2 size={10} />
              </button>
            </div>
          )}
        </div>
        <div className="flex items-center gap-1.5 text-[10px]">
          {isThinking ? (
            <span className="text-purple-400 flex items-center gap-1"><Brain size={9} className="animate-pulse" />Thinking...</span>
          ) : text.trim() ? (
            <span className="text-success flex items-center gap-1"><Sparkles size={9} />~{estimatedDuration}s</span>
          ) : (
            <span className="text-text-muted">Ctrl+Enter</span>
          )}
        </div>
      </div>
    </div>
  )
}
