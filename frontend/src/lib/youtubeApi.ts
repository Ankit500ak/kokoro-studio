import { API_BASE } from './api'
import { fetchWithTimeout } from './fetch'

export interface YouTubeStatus {
  connected: boolean
  channel_title: string | null
  channel_id: string | null
  expires_at: string | null
}

export interface YouTubeUpload {
  id: string
  video_id: string | null
  video_url: string | null
  title: string
  description: string | null
  tags: string[]
  thumbnail_path: string | null
  privacy_status: string
  status: string
  error_message: string | null
  created_at: string | null
  uploaded_at: string | null
}

export interface MetadataPreview {
  title: string
  description: string
  tags: string[]
  hashtags: string[]
  title_options: string[]
  category_id: string
}

export interface Playlist {
  id: string
  title: string
  video_count: number
}

export async function fetchYouTubeStatus(): Promise<YouTubeStatus> {
  const res = await fetchWithTimeout(`${API_BASE}/youtube/status`, { timeout: 8000 })
  if (!res.ok) throw new Error('Failed to fetch YouTube status')
  return res.json()
}

export async function startYouTubeAuth(): Promise<{ auth_url: string }> {
  const res = await fetchWithTimeout(`${API_BASE}/youtube/auth`, { timeout: 8000 })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to start auth')
  }
  return res.json()
}

export async function disconnectYouTube(): Promise<void> {
  const res = await fetchWithTimeout(`${API_BASE}/youtube/disconnect`, {
    method: 'POST',
    timeout: 8000,
  })
  if (!res.ok) throw new Error('Failed to disconnect')
}

export async function previewMetadata(params: {
  render_output_id: string
  niche: string
  topic: string
  title_override?: string
}): Promise<MetadataPreview> {
  const res = await fetchWithTimeout(`${API_BASE}/youtube/metadata/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    timeout: 15000,
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Failed to generate metadata')
  }
  return res.json()
}

export async function uploadToYouTube(params: {
  render_output_id: string
  privacy_status?: string
  playlist_id?: string | null
  schedule_time?: string | null
  auto_metadata?: boolean
  title?: string
  description?: string
  tags?: string[]
  niche?: string
  topic?: string
}): Promise<YouTubeUpload> {
  const res = await fetchWithTimeout(`${API_BASE}/youtube/upload`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    timeout: 30000,
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    if (res.status === 429) {
      throw new Error(err.detail || 'YouTube quota exceeded. Will retry after midnight Pacific Time.')
    }
    throw new Error(err.detail || 'Upload failed')
  }
  return res.json()
}

export async function fetchUploads(limit = 50, status?: string): Promise<{ items: YouTubeUpload[]; total: number }> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (status) params.set('status', status)
  const res = await fetchWithTimeout(`${API_BASE}/youtube/uploads?${params}`, { timeout: 8000 })
  if (!res.ok) throw new Error('Failed to fetch uploads')
  return res.json()
}

export async function fetchUpload(uploadId: string): Promise<YouTubeUpload> {
  const res = await fetchWithTimeout(`${API_BASE}/youtube/uploads/${uploadId}`, { timeout: 8000 })
  if (!res.ok) throw new Error('Failed to fetch upload')
  return res.json()
}

export async function deleteUpload(uploadId: string): Promise<void> {
  const res = await fetchWithTimeout(`${API_BASE}/youtube/uploads/${uploadId}`, {
    method: 'DELETE',
    timeout: 8000,
  })
  if (!res.ok) throw new Error('Failed to delete upload')
}

export async function fetchPlaylists(): Promise<Playlist[]> {
  const res = await fetchWithTimeout(`${API_BASE}/youtube/playlists`, { timeout: 8000 })
  if (!res.ok) throw new Error('Failed to fetch playlists')
  return res.json()
}

export async function generateThumbnail(params: {
  render_output_id: string
  title: string
  niche: string
}): Promise<{ thumbnail_path: string; filename: string }> {
  const res = await fetchWithTimeout(`${API_BASE}/youtube/thumbnail/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    timeout: 30000,
    body: JSON.stringify(params),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || 'Thumbnail generation failed')
  }
  return res.json()
}

export async function fetchUploadQueue(): Promise<{ queue_size: number; active_uploads: number; jobs: any[] }> {
  const res = await fetchWithTimeout(`${API_BASE}/youtube/queue`, { timeout: 8000 })
  if (!res.ok) throw new Error('Failed to fetch queue')
  return res.json()
}

export async function directUploadToYouTube(params: {
  video: File
  privacy_status?: string
  playlist_id?: string | null
  auto_metadata?: boolean
  title?: string
  description?: string
  tags?: string[]
  niche?: string
  topic?: string
}): Promise<YouTubeUpload> {
  const formData = new FormData()
  formData.append('video', params.video)
  if (params.privacy_status) formData.append('privacy_status', params.privacy_status)
  if (params.playlist_id) formData.append('playlist_id', params.playlist_id)
  if (params.auto_metadata !== undefined) formData.append('auto_metadata', String(params.auto_metadata))
  if (params.title) formData.append('title', params.title)
  if (params.description) formData.append('description', params.description)
  if (params.tags) formData.append('tags', JSON.stringify(params.tags))
  if (params.niche) formData.append('niche', params.niche)
  if (params.topic) formData.append('topic', params.topic)

  const res = await fetchWithTimeout(`${API_BASE}/youtube/direct-upload`, {
    method: 'POST',
    body: formData,
    timeout: 60000,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    if (res.status === 429) {
      throw new Error(err.detail || 'YouTube quota exceeded. Will retry after midnight Pacific Time.')
    }
    throw new Error(err.detail || 'Upload failed')
  }
  return res.json()
}
