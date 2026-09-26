import { useState } from 'react'
import { previewMetadata, type MetadataPreview } from '../lib/youtubeApi'
import { Sparkles, Tag, Hash, FileText, RefreshCw } from 'lucide-react'

interface MetadataEditorProps {
  renderOutputId: string
  niche: string
  topic: string
  onApply?: (title: string, description: string, tags: string[]) => void
}

export function MetadataEditor({ renderOutputId, niche, topic, onApply }: MetadataEditorProps) {
  const [metadata, setMetadata] = useState<MetadataPreview | null>(null)
  const [loading, setLoading] = useState(false)
  const [selectedTitle, setSelectedTitle] = useState('')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState<string[]>([])
  const [newTag, setNewTag] = useState('')

  const handleGenerate = async () => {
    setLoading(true)
    try {
      const data = await previewMetadata({ render_output_id: renderOutputId, niche, topic })
      setMetadata(data)
      setSelectedTitle(data.title)
      setDescription(data.description)
      setTags(data.tags)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  const addTag = () => {
    if (newTag.trim() && !tags.includes(newTag.trim())) {
      setTags([...tags, newTag.trim()])
      setNewTag('')
    }
  }

  const removeTag = (tag: string) => {
    setTags(tags.filter(t => t !== tag))
  }

  const handleApply = () => {
    onApply?.(selectedTitle, description, tags)
  }

  return (
    <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border/50 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <FileText size={13} className="text-accent" />
          <span className="text-xs font-semibold text-text-primary">Metadata Editor</span>
        </div>
        <button
          onClick={handleGenerate}
          disabled={loading}
          className="flex items-center gap-1 text-[10px] text-accent hover:text-accent-hover disabled:opacity-50"
        >
          {loading ? <RefreshCw size={10} className="animate-spin" /> : <Sparkles size={10} />}
          {metadata ? 'Regenerate' : 'Generate'}
        </button>
      </div>

      {metadata && (
        <div className="p-3 space-y-3">
          {/* Title options */}
          <div>
            <label className="text-[9px] font-semibold text-text-muted uppercase tracking-wider mb-1 block">Title</label>
            <input
              type="text"
              value={selectedTitle}
              onChange={(e) => setSelectedTitle(e.target.value)}
              className="w-full bg-surface border border-border/30 rounded-lg px-2 py-1.5 text-[11px] text-text-primary outline-none focus:border-accent"
              maxLength={100}
            />
            <div className="flex gap-1 mt-1">
              {metadata.title_options.map((opt, i) => (
                <button
                  key={i}
                  onClick={() => setSelectedTitle(opt)}
                  className={`text-[8px] px-1.5 py-0.5 rounded border transition-colors ${
                    selectedTitle === opt
                      ? 'bg-accent/15 border-accent/30 text-accent'
                      : 'bg-surface border-border/20 text-text-muted hover:text-text-primary'
                  }`}
                >
                  Option {i + 2}
                </button>
              ))}
            </div>
            <div className="text-[9px] text-text-muted mt-0.5">{selectedTitle.length}/100</div>
          </div>

          {/* Description */}
          <div>
            <label className="text-[9px] font-semibold text-text-muted uppercase tracking-wider mb-1 block">Description</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={5}
              className="w-full bg-surface border border-border/30 rounded-lg px-2 py-1.5 text-[11px] text-text-secondary outline-none focus:border-accent resize-none"
              maxLength={5000}
            />
            <div className="text-[9px] text-text-muted mt-0.5">{description.length}/5000</div>
          </div>

          {/* Tags */}
          <div>
            <label className="text-[9px] font-semibold text-text-muted uppercase tracking-wider mb-1 flex items-center gap-1">
              <Tag size={9} /> Tags ({tags.length})
            </label>
            <div className="flex flex-wrap gap-1 mb-1.5">
              {tags.map((tag) => (
                <span
                  key={tag}
                  className="text-[9px] px-1.5 py-0.5 rounded bg-surface border border-border/30 text-text-secondary flex items-center gap-1"
                >
                  {tag}
                  <button onClick={() => removeTag(tag)} className="text-text-muted hover:text-red-400">&times;</button>
                </span>
              ))}
            </div>
            <div className="flex gap-1">
              <input
                type="text"
                value={newTag}
                onChange={(e) => setNewTag(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addTag()}
                placeholder="Add tag..."
                className="flex-1 bg-surface border border-border/30 rounded px-2 py-1 text-[10px] text-text-primary outline-none"
              />
              <button onClick={addTag} className="px-2 py-1 bg-surface border border-border/30 rounded text-[10px] text-text-muted hover:text-text-primary">+</button>
            </div>
          </div>

          {/* Hashtags */}
          <div>
            <label className="text-[9px] font-semibold text-text-muted uppercase tracking-wider mb-1 flex items-center gap-1">
              <Hash size={9} /> Hashtags
            </label>
            <div className="flex flex-wrap gap-1">
              {metadata.hashtags.map((tag) => (
                <span key={tag} className="text-[9px] text-accent">#{tag}</span>
              ))}
            </div>
          </div>

          {onApply && (
            <button
              onClick={handleApply}
              className="w-full py-1.5 rounded-lg bg-accent text-white text-[11px] font-medium hover:bg-accent-hover transition-colors"
            >
              Apply to Upload
            </button>
          )}
        </div>
      )}
    </div>
  )
}
