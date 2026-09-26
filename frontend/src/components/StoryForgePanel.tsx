import { useState, useCallback, useRef, useEffect } from 'react'
import { useAppStore } from '../hooks/useStore'
import {
  startPipeline, selectHook,
  generateDraft, retentionPass, qualityScore,
  runFullAuto, getSession, checkThemeDuplicate,
  type PipelineResult, type ColdOpenHook,
} from '../lib/forgeApi'
import { useToast } from './Toast'
import {
  Wand2, Target, Layers, PenTool,
  TrendingUp, BarChart3, Loader2, Check,
  ChevronRight, Sparkles, Zap, Copy, Play,
  ToggleLeft, ToggleRight, Minimize2, Maximize2,
  AlertTriangle, Clock,
} from 'lucide-react'

const STAGES = [
  { id: 1, name: 'Classify', icon: Wand2, color: 'text-amber-400' },
  { id: 2, name: 'Hooks', icon: Target, color: 'text-red-400' },
  { id: 3, name: 'Arch', icon: Layers, color: 'text-blue-400' },
  { id: 4, name: 'Draft', icon: PenTool, color: 'text-purple-400' },
  { id: 5, name: 'Retain', icon: TrendingUp, color: 'text-green-400' },
  { id: 6, name: 'Score', icon: BarChart3, color: 'text-pink-400' },
]

const DURATION_OPTIONS = [
  { value: 15, label: '15s', description: 'Quick hook' },
  { value: 30, label: '30s', description: 'Short story' },
  { value: 45, label: '45s', description: 'Standard Shorts' },
  { value: 60, label: '60s', description: 'Full Short' },
  { value: 90, label: '90s', description: 'Extended Short' },
  { value: 120, label: '2min', description: 'Default (Recommended)' },
  { value: 180, label: '3min', description: 'Deep dive' },
  { value: 240, label: '4min', description: 'Full narrative' },
  { value: 300, label: '5min', description: 'Epic story' },
  { value: 600, label: '10min', description: 'Long-form video' },
  { value: 900, label: '15min', description: 'Extended long-form' },
  { value: 1200, label: '20min', description: 'Deep long-form' },
  { value: 1800, label: '30min', description: 'Full long-form' },
  { value: 2700, label: '45min', description: 'Extended video' },
  { value: 3600, label: '60min', description: 'Full hour video' },
]

function formatScript(text: string): string {
  if (!text) return ''
  return text
    .replace(/\n{3,}/g, '\n\n')
    .trim()
}

export function StoryForgePanel() {
  const setText = useAppStore((s) => s.setText)
  const backgroundPipeline = useAppStore((s) => s.backgroundPipeline)
  const setBackgroundPipeline = useAppStore((s) => s.setBackgroundPipeline)
  const toast = useToast()

  const [theme, setTheme] = useState('')
  const [pipeline, setPipeline] = useState<PipelineResult | null>(null)
  const [activeStage, setActiveStage] = useState(0)
  const [loading, setLoading] = useState(false)
  const [loadingStage, setLoadingStage] = useState(0)
  const [loadingLabel, setLoadingLabel] = useState('')
  const [autoPaste, setAutoPaste] = useState(true)
  const [autoGenerate, setAutoGenerate] = useState(false)
  const [isMinimized, setIsMinimized] = useState(false)
  const [themeDuplicate, setThemeDuplicate] = useState<{ is_used: boolean; message: string } | null>(null)
  const [targetDuration, setTargetDuration] = useState(120)

  const runningRef = useRef(false)
  const timersRef = useRef<number[]>([])
  const sessionIdRef = useRef('')
  const themeCheckRef = useRef<number>(0)

  useEffect(() => {
    return () => timersRef.current.forEach(clearTimeout)
  }, [])

  useEffect(() => {
    if (!theme.trim()) {
      setThemeDuplicate(null)
      return
    }
    const checkId = ++themeCheckRef.current
    const timer = setTimeout(async () => {
      try {
        const result = await checkThemeDuplicate(theme.trim())
        if (checkId === themeCheckRef.current) {
          setThemeDuplicate(result)
        }
      } catch {
        if (checkId === themeCheckRef.current) {
          setThemeDuplicate(null)
        }
      }
    }, 500)
    return () => clearTimeout(timer)
  }, [theme])

  const scheduleRemove = useCallback((id: string, delay: number) => {
    const timer = window.setTimeout(() => toast.removeToast(id), delay)
    timersRef.current.push(timer)
  }, [toast])

  const updatePipeline = useCallback(async (sessionId: string) => {
    const updated = await getSession(sessionId)
    setPipeline(updated)
    return updated
  }, [])

  const handleStart = useCallback(async () => {
    if (!theme.trim() || runningRef.current) return
    runningRef.current = true
    setLoading(true)
    setLoadingStage(1)
    setLoadingLabel('Classifying story & generating hooks...')
    const toastId = toast.loading('Generating hooks...')
    try {
      const result = await startPipeline(theme.trim(), targetDuration)
      const updated = await updatePipeline(result.session_id)
      setActiveStage(2)
      toast.updateToast(toastId, { type: 'success', message: `${updated.cold_hooks?.length || 0} hooks generated` })
      scheduleRemove(toastId, 2000)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to generate hooks'
      toast.updateToast(toastId, { type: 'error', message: msg })
    } finally {
      setLoading(false)
      setLoadingStage(0)
      setLoadingLabel('')
      runningRef.current = false
    }
  }, [theme, toast, updatePipeline, scheduleRemove, targetDuration])

  const handleSelectHook = useCallback(async (hook: ColdOpenHook) => {
    if (!pipeline || runningRef.current) return
    runningRef.current = true
    setLoading(true)
    setLoadingStage(3)
    setLoadingLabel('Building story architecture...')
    const toastId = toast.loading('Building architecture & generating draft...')
    try {
      await selectHook(pipeline.session_id, hook.id)
      const updated = await updatePipeline(pipeline.session_id)
      setActiveStage(4)
      toast.updateToast(toastId, { type: 'success', message: 'Architecture built' })
      scheduleRemove(toastId, 2000)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Failed to build architecture'
      toast.updateToast(toastId, { type: 'error', message: msg })
    } finally {
      setLoading(false)
      setLoadingStage(0)
      setLoadingLabel('')
      runningRef.current = false
    }
  }, [pipeline, toast, updatePipeline, scheduleRemove])

  const handleRunRemaining = useCallback(async (fromStage: number) => {
    if (!pipeline || runningRef.current) return
    runningRef.current = true
    setLoading(true)

    const stages = [
      { id: 4, name: 'Draft', fn: () => generateDraft(pipeline.session_id) },
      { id: 5, name: 'Retention', fn: () => retentionPass(pipeline.session_id) },
      { id: 6, name: 'Quality', fn: () => qualityScore(pipeline.session_id) },
    ]

    for (const stage of stages) {
      if (stage.id < fromStage) continue
      setLoadingStage(stage.id)
      setLoadingLabel(`Stage ${stage.id}: ${stage.name}...`)
      const toastId = toast.loading(`Stage ${stage.id}: ${stage.name}...`)
      try {
        await stage.fn()
        const updated = await updatePipeline(pipeline.session_id)
        setActiveStage(stage.id)
        toast.updateToast(toastId, { type: 'success', message: `${stage.name} complete` })
        scheduleRemove(toastId, 1500)

        if (stage.id === 6 && autoPaste) {
          const finalScript = updated.final_script || updated.retention_optimized || updated.draft
          if (finalScript) {
            setText(finalScript)
            toast.success('Script auto-pasted into editor')
            if (autoGenerate) {
              setTimeout(() => {
                document.querySelector<HTMLButtonElement>('[data-generate-btn]')?.click()
                toast.info('Auto-generating speech...')
              }, 500)
            }
          }
        }
      } catch (err) {
        const msg = err instanceof Error ? err.message : `${stage.name} failed`
        toast.updateToast(toastId, { type: 'error', message: msg })
        break
      }
    }

    setLoading(false)
    setLoadingStage(0)
    setLoadingLabel('')
    runningRef.current = false
  }, [pipeline, toast, updatePipeline, scheduleRemove, autoPaste, autoGenerate, setText])

  const handleFullAuto = useCallback(async () => {
    if (!theme.trim() || runningRef.current) return
    runningRef.current = true
    sessionIdRef.current = ''
    setLoading(true)
    setLoadingStage(1)
    setLoadingLabel('Starting pipeline...')
    const toastId = toast.loading('Starting pipeline...')

    setBackgroundPipeline({
      sessionId: '',
      theme: theme.trim(),
      currentStage: 1,
      totalStages: 6,
      stageLabel: 'Starting pipeline...',
      isRunning: true,
      autoPaste,
      autoGenerate,
    })

    try {
      const result = await runFullAuto(theme.trim(), (stage, label) => {
        setLoadingStage(stage || 0)
        setLoadingLabel(label)
        setBackgroundPipeline({
          sessionId: sessionIdRef.current,
          theme: theme.trim(),
          currentStage: stage || 0,
          totalStages: 6,
          stageLabel: label,
          isRunning: true,
          autoPaste,
          autoGenerate,
        })
      }, targetDuration)
      sessionIdRef.current = result.session_id
      setPipeline(result)
      setActiveStage(6)
      setLoadingStage(0)
      setLoadingLabel('Complete!')
      toast.updateToast(toastId, { type: 'success', message: `Score: ${result.quality_score}/100` })
      scheduleRemove(toastId, 3000)

      const finalScript = result.final_script || result.retention_optimized || result.draft
      if (autoPaste && finalScript) {
        setText(finalScript)
        toast.success('Script auto-pasted into editor')
        if (autoGenerate) {
          setTimeout(() => {
            document.querySelector<HTMLButtonElement>('[data-generate-btn]')?.click()
            toast.info('Auto-generating speech...')
          }, 500)
        }
      }

      setBackgroundPipeline(null)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Pipeline failed'
      toast.updateToast(toastId, { type: 'error', message: msg })
      setBackgroundPipeline(null)
    } finally {
      setLoading(false)
      setLoadingStage(0)
      setLoadingLabel('')
      runningRef.current = false
    }
  }, [theme, toast, scheduleRemove, autoPaste, autoGenerate, setText, setBackgroundPipeline, targetDuration])

  const handleUseScript = useCallback(() => {
    if (!pipeline?.final_script) return
    setText(pipeline.final_script)
    toast.success('Script loaded into editor')
    if (autoGenerate) {
      setTimeout(() => {
        document.querySelector<HTMLButtonElement>('[data-generate-btn]')?.click()
        toast.info('Auto-generating speech...')
      }, 500)
    }
  }, [pipeline, setText, toast, autoGenerate])

  const completedCount = pipeline?.completed_stages?.length || 0
  const hooks = pipeline?.cold_hooks || []
  const arch = pipeline?.architecture || []

  return (
    <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      {/* Header */}
      <div className="px-3 py-2 border-b border-border/50 flex items-center gap-2">
        <div className="w-5 h-5 bg-gradient-to-br from-amber-500 to-orange-600 rounded-md flex items-center justify-center">
          <Wand2 size={10} className="text-white" />
        </div>
        <span className="text-xs font-semibold text-text-primary">Story Forge</span>
        {pipeline && (
          <span className="text-[9px] text-text-muted ml-auto">{completedCount}/6 stages</span>
        )}
        <button
          onClick={() => setIsMinimized(!isMinimized)}
          className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-surface-hover transition-all"
        >
          {isMinimized ? <Maximize2 size={10} /> : <Minimize2 size={10} />}
        </button>
      </div>

      {/* Background pipeline status */}
      {backgroundPipeline?.isRunning && (
        <div className="px-3 py-2 bg-amber-500/10 border-b border-amber-500/20">
          <div className="flex items-center gap-2">
            <div className="relative">
              <div className="w-2 h-2 bg-amber-400 rounded-full animate-pulse" />
              <div className="absolute inset-0 w-2 h-2 bg-amber-400 rounded-full animate-ping opacity-75" />
            </div>
            <span className="text-[10px] text-amber-400 font-medium">Background Process</span>
            <span className="text-[9px] text-text-muted ml-auto">
              Stage {backgroundPipeline.currentStage}/{backgroundPipeline.totalStages}
            </span>
          </div>
          <div className="mt-1.5 flex gap-0.5">
            {Array.from({ length: backgroundPipeline.totalStages }, (_, i) => (
              <div
                key={i}
                className={`flex-1 h-1 rounded-full transition-all duration-500 ${
                  i + 1 < backgroundPipeline.currentStage ? 'bg-green-500' :
                  i + 1 === backgroundPipeline.currentStage ? 'bg-amber-400 animate-pulse' :
                  'bg-border/30'
                }`}
              />
            ))}
          </div>
          <p className="text-[9px] text-text-muted mt-1">{backgroundPipeline.stageLabel}</p>
        </div>
      )}

      <div className={`transition-all duration-300 ${isMinimized ? 'max-h-0 overflow-hidden' : 'max-h-[calc(100vh-200px)] overflow-y-auto custom-scrollbar'}`}>
        <div className="p-3 space-y-3">
          {/* Theme input */}
          <div className="space-y-1.5">
            <input
              type="text"
              value={theme}
              onChange={(e) => setTheme(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && !loading && (pipeline ? handleFullAuto() : handleStart())}
              placeholder="Enter a theme or topic..."
              className={`w-full px-3 py-1.5 bg-surface border rounded-lg text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent/50 transition-all ${
                themeDuplicate?.is_used ? 'border-amber-500/50' : 'border-border'
              }`}
              disabled={loading}
            />
            {themeDuplicate?.is_used && (
              <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-amber-500/10 border border-amber-500/20">
                <AlertTriangle size={10} className="text-amber-400 flex-shrink-0" />
                <span className="text-[9px] text-amber-400">This theme has been used before. Choose a different one.</span>
              </div>
            )}
            
            {/* Duration selector */}
            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1.5">
                <Clock size={10} className="text-text-muted" />
                <span className="text-[9px] text-text-muted">Duration:</span>
              </div>
              <div className="flex gap-1 flex-wrap">
                {DURATION_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => setTargetDuration(opt.value)}
                    disabled={loading}
                    className={`px-2 py-0.5 rounded text-[9px] font-medium transition-all ${
                      targetDuration === opt.value
                        ? 'bg-accent text-white'
                        : 'bg-surface border border-border/30 text-text-muted hover:border-accent/50 hover:text-text-primary'
                    } disabled:opacity-40`}
                    title={opt.description}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="flex gap-1.5">
              <button
                onClick={handleStart}
                disabled={!theme.trim() || loading}
                className="flex-1 py-1.5 bg-accent/10 hover:bg-accent/20 text-accent text-[10px] font-medium rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-1"
              >
                {loading && loadingStage === 1 ? <Loader2 size={10} className="animate-spin" /> : <Sparkles size={10} />}
                Step by Step
              </button>
              <button
                onClick={handleFullAuto}
                disabled={!theme.trim() || loading}
                className="flex-1 py-1.5 bg-gradient-to-r from-amber-500/20 to-orange-500/20 hover:from-amber-500/30 hover:to-orange-500/30 text-amber-400 text-[10px] font-medium rounded-lg transition-all disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-1"
              >
                {loading && loadingStage > 0 ? <Loader2 size={10} className="animate-spin" /> : <Zap size={10} />}
                Full Auto
              </button>
            </div>
          </div>

          {/* Auto-paste / Auto-generate toggles */}
          <div className="flex gap-2">
            <button
              onClick={() => setAutoPaste(!autoPaste)}
              className="flex items-center gap-1.5 px-2 py-1 rounded-lg border border-border/30 hover:border-border transition-all flex-1"
            >
              {autoPaste ? <ToggleRight size={12} className="text-green-400" /> : <ToggleLeft size={12} className="text-text-muted" />}
              <span className="text-[9px] text-text-muted">Auto-paste</span>
            </button>
            <button
              onClick={() => setAutoGenerate(!autoGenerate)}
              className="flex items-center gap-1.5 px-2 py-1 rounded-lg border border-border/30 hover:border-border transition-all flex-1"
            >
              {autoGenerate ? <ToggleRight size={12} className="text-green-400" /> : <ToggleLeft size={12} className="text-text-muted" />}
              <span className="text-[9px] text-text-muted">Auto-generate</span>
            </button>
          </div>

          {/* Loading progress */}
          {loading && loadingStage > 0 && (
            <div className="space-y-1.5">
              <div className="flex gap-0.5">
                {STAGES.map((stage) => {
                  const isCompleted = pipeline?.completed_stages?.includes(stage.id)
                  const isActive = loadingStage === stage.id
                  return (
                    <div
                      key={stage.id}
                      className={`flex-1 h-1.5 rounded-full transition-all duration-500 ${
                        isCompleted ? 'bg-success' : isActive ? 'bg-accent animate-pulse' : 'bg-border/30'
                      }`}
                    />
                  )
                })}
              </div>
              <div className="flex items-center justify-center gap-1.5">
                <Loader2 size={10} className="text-accent animate-spin" />
                <span className="text-[10px] text-text-muted">{loadingLabel}</span>
              </div>
            </div>
          )}

          {/* Pipeline results progress */}
          {pipeline && !loading && (
            <div className="space-y-2">
              <div className="flex gap-0.5">
                {STAGES.map((stage) => {
                  const isCompleted = pipeline.completed_stages?.includes(stage.id)
                  return (
                    <div
                      key={stage.id}
                      className={`flex-1 h-1 rounded-full transition-all duration-300 ${
                        isCompleted ? 'bg-success' : 'bg-border/30'
                      }`}
                    />
                  )
                })}
              </div>
              <div className="flex justify-between">
                {STAGES.map((stage) => {
                  const isCompleted = pipeline.completed_stages?.includes(stage.id)
                  const Icon = stage.icon
                  return (
                    <div key={stage.id} className={`flex flex-col items-center gap-0.5 ${isCompleted ? stage.color : 'text-text-muted/40'}`}>
                      {isCompleted ? <Check size={8} /> : <Icon size={8} />}
                      <span className="text-[7px]">{stage.name.slice(0, 3)}</span>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* Classification */}
          {pipeline?.classification && (
            <div className="flex items-center gap-2 p-2 rounded-lg bg-surface/50 border border-border/30">
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 font-medium">{pipeline.classification.category}</span>
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-500/20 text-blue-400">{pipeline.classification.tone}</span>
              <span className="text-[9px] px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400 flex items-center gap-1">
                <Clock size={8} /> {targetDuration}s
              </span>
              <span className="text-[8px] text-text-muted ml-auto">{pipeline.classification.target_audience}</span>
            </div>
          )}

          {/* Stage 2: Cold Open Hooks */}
          {activeStage >= 2 && hooks.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex items-center gap-1.5">
                <Target size={10} className="text-red-400" />
                <span className="text-[10px] font-semibold text-text-primary">Cold Open Hooks</span>
              </div>
              <div className="space-y-1">
                {hooks.map((hook) => (
                  <button
                    key={hook.id}
                    onClick={() => handleSelectHook(hook)}
                    disabled={loading || activeStage >= 3}
                    className={`w-full text-left p-2 rounded-lg border transition-all ${
                      hook.selected
                        ? 'border-accent/30 bg-accent/5'
                        : 'border-border/30 hover:border-border hover:bg-surface-hover'
                    } disabled:cursor-not-allowed`}
                  >
                    <p className="text-[10px] font-medium text-text-primary mb-0.5">"{hook.text}"</p>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[7px] px-1 py-px rounded bg-red-500/20 text-red-400">{hook.hook_category}</span>
                      <span className="text-[7px] text-text-muted">{hook.psychological_trigger}</span>
                    </div>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Stage 3: Architecture */}
          {activeStage >= 3 && arch.length > 0 && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <Layers size={10} className="text-blue-400" />
                  <span className="text-[10px] font-semibold text-text-primary">Story Architecture</span>
                </div>
                {activeStage === 3 && !loading && (
                  <button
                    onClick={() => handleRunRemaining(4)}
                    className="text-[9px] text-accent hover:text-accent-hover flex items-center gap-0.5"
                  >
                    Continue <ChevronRight size={8} />
                  </button>
                )}
              </div>
              <div className="space-y-0.5">
                {arch.map((beat) => (
                  <div key={beat.beat_number} className="flex items-start gap-2 p-1.5 rounded bg-surface/50">
                    <div className="flex-shrink-0 w-8 text-center">
                      <span className="text-[8px] text-text-muted">{beat.timecode_start}-{beat.timecode_end}</span>
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-1">
                        <span className="text-[9px] font-medium text-text-primary">{beat.purpose}</span>
                        <span className="text-[7px] text-text-muted">|</span>
                        <span className="text-[7px] text-blue-400">{beat.emotion}</span>
                      </div>
                      <p className="text-[8px] text-text-muted mt-0.5 line-clamp-1">{beat.content}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Stages 4-6: Script output */}
          {activeStage >= 4 && pipeline && (pipeline.final_script || pipeline.draft) && (
            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <PenTool size={10} className="text-purple-400" />
                  <span className="text-[10px] font-semibold text-text-primary">
                    {activeStage >= 6 ? 'Final Script' : activeStage >= 5 ? 'Retention Optimized' : 'Draft'}
                  </span>
                </div>
                {activeStage < 6 && !loading && (
                  <button
                    onClick={() => handleRunRemaining(activeStage + 1)}
                    className="text-[9px] text-accent hover:text-accent-hover flex items-center gap-0.5"
                  >
                    Next Stage <ChevronRight size={8} />
                  </button>
                )}
              </div>

              {/* Quality score */}
              {activeStage >= 6 && pipeline.quality_score > 0 && (
                <div className="flex items-center gap-2 p-2 rounded-lg bg-surface/50 border border-border/30">
                  <div className="flex-shrink-0">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold ${
                      pipeline.quality_score >= 80 ? 'bg-green-500/20 text-green-400' :
                      pipeline.quality_score >= 60 ? 'bg-amber-500/20 text-amber-400' :
                      'bg-red-500/20 text-red-400'
                    }`}>
                      {Math.round(pipeline.quality_score)}
                    </div>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(pipeline.quality_breakdown || {}).map(([key, val]) => (
                        <span key={key} className="text-[7px] px-1 py-px rounded bg-surface border border-border/30 text-text-muted">
                          {key.replace(/_/g, ' ')}: {String(val)}
                        </span>
                      ))}
                    </div>
                  </div>
                </div>
              )}

              {/* Script text */}
              <div className="bg-surface rounded-lg border border-border/30 p-2 max-h-[300px] overflow-y-auto custom-scrollbar">
                <div className="flex items-center gap-2 mb-2 text-[9px] text-text-muted">
                  <span>{pipeline.word_count || 0} words</span>
                  <span>~{Math.round(pipeline.estimated_duration || 0)}s estimated</span>
                  <span className="text-accent">Target: {targetDuration}s</span>
                </div>
                <div className="text-[10px] text-text-primary leading-relaxed whitespace-pre-wrap">
                  {formatScript(pipeline.final_script || pipeline.retention_optimized || pipeline.draft)
                    .split('\n\n')
                    .map((para, i) => (
                      <p key={i} className={i > 0 ? 'mt-2' : ''}>{para}</p>
                    ))}
                </div>
              </div>

              {/* Suggestions */}
              {(pipeline.suggestions?.length || 0) > 0 && (
                <div className="space-y-0.5">
                  <span className="text-[9px] font-medium text-text-muted">Suggestions:</span>
                  {pipeline.suggestions!.map((s, i) => (
                    <p key={i} className="text-[8px] text-text-muted pl-2 border-l border-border/30">- {s}</p>
                  ))}
                </div>
              )}

              {/* Action buttons */}
              <div className="flex gap-1.5">
                <button
                  onClick={() => {
                    const script = pipeline.final_script || pipeline.retention_optimized || pipeline.draft
                    navigator.clipboard.writeText(script)
                    toast.success('Script copied')
                  }}
                  className="flex-1 py-1.5 bg-accent/10 hover:bg-accent/20 text-accent text-[10px] font-medium rounded-lg flex items-center justify-center gap-1.5 transition-all"
                >
                  <Copy size={10} /> Copy
                </button>
                <button
                  onClick={handleUseScript}
                  className="flex-1 py-1.5 bg-gradient-to-r from-accent to-accent-hover text-white text-[10px] font-medium rounded-lg flex items-center justify-center gap-1.5 hover:shadow-glow transition-all"
                >
                  <Play size={10} /> Use in Editor
                </button>
                {autoGenerate && (
                  <button
                    onClick={() => {
                      handleUseScript()
                      setTimeout(() => {
                        document.querySelector<HTMLButtonElement>('[data-generate-btn]')?.click()
                      }, 500)
                    }}
                    className="flex-1 py-1.5 bg-gradient-to-r from-green-500/20 to-emerald-500/20 hover:from-green-500/30 hover:to-emerald-500/30 text-green-400 text-[10px] font-medium rounded-lg flex items-center justify-center gap-1.5 transition-all"
                  >
                    <Play size={10} /> Generate Speech
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
