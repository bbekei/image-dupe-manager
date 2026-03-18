import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Users, RefreshCw, Upload, Download } from 'lucide-react'
import { toast } from 'sonner'
import { callBackend } from '../hooks/usePyBridge.ts'
import { useScanStore } from '../stores/useScanStore.ts'
import type { RemotePeer } from '../types/api.ts'

export function Family() {
  const { t } = useTranslation()
  const { sessionId } = useScanStore()
  const [peers, setPeers] = useState<RemotePeer[]>([])
  const [syncing, setSyncing] = useState(false)
  const [loading, setLoading] = useState(true)

  const loadPeers = useCallback(async () => {
    setLoading(true)
    try {
      const result = await callBackend<RemotePeer[]>('get_remote_peers')
      setPeers(result)
    } catch {
      // handle error
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadPeers() }, [loadPeers])

  const handleSync = async () => {
    setSyncing(true)
    try {
      const result = await callBackend<{ status: string; errors: Record<string, string> }>('sync_drive')
      if (Object.keys(result.errors).length > 0) {
        toast.error(`Sync completed with errors`)
      } else {
        toast.success(`Sync completed: ${result.status}`)
      }
      loadPeers()
    } catch {
      toast.error('Sync failed')
    } finally {
      setSyncing(false)
    }
  }

  const handleExport = async () => {
    if (!sessionId) return
    try {
      const path = await callBackend<string>('export_hashes', { session_id: sessionId })
      toast.success(`Exported to ${path}`)
    } catch {
      toast.error('Export failed')
    }
  }

  const handleImport = async () => {
    try {
      // The backend handles file selection
      const result = await callBackend<{ imported: number; username?: string; error?: string }>('import_hashes', { file_path: '' })
      if (result.error) {
        toast.error(`Import failed: ${result.error}`)
      } else {
        toast.success(`Imported peer '${result.username}'`)
      }
      loadPeers()
    } catch {
      toast.error('Import failed')
    }
  }

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-dv-text">{t('family.title')}</h1>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleExport}
            className="flex items-center gap-2 px-4 py-2 bg-dv-surface hover:bg-dv-surface-hover text-dv-text border border-dv-border rounded-lg text-sm transition-colors"
          >
            <Upload size={14} />
            {t('family.export')}
          </button>
          <button
            onClick={handleImport}
            className="flex items-center gap-2 px-4 py-2 bg-dv-surface hover:bg-dv-surface-hover text-dv-text border border-dv-border rounded-lg text-sm transition-colors"
          >
            <Download size={14} />
            {t('family.import')}
          </button>
          <button
            onClick={handleSync}
            disabled={syncing}
            className="flex items-center gap-2 px-4 py-2 bg-dv-primary hover:bg-dv-primary-hover text-white rounded-lg text-sm transition-colors disabled:opacity-50"
          >
            <RefreshCw size={14} className={syncing ? 'animate-spin' : ''} />
            {t('family.sync')}
          </button>
        </div>
      </div>

      <h2 className="text-lg font-semibold text-dv-text mb-4">{t('family.peers')}</h2>

      {loading ? (
        <div className="text-dv-text-muted text-center py-8">{t('common.loading')}</div>
      ) : peers.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-dv-text-muted gap-4">
          <Users size={48} />
          <p>{t('family.no_peers')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {peers.map((peer) => (
            <div
              key={peer.id}
              className="bg-dv-surface rounded-xl border border-dv-border p-4 flex items-center justify-between"
            >
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-dv-primary/10 flex items-center justify-center text-dv-primary font-bold">
                  {peer.username[0].toUpperCase()}
                </div>
                <div>
                  <div className="font-medium text-dv-text">{peer.username}</div>
                  <div className="text-xs text-dv-text-muted">
                    {t('family.last_sync', {
                      time: new Date(peer.last_seen_at).toLocaleDateString(),
                    })}
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
