import { useState, useEffect, useCallback } from 'react'
import { FolderOpen, Plus, Trash2, Edit3, Check, X } from 'lucide-react'
import type { Project } from '../types'
import { fetchWithTimeout } from '../lib/fetch'
import { API_BASE } from '../lib/api'

interface ProjectSelectorProps {
  onSelectProject: (project: Project | null) => void
  currentProject: Project | null
}

export function ProjectSelector({ onSelectProject, currentProject }: ProjectSelectorProps) {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [isCreating, setIsCreating] = useState(false)
  const [newName, setNewName] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editName, setEditName] = useState('')

  const fetchProjects = useCallback(async () => {
    try {
      const response = await fetchWithTimeout(`${API_BASE}/projects/`, { timeout: 8000 })
      if (!response.ok) throw new Error('Failed to fetch')
      const data = await response.json()
      setProjects(Array.isArray(data?.items) ? data.items : [])
    } catch (err) {
      console.error('Failed to fetch projects:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  const createProject = async () => {
    if (!newName.trim()) return
    try {
      const response = await fetchWithTimeout(`${API_BASE}/projects/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newName.trim() })
      })
      if (!response.ok) throw new Error('Failed to create')
      const project = await response.json()
      setProjects([project, ...projects])
      setNewName('')
      setIsCreating(false)
      onSelectProject(project)
    } catch (err) {
      console.error('Failed to create project:', err)
    }
  }

  const updateProject = async (id: string) => {
    if (!editName.trim()) return
    try {
      const response = await fetchWithTimeout(`${API_BASE}/projects/${id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: editName.trim() })
      })
      if (!response.ok) throw new Error('Failed to update')
      const updated = await response.json()
      setProjects(projects.map(p => p.id === id ? updated : p))
      setEditingId(null)
      if (currentProject?.id === id) {
        onSelectProject(updated)
      }
    } catch (err) {
      console.error('Failed to update project:', err)
    }
  }

  const deleteProject = async (id: string) => {
    try {
      await fetchWithTimeout(`${API_BASE}/projects/${id}`, { method: 'DELETE', timeout: 5000 })
      setProjects(projects.filter(p => p.id !== id))
      if (currentProject?.id === id) {
        onSelectProject(null)
      }
    } catch (err) {
      console.error('Failed to delete project:', err)
    }
  }

  return (
    <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FolderOpen size={16} className="text-accent" />
          <span className="text-sm font-semibold text-text-primary">Projects</span>
        </div>
        <button
          onClick={() => setIsCreating(true)}
          className="p-1.5 rounded-lg bg-accent/10 hover:bg-accent/20 text-accent transition-all"
        >
          <Plus size={14} />
        </button>
      </div>

      {isCreating && (
        <div className="px-4 py-3 border-b border-border/50 bg-surface/50">
          <div className="flex items-center gap-2">
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && createProject()}
              placeholder="Project name..."
              className="flex-1 px-3 py-1.5 text-sm bg-surface border border-border/50 rounded-lg focus:outline-none focus:ring-1 focus:ring-accent/50 text-text-primary"
              autoFocus
            />
            <button onClick={createProject} className="p-1.5 text-success hover:bg-success/10 rounded-lg">
              <Check size={14} />
            </button>
            <button onClick={() => { setIsCreating(false); setNewName('') }} className="p-1.5 text-text-muted hover:bg-surface rounded-lg">
              <X size={14} />
            </button>
          </div>
        </div>
      )}

      <div className="p-2 space-y-1 max-h-[200px] overflow-y-auto">
        {loading ? (
          <div className="p-4 text-center text-text-muted text-xs">Loading...</div>
        ) : projects.length === 0 ? (
          <div className="p-4 text-center text-text-muted text-xs">No projects yet</div>
        ) : (
          projects.map((project) => (
            <div
              key={project.id}
              className={`group flex items-center gap-2 p-2 rounded-lg cursor-pointer transition-all ${
                currentProject?.id === project.id
                  ? 'bg-accent/10 border border-accent/30'
                  : 'hover:bg-surface-hover border border-transparent'
              }`}
              onClick={() => onSelectProject(project)}
            >
              {editingId === project.id ? (
                <input
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && updateProject(project.id)}
                  className="flex-1 px-2 py-1 text-sm bg-surface border border-border/50 rounded focus:outline-none focus:ring-1 focus:ring-accent/50 text-text-primary"
                  autoFocus
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <span className="flex-1 text-sm text-text-primary truncate">{project.name}</span>
              )}

              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                {editingId === project.id ? (
                  <>
                    <button
                      onClick={(e) => { e.stopPropagation(); updateProject(project.id) }}
                      className="p-1 text-success hover:bg-success/10 rounded"
                    >
                      <Check size={12} />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); setEditingId(null) }}
                      className="p-1 text-text-muted hover:bg-surface rounded"
                    >
                      <X size={12} />
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      onClick={(e) => { e.stopPropagation(); setEditingId(project.id); setEditName(project.name) }}
                      className="p-1 text-text-muted hover:text-text-primary hover:bg-surface rounded"
                    >
                      <Edit3 size={12} />
                    </button>
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteProject(project.id) }}
                      className="p-1 text-text-muted hover:text-red-400 hover:bg-red-500/10 rounded"
                    >
                      <Trash2 size={12} />
                    </button>
                  </>
                )}
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
