import { useState, useEffect, useCallback } from 'react'
import { FolderOpen, Plus, Trash2, Edit3, Check, X, Clock, Film } from 'lucide-react'
import type { Project } from '../types'
import { fetchWithTimeout } from '../lib/fetch'
import { API_BASE } from '../lib/api'
import { useAppStore } from '../hooks/useStore'
import { SkeletonPanel, EmptyState } from './Skeleton'
import { useToast } from './Toast'

interface ProjectDashboardProps {
  onSelectProject: (project: Project | null) => void
  currentProject: Project | null
}

interface ProjectStats {
  renderCount: number
  completedRenders: number
}

export function ProjectDashboard({ onSelectProject, currentProject }: ProjectDashboardProps) {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [isCreating, setIsCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')
  const [projectStats, setProjectStats] = useState<Record<string, ProjectStats>>({})
  const toast = useToast()

  const fetchProjects = useCallback(async () => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/projects/`, { timeout: 8000 })
      if (!response.ok) throw new Error('Failed to fetch')
      const data = await response.json()
      const items = Array.isArray(data?.items) ? data.items : []
      setProjects(items)
      const statsPromises = items.map(async (project: Project) => {
        try {
          const r = await fetchWithTimeout(`${API_BASE}/renders/?project_id=${project.id}`, { timeout: 5000 })
          if (r.ok) {
            const d = await r.json()
            return [project.id, { renderCount: d.total || 0, completedRenders: d.items?.filter((x: any) => x.status === 'completed').length || 0 }] as const
          }
        } catch {}
        return [project.id, { renderCount: 0, completedRenders: 0 }] as const
      })
      const results = await Promise.all(statsPromises)
      const stats: Record<string, ProjectStats> = {}
      for (const [id, s] of results) stats[id] = s
      setProjectStats(stats)
    } catch (err) { console.error('Failed to fetch projects:', err) } finally { setLoading(false) }
  }, [])

  useEffect(() => { fetchProjects() }, [fetchProjects])

  const createProject = async () => {
    if (!newName.trim()) return
    const id = toast.loading('Creating project...')
    try {
      const response = await fetchWithTimeout(`${API_BASE}/projects/`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: newName.trim() }) })
      if (!response.ok) throw new Error('Failed to create')
      const project = await response.json()
      setProjects([project, ...projects]); setNewName(''); setIsCreating(false); onSelectProject(project)
      toast.success('Project created', project.name)
    } catch (err) {
      toast.error('Failed to create project')
      console.error('Failed to create project:', err)
    }
  }

  const updateProject = async (id: string) => {
    if (!editName.trim()) return
    try {
      const response = await fetchWithTimeout(`${API_BASE}/projects/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: editName.trim() }) })
      if (!response.ok) throw new Error('Failed')
      const updated = await response.json()
      setProjects(projects.map(p => p.id === id ? updated : p)); setEditingId(null)
      if (currentProject?.id === id) onSelectProject(updated)
      toast.success('Project renamed')
    } catch (err) {
      toast.error('Failed to rename project')
      console.error('Failed to update project:', err)
    }
  }

  const deleteProject = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Delete this project?')) return
    try {
      await fetchWithTimeout(`${API_BASE}/projects/${id}`, { method: 'DELETE' })
      setProjects(projects.filter(p => p.id !== id))
      if (currentProject?.id === id) {
        onSelectProject(null)
        useAppStore.getState().setGeneratedAudio(null)
      }
      toast.success('Project deleted')
    } catch (err) {
      toast.error('Failed to delete project')
      console.error('Failed to delete project:', err)
    }
  }

  const formatDate = (dateStr?: string) => {
    if (!dateStr) return ''
    const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 86400000)
    if (diff === 0) return 'Today'
    if (diff === 1) return 'Yesterday'
    if (diff < 7) return `${diff}d ago`
    return new Date(dateStr).toLocaleDateString()
  }

  return (
    <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FolderOpen size={13} className="text-accent" />
          <span className="text-xs font-semibold text-text-primary">Projects</span>
          <span className="text-[10px] text-text-muted">({projects.length})</span>
        </div>
        <button onClick={() => setIsCreating(true)} className="flex items-center gap-1 px-2 py-0.5 bg-accent/10 hover:bg-accent/20 text-accent text-[10px] font-medium rounded transition-all">
          <Plus size={10} />New
        </button>
      </div>

      {isCreating && (
        <div className="px-3 py-2 border-b border-border/50 bg-surface/30">
          <div className="flex items-center gap-1.5">
            <input
              type="text" value={newName} onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && createProject()}
              placeholder="Project name..." autoFocus
              className="flex-1 px-2 py-1 text-xs bg-surface border border-border/50 rounded focus:outline-none focus:ring-1 focus:ring-accent/50 text-text-primary"
            />
            <button onClick={createProject} className="p-1 text-success hover:bg-success/10 rounded transition-all"><Check size={12} /></button>
            <button onClick={() => { setIsCreating(false); setNewName('') }} className="p-1 text-text-muted hover:bg-surface rounded transition-all"><X size={12} /></button>
          </div>
        </div>
      )}

      <div className="p-1 space-y-0.5 max-h-[200px] overflow-y-auto custom-scrollbar">
        {loading ? (
          <SkeletonPanel rows={3} />
        ) : projects.length === 0 ? (
          <EmptyState
            icon={<FolderOpen size={20} />}
            title="No projects yet"
            description="Create one to get started"
          />
        ) : (
          projects.map((project, i) => {
            const stats = projectStats[project.id]
            const isActive = currentProject?.id === project.id
            return (
              <div
                key={project.id}
                onClick={() => onSelectProject(project)}
                className={`list-item-enter group flex items-center gap-2 px-2 py-1.5 rounded-lg cursor-pointer transition-all ${
                  isActive ? 'bg-accent/10 border border-accent/30' : 'hover:bg-surface-hover border border-transparent'
                }`}
                style={{ animationDelay: `${i * 30}ms` }}
              >
                <div className="flex-1 min-w-0">
                  {editingId === project.id ? (
                    <input
                      type="text" value={editName} onChange={(e) => setEditName(e.target.value)}
                      onKeyDown={(e) => e.key === 'Enter' && updateProject(project.id)}
                      className="w-full px-1.5 py-0.5 text-[11px] bg-surface border border-border/50 rounded focus:outline-none focus:ring-1 focus:ring-accent/50 text-text-primary"
                      autoFocus onClick={(e) => e.stopPropagation()}
                    />
                  ) : (
                    <p className="text-[11px] font-medium text-text-primary truncate">{project.name}</p>
                  )}
                  <div className="flex items-center gap-2 mt-0.5">
                    <span className="text-[9px] text-text-muted flex items-center gap-0.5"><Clock size={7} />{formatDate(project.created_at)}</span>
                    {stats && stats.renderCount > 0 && (
                      <span className="text-[9px] text-text-muted flex items-center gap-0.5"><Film size={7} />{stats.renderCount}</span>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                  {editingId === project.id ? (
                    <>
                      <button onClick={(e) => { e.stopPropagation(); updateProject(project.id) }} className="p-1 text-success hover:bg-success/10 rounded transition-all"><Check size={10} /></button>
                      <button onClick={(e) => { e.stopPropagation(); setEditingId(null) }} className="p-1 text-text-muted hover:bg-surface rounded transition-all"><X size={10} /></button>
                    </>
                  ) : (
                    <>
                      <button onClick={(e) => { e.stopPropagation(); setEditingId(project.id); setEditName(project.name) }} className="p-1 text-text-muted hover:text-text-primary hover:bg-surface rounded transition-all"><Edit3 size={10} /></button>
                      <button onClick={(e) => deleteProject(project.id, e)} className="p-1 text-text-muted hover:text-red-400 hover:bg-red-500/10 rounded transition-all"><Trash2 size={10} /></button>
                    </>
                  )}
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
