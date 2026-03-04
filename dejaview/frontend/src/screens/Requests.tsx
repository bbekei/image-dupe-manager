import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { MessageSquare, Check, X } from 'lucide-react'
import { callBackend } from '../hooks/usePyBridge.ts'
import { useScanStore } from '../stores/useScanStore.ts'
import type { ShareRequest } from '../types/api.ts'

export function Requests() {
  const { t } = useTranslation()
  const { sessionId } = useScanStore()
  const [requests, setRequests] = useState<ShareRequest[]>([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<'incoming' | 'outgoing'>('incoming')

  const loadRequests = useCallback(async () => {
    if (!sessionId) return
    setLoading(true)
    try {
      const result = await callBackend<ShareRequest[]>('get_requests', sessionId)
      setRequests(result)
    } catch {
      // handle error
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => { loadRequests() }, [loadRequests])

  const handleRespond = async (requestId: number, response: string) => {
    try {
      await callBackend('respond_to_request', requestId, response)
      loadRequests()
    } catch {
      // handle error
    }
  }

  const filtered = requests.filter((r) => r.direction === tab)

  const statusColor: Record<string, string> = {
    pending: 'bg-dv-warning/10 text-dv-warning',
    approved: 'bg-dv-success/10 text-dv-success',
    declined: 'bg-dv-danger/10 text-dv-danger',
    cancelled: 'bg-dv-text-muted/10 text-dv-text-muted',
  }

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold text-dv-text mb-6">{t('requests.title')}</h1>

      {/* Tabs */}
      <div className="flex gap-1 mb-6 bg-dv-surface rounded-lg p-1 w-fit">
        <button
          onClick={() => setTab('incoming')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            tab === 'incoming'
              ? 'bg-dv-primary text-white'
              : 'text-dv-text-muted hover:text-dv-text'
          }`}
        >
          {t('requests.incoming')}
        </button>
        <button
          onClick={() => setTab('outgoing')}
          className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            tab === 'outgoing'
              ? 'bg-dv-primary text-white'
              : 'text-dv-text-muted hover:text-dv-text'
          }`}
        >
          {t('requests.outgoing')}
        </button>
      </div>

      {loading ? (
        <div className="text-dv-text-muted text-center py-8">{t('common.loading')}</div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-dv-text-muted gap-4">
          <MessageSquare size={48} />
          <p>{t('requests.no_requests')}</p>
        </div>
      ) : (
        <div className="space-y-3">
          {filtered.map((req) => (
            <div
              key={req.id}
              className="bg-dv-surface rounded-xl border border-dv-border p-4 flex items-center justify-between"
            >
              <div>
                <div className="font-medium text-dv-text">{req.peer_username}</div>
                {req.message && (
                  <div className="text-sm text-dv-text-muted mt-1">{req.message}</div>
                )}
                <div className="text-xs text-dv-text-muted mt-1">
                  {new Date(req.created_at).toLocaleDateString()}
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span className={`px-3 py-1 rounded-full text-xs font-medium ${statusColor[req.status]}`}>
                  {t(`requests.status.${req.status}`)}
                </span>
                {tab === 'incoming' && req.status === 'pending' && (
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => handleRespond(req.id, 'approved')}
                      className="p-2 bg-dv-success/10 hover:bg-dv-success/20 rounded-lg transition-colors"
                      title={t('requests.approve')}
                    >
                      <Check size={16} className="text-dv-success" />
                    </button>
                    <button
                      onClick={() => handleRespond(req.id, 'declined')}
                      className="p-2 bg-dv-danger/10 hover:bg-dv-danger/20 rounded-lg transition-colors"
                      title={t('requests.decline')}
                    >
                      <X size={16} className="text-dv-danger" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
