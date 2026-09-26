import { useState, useEffect, useCallback } from 'react'
import { Layout, Check, ChevronDown } from 'lucide-react'
import { fetchWithTimeout } from '../lib/fetch'
import { API_BASE } from '../lib/api'

interface Template {
  id: string; name: string; version: number; description?: string; config: any; is_default: boolean
}

interface TemplateSelectorProps {
  onSelectTemplate: (template: Template) => void
  selectedTemplateId?: string | null
}

export function TemplateSelector({ onSelectTemplate, selectedTemplateId }: TemplateSelectorProps) {
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [isOpen, setIsOpen] = useState(false)

  const fetchTemplates = useCallback(async () => {
    try {
      const defaultResp = await fetchWithTimeout(`${API_BASE}/templates/defaults`, { timeout: 8000 })
      if (defaultResp.ok) {
        const defaultTemplate = await defaultResp.json()
        const response = await fetchWithTimeout(`${API_BASE}/templates/`, { timeout: 8000 })
        if (response.ok) {
          const data = await response.json()
          const rawItems: any[] = Array.isArray(data?.items) ? data.items : []
          const items = rawItems.filter((t): t is Template => !!(t?.id && t?.name && t?.config))
          if (defaultTemplate?.id && !items.some((t) => t.id === defaultTemplate.id)) items.unshift(defaultTemplate)
          setTemplates(items)
          if (!selectedTemplateId && defaultTemplate?.id) onSelectTemplate(defaultTemplate)
        }
      }
    } catch (err) { console.error('Failed to fetch templates:', err) } finally { setLoading(false) }
  }, [selectedTemplateId, onSelectTemplate])

  useEffect(() => { fetchTemplates() }, [fetchTemplates])

  const selected = templates.find(t => t.id === selectedTemplateId)

  return (
    <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border/50 flex items-center gap-2">
        <Layout size={13} className="text-accent" />
        <span className="text-xs font-semibold text-text-primary">Template</span>
      </div>
      <div className="p-2">
        <div className="relative">
          <button
            onClick={() => setIsOpen(!isOpen)}
            className="w-full flex items-center justify-between p-2 bg-surface border border-border/30 rounded-lg hover:border-border transition-all text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
          >
            <div className="flex items-center gap-2 min-w-0">
              <div className="w-6 h-6 rounded bg-gradient-to-br from-yellow-500 to-amber-500 flex items-center justify-center flex-shrink-0">
                <Layout size={10} className="text-white" />
              </div>
              <div className="min-w-0">
                <p className="text-[11px] font-medium text-text-primary truncate">{selected?.name || 'Select template'}</p>
                <p className="text-[9px] text-text-muted">{selected ? `v${selected.version}` : 'Choose'}</p>
              </div>
            </div>
            <ChevronDown size={12} className={`text-text-muted transition-transform flex-shrink-0 ${isOpen ? 'rotate-180' : ''}`} />
          </button>

          {isOpen && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-surface-elevated border border-border rounded-lg shadow-lg z-10 overflow-hidden">
              <div className="p-1 max-h-[150px] overflow-y-auto">
                {loading ? (
                  <div className="p-2 text-center text-text-muted text-[10px]">Loading...</div>
                ) : templates.length === 0 ? (
                  <div className="p-2 text-center text-text-muted text-[10px]">No templates</div>
                ) : templates.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => { onSelectTemplate(t); setIsOpen(false) }}
                    className={`w-full flex items-center gap-2 p-1.5 rounded-lg transition-all ${selectedTemplateId === t.id ? 'bg-accent/10' : 'hover:bg-surface-hover'}`}
                  >
                    <div className="w-6 h-6 rounded bg-gradient-to-br from-yellow-500 to-amber-500 flex items-center justify-center flex-shrink-0">
                      <Layout size={10} className="text-white" />
                    </div>
                    <div className="flex-1 text-left min-w-0">
                      <p className="text-[11px] font-medium text-text-primary truncate">{t.name}</p>
                      <p className="text-[9px] text-text-muted truncate">v{t.version}</p>
                    </div>
                    {selectedTemplateId === t.id && <Check size={10} className="text-accent flex-shrink-0" />}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {selected && (
          <div className="mt-2 px-2 py-1.5 bg-surface/30 rounded-lg space-y-1">
            <div className="flex items-center justify-between text-[9px]">
              <span className="text-text-muted">Canvas</span>
              <span className="text-text-secondary">{selected.config?.canvas?.width}x{selected.config?.canvas?.height}</span>
            </div>
            <div className="flex items-center justify-between text-[9px]">
              <span className="text-text-muted">Title</span>
              <div className="flex items-center gap-1">
                <div className="w-2 h-2 rounded" style={{ backgroundColor: selected.config?.title?.color }} />
                <span className="text-text-secondary">{selected.config?.title?.color}</span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
