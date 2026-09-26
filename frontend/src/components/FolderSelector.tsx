import { useState, useEffect, useCallback } from 'react'
import { Film, Folder } from 'lucide-react'
import { fetchWithTimeout } from '../lib/fetch'
import { API_BASE } from '../lib/api'

interface VideoFolder {
  name: string
  count: number
  thumbnail_asset_id?: string
}

interface FolderSelectorProps {
  onSelectFolders: (folders: string[]) => void
  selectedFolders: string[]
}

function FolderCard({ folder, isSelected, onClick }: { folder: VideoFolder; isSelected: boolean; onClick: () => void }) {
  const [thumbUrl, setThumbUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!folder.thumbnail_asset_id) return
    const img = new Image()
    img.src = `${API_BASE}/media/${folder.thumbnail_asset_id}/thumbnail`
    img.onload = () => setThumbUrl(img.src)
    img.onerror = () => setThumbUrl(null)
    return () => { img.src = '' }
  }, [folder.thumbnail_asset_id])

  const getFolderLabel = (name: string) => {
    const labels: Record<string, string> = {
      'odlysatisfy': 'Oddly Satisfying',
      'sandsatisfy': 'Sand Satisfying',
      'sandsound': 'Sand Sound',
      'SandTagious': 'Sand Tagious',
      'stablesatisfaction': 'Stable Satisfaction',
    }
    return labels[name] || name.replace(/([A-Z])/g, ' $1').replace(/_/g, ' ').trim()
  }

  return (
    <button
      onClick={onClick}
      className={`group relative flex flex-col items-center gap-1.5 p-1.5 rounded-xl transition-all ${
        isSelected
          ? 'ring-2 ring-accent bg-accent/10'
          : 'hover:bg-surface-hover hover:ring-1 hover:ring-border'
      }`}
    >
      <div className="w-full aspect-video rounded-lg overflow-hidden bg-surface relative">
        {thumbUrl ? (
          <img src={thumbUrl} alt={folder.name} className="w-full h-full object-cover" />
        ) : (
          <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-amber-400 to-amber-500">
            <Folder size={20} className="text-white/80" />
          </div>
        )}
        {isSelected && (
          <div className="absolute inset-0 bg-accent/20 flex items-center justify-center">
            <div className="w-5 h-5 rounded-full bg-accent flex items-center justify-center">
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                <path d="M2 5L4.5 7.5L8 3" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
            </div>
          </div>
        )}
      </div>
      <div className="w-full text-center">
        <p className="text-[10px] font-medium text-text-primary truncate leading-tight">
          {getFolderLabel(folder.name)}
        </p>
        <p className="text-[9px] text-text-muted">{folder.count} clips</p>
      </div>
    </button>
  )
}

export function FolderSelector({ onSelectFolders, selectedFolders }: FolderSelectorProps) {
  const [folders, setFolders] = useState<VideoFolder[]>([])
  const [loading, setLoading] = useState(true)

  const fetchFolders = useCallback(async () => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/media/folders`, { timeout: 8000 })
      if (response.ok) {
        const data = await response.json()
        setFolders(data)
      }
    } catch (err) {
      console.error('Failed to fetch folders:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchFolders() }, [fetchFolders])

  const totalClips = folders
    .filter(f => selectedFolders.includes(f.name))
    .reduce((sum, f) => sum + f.count, 0)

  const toggleFolder = (name: string) => {
    if (selectedFolders.includes(name)) {
      onSelectFolders(selectedFolders.filter(f => f !== name))
    } else {
      onSelectFolders([...selectedFolders, name])
    }
  }

  const hasSelection = selectedFolders.length > 0

  return (
    <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border/50 flex items-center gap-2">
        <Film size={13} className="text-accent" />
        <span className="text-xs font-semibold text-text-primary">Background</span>
        {hasSelection && (
          <button
            onClick={() => onSelectFolders([])}
            className="ml-auto text-[9px] text-accent hover:text-accent-hover transition-colors"
          >
            Clear
          </button>
        )}
      </div>
      <div className="p-2">
        {loading ? (
          <div className="flex items-center justify-center py-4 text-text-muted text-[10px]">
            Loading folders...
          </div>
        ) : folders.length === 0 ? (
          <div className="flex items-center justify-center py-4 text-text-muted text-[10px]">
            No folders found
          </div>
        ) : (
          <>
            <div className="grid grid-cols-3 gap-1.5">
              {folders.map((f) => (
                <FolderCard
                  key={f.name}
                  folder={f}
                  isSelected={selectedFolders.includes(f.name)}
                  onClick={() => toggleFolder(f.name)}
                />
              ))}
            </div>
            {hasSelection && (
              <div className="mt-2 px-1 text-[9px] text-text-muted">
                {selectedFolders.length} folder{selectedFolders.length > 1 ? 's' : ''} selected · {totalClips} total clips
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
