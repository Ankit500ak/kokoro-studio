import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchYouTubeStatus, startYouTubeAuth, disconnectYouTube, type YouTubeStatus } from '../lib/youtubeApi'
import { Youtube, CheckCircle2, XCircle, Loader2, ExternalLink } from 'lucide-react'
import { useToast } from './Toast'

interface YouTubeAuthPanelProps {
  onStatusChange?: (connected: boolean) => void
}

export function YouTubeAuthPanel({ onStatusChange }: YouTubeAuthPanelProps) {
  const [status, setStatus] = useState<YouTubeStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [connecting, setConnecting] = useState(false)
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pollTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const toast = useToast()

  const checkStatus = useCallback(async () => {
    try {
      const s = await fetchYouTubeStatus()
      setStatus(s)
      onStatusChange?.(s.connected)
    } catch {
      setStatus({ connected: false, channel_title: null, channel_id: null, expires_at: null })
    } finally {
      setLoading(false)
    }
  }, [onStatusChange])

  useEffect(() => { checkStatus() }, [checkStatus])

  useEffect(() => {
    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current)
        pollIntervalRef.current = null
      }
      if (pollTimeoutRef.current) {
        clearTimeout(pollTimeoutRef.current)
        pollTimeoutRef.current = null
      }
    }
  }, [])

  const handleConnect = async () => {
    setConnecting(true)
    try {
      const { auth_url } = await startYouTubeAuth()
      window.open(auth_url, '_blank', 'width=600,height=700')
      // Poll status after user authorizes
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current)
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current)
      pollIntervalRef.current = setInterval(async () => {
        await checkStatus()
      }, 3000)
      pollTimeoutRef.current = setTimeout(() => {
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current)
          pollIntervalRef.current = null
        }
      }, 120000)
    } catch (err) {
      console.error(err)
    } finally {
      setConnecting(false)
    }
  }

  const handleDisconnect = async () => {
    try {
      await disconnectYouTube()
      setStatus({ connected: false, channel_title: null, channel_id: null, expires_at: null })
      onStatusChange?.(false)
      toast.success('YouTube disconnected')
    } catch (err) {
      toast.error('Failed to disconnect')
      console.error(err)
    }
  }

  if (loading) {
    return (
      <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
        <div className="px-3 py-2 border-b border-border/50 flex items-center gap-2">
          <Youtube size={13} className="text-red-500" />
          <span className="text-xs font-semibold text-text-primary">YouTube</span>
        </div>
        <div className="p-3 text-[11px] text-text-muted">Checking connection...</div>
      </div>
    )
  }

  return (
    <div className="bg-surface-elevated rounded-xl border border-border overflow-hidden">
      <div className="px-3 py-2 border-b border-border/50 flex items-center gap-2">
        <Youtube size={13} className="text-red-500" />
        <span className="text-xs font-semibold text-text-primary">YouTube</span>
        {status?.connected && (
          <CheckCircle2 size={11} className="text-green-400 ml-auto" />
        )}
      </div>

      <div className="p-3 space-y-2">
        {status?.connected ? (
          <>
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-red-500/20 flex items-center justify-center">
                <Youtube size={14} className="text-red-500" />
              </div>
              <div>
                <div className="text-[11px] font-medium text-text-primary">{status.channel_title}</div>
                <div className="text-[9px] text-green-400">Connected</div>
              </div>
            </div>
            <button
              onClick={handleDisconnect}
              className="w-full flex items-center justify-center gap-1.5 py-1.5 rounded-lg bg-red-500/10 text-red-400 text-[10px] font-medium hover:bg-red-500/20 transition-colors"
            >
              <XCircle size={10} />
              Disconnect
            </button>
          </>
        ) : (
          <>
            <p className="text-[10px] text-text-muted">Connect your YouTube channel to upload videos automatically.</p>
            <button
              onClick={handleConnect}
              disabled={connecting}
              className="w-full flex items-center justify-center gap-2 py-2 rounded-lg bg-red-600 text-white text-[11px] font-medium hover:bg-red-700 disabled:opacity-50 transition-colors"
            >
              {connecting ? (
                <><Loader2 size={12} className="animate-spin" /> Connecting...</>
              ) : (
                <><Youtube size={12} /> Connect YouTube</>
              )}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
