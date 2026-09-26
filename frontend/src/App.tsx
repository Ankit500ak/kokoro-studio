import { useEffect, useState, useRef } from 'react'
import { useTTS } from './hooks/useTTS'
import { useAppStore } from './hooks/useStore'
import { ToastProvider } from './components/Toast'
import { ScriptEditor } from './components/ScriptEditor'
import { VoiceSelector } from './components/VoiceSelector'
import { PresetSelector } from './components/PresetSelector'
import { SpeedControl } from './components/SpeedControl'
import { EmotionDisplay } from './components/EmotionDisplay'
import { GenerateButton } from './components/GenerateButton'
import { AudioPlayer } from './components/AudioPlayer'
import { History } from './components/History'
import { LibraryView } from './components/LibraryView'
import { ProjectDashboard } from './components/ProjectDashboard'
import { MediaLibrary } from './components/MediaLibrary'
import { MakeShortButton } from './components/MakeShortButton'
import { RenderProgress } from './components/RenderProgress'
import { TemplateSelector } from './components/TemplateSelector'
import { FolderSelector } from './components/FolderSelector'
import { RenderHistory } from './components/RenderHistory'
import { StoryForgePanel } from './components/StoryForgePanel'
import { YouTubeAuthPanel } from './components/YouTubeAuthPanel'
import { YouTubeUploadHistory } from './components/YouTubeUploadHistory'
import { CONTENT_PRESETS } from './types'
import type { Project, VideoAsset, RenderJob } from './types'
import { Mic, Sparkles, Zap, Wand2 } from 'lucide-react'

interface Template {
  id: string
  name: string
  version: number
  config: any
  is_default: boolean
}

function AppContent() {
  const { fetchAllVoices } = useTTS()
  const voices = useAppStore((s) => s.voices)
  const preset = useAppStore((s) => s.preset)
  const generatedAudio = useAppStore((s) => s.generatedAudio)
  const [currentProject, setCurrentProject] = useState<Project | null>(null)
  const [selectedVideoAsset, setSelectedVideoAsset] = useState<VideoAsset | null>(null)
  const [activeRenderJob, setActiveRenderJob] = useState<RenderJob | null>(null)
  const [selectedTemplate, setSelectedTemplate] = useState<Template | null>(null)
  const [selectedVideoFolders, setSelectedVideoFolders] = useState<string[]>([])
  const [showStoryForge, setShowStoryForge] = useState(false)
  const fetchedRef = useRef(false)

  useEffect(() => {
    if (!fetchedRef.current) {
      fetchedRef.current = true
      fetchAllVoices()
    }
  }, [fetchAllVoices])

  const activePreset = CONTENT_PRESETS.find(p => p.id === preset)

  return (
    <div className="h-screen flex flex-col bg-background overflow-hidden">
      {/* Slim Toolbar */}
      <header className="flex-shrink-0 h-11 glass border-b border-border/50 flex items-center px-4 gap-3 z-50">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-gradient-to-br from-accent to-accent-hover rounded-lg flex items-center justify-center">
            <Mic size={14} className="text-white" />
          </div>
          <span className="text-sm font-bold gradient-text hidden sm:inline">Kokoro</span>
        </div>

        <div className="h-4 w-px bg-border/50" />

        {activePreset && (
          <div className={`flex items-center gap-1 text-[10px] font-medium bg-gradient-to-r ${activePreset.gradient} text-white px-2 py-0.5 rounded-full`}>
            <Zap size={9} />
            <span>{activePreset.name}</span>
          </div>
        )}

        <div className="flex-1" />

        <button
          onClick={() => setShowStoryForge(!showStoryForge)}
          className={`flex items-center gap-1.5 px-2 py-1 rounded-lg text-[10px] font-medium transition-all ${
            showStoryForge
              ? 'bg-gradient-to-r from-amber-500 to-orange-600 text-white'
              : 'text-text-muted hover:text-text-primary hover:bg-surface-hover'
          }`}
          title="Story Forge"
        >
          <Wand2 size={12} />
          <span className="hidden sm:inline">Forge</span>
        </button>

        <div className="flex items-center gap-2 text-[11px]">
          <div className="flex items-center gap-1.5 text-text-muted">
            <span className={`w-1.5 h-1.5 rounded-full ${voices.length > 0 ? 'bg-success' : 'bg-warning animate-pulse'}`} />
            <span>{voices.length > 0 ? `${voices.length} voices` : 'Loading'}</span>
          </div>
        </div>
      </header>

      {/* 3-Column Layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left Sidebar: Projects + Presets + Voice + Speed */}
        <aside className="w-72 xl:w-80 flex-shrink-0 border-r border-border/50 overflow-y-auto custom-scrollbar bg-surface/30">
          <div className="p-3 space-y-3">
            {showStoryForge && (
              <div className="panel-enter">
                <StoryForgePanel />
              </div>
            )}
            <ProjectDashboard
              onSelectProject={setCurrentProject}
              currentProject={currentProject}
            />
            <PresetSelector />
            <VoiceSelector />
            <SpeedControl />
            <EmotionDisplay />
          </div>
        </aside>

        {/* Center: Script + Generate + Audio + Make Short + Render */}
        <main className="flex-1 overflow-y-auto custom-scrollbar">
          <div className="max-w-3xl mx-auto p-4 space-y-3">
            <ScriptEditor />
            <div className="flex items-center gap-3">
              <div className="flex-1">
                <GenerateButton projectId={currentProject?.id} />
              </div>
              <div className="flex-1">
                <MakeShortButton
                  project={currentProject}
                  generatedAudio={generatedAudio}
                  onRenderStart={setActiveRenderJob}
                  videoFolders={selectedVideoFolders}
                />
              </div>
            </div>
            <AudioPlayer />
            {activeRenderJob && (
              <RenderProgress
                job={activeRenderJob}
                onRetry={setActiveRenderJob}
              />
            )}
          </div>
        </main>

        {/* Right Sidebar: Template + Media + History */}
        <aside className="w-64 xl:w-72 flex-shrink-0 border-l border-border/50 overflow-y-auto custom-scrollbar bg-surface/30">
          <div className="p-3 space-y-3">
            <TemplateSelector
              onSelectTemplate={setSelectedTemplate}
              selectedTemplateId={selectedTemplate?.id}
            />
            <FolderSelector
              onSelectFolders={setSelectedVideoFolders}
              selectedFolders={selectedVideoFolders}
            />
            <MediaLibrary
              onSelectAsset={setSelectedVideoAsset}
              selectedAssetId={selectedVideoAsset?.id}
            />
            <YouTubeAuthPanel />
            <YouTubeUploadHistory />
            <RenderHistory />
            <LibraryView />
            <History />
          </div>
        </aside>
      </div>
    </div>
  )
}

function App() {
  return (
    <ToastProvider>
      <AppContent />
    </ToastProvider>
  )
}

export default App
