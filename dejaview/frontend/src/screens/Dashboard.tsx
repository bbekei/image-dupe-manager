import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { FolderSearch, Images, Users, HardDrive, Plus } from 'lucide-react'
import { callBackend, usePyBridgeReady } from '../hooks/usePyBridge.ts'
import { useScanStore } from '../stores/useScanStore.ts'
import type { Session, ScanSummary } from '../types/api.ts'

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

interface StatCardProps {
  icon: React.ReactNode
  label: string
  value: string | number
  color: string
}

function StatCard({ icon, label, value, color }: StatCardProps) {
  return (
    <div className="bg-dv-surface rounded-xl p-5 border border-dv-border">
      <div className="flex items-center gap-3 mb-3">
        <div className={`p-2 rounded-lg ${color}`}>{icon}</div>
        <span className="text-dv-text-muted text-sm">{label}</span>
      </div>
      <div className="text-2xl font-bold text-dv-text">{value}</div>
    </div>
  )
}

export function Dashboard() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { setSessionId } = useScanStore()
  const [sessions, setSessions] = useState<Session[]>([])
  const [summary, setSummary] = useState<ScanSummary | null>(null)
  const [loading, setLoading] = useState(true)

  const loadData = useCallback(async () => {
    try {
      const sessions = await callBackend<Session[]>('get_sessions')
      setSessions(sessions)
      if (sessions.length > 0) {
        const latest = sessions[0]
        const sum = await callBackend<ScanSummary>('get_scan_summary', latest.id)
        setSummary(sum)
      }
    } catch {
      // pywebview not available (dev mode)
    } finally {
      setLoading(false)
    }
  }, [])

  usePyBridgeReady(loadData)
  useEffect(() => { loadData() }, [loadData])

  const handleStartScan = async () => {
    try {
      const folders = await callBackend<string[]>('select_folders')
      if (folders && folders.length > 0) {
        const sessionId = await callBackend<number>(
          'start_scan',
          folders,
          `Scan ${new Date().toLocaleDateString()}`,
          false,
        )
        setSessionId(sessionId)
        navigate('/browse')
      }
    } catch {
      // User cancelled folder selection
    }
  }

  const handleSessionClick = (session: Session) => {
    setSessionId(session.id)
    if (session.status === 'paused') {
      navigate('/browse')
    } else if (session.status === 'complete') {
      navigate('/browse')
    }
  }

  return (
    <div className="max-w-6xl">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-dv-text">{t('dashboard.title')}</h1>
          <p className="text-dv-text-muted mt-1">{t('dashboard.welcome')}</p>
        </div>
        <button
          onClick={handleStartScan}
          className="flex items-center gap-2 px-5 py-2.5 bg-dv-primary hover:bg-dv-primary-hover text-white rounded-lg transition-colors font-medium"
        >
          <Plus size={18} />
          {t('dashboard.start_scan')}
        </button>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        <StatCard
          icon={<FolderSearch size={20} className="text-dv-primary" />}
          label={t('dashboard.stats.local_duplicates')}
          value={summary?.total_groups ?? 0}
          color="bg-dv-primary/10"
        />
        <StatCard
          icon={<Images size={20} className="text-amber-400" />}
          label={t('dashboard.stats.similar_images')}
          value={summary?.similarity_group_count ?? 0}
          color="bg-amber-400/10"
        />
        <StatCard
          icon={<Users size={20} className="text-emerald-400" />}
          label={t('dashboard.stats.family_photos')}
          value={0}
          color="bg-emerald-400/10"
        />
        <StatCard
          icon={<HardDrive size={20} className="text-blue-400" />}
          label={t('dashboard.stats.recoverable_space')}
          value={summary ? formatBytes(summary.recoverable_bytes) : '0 B'}
          color="bg-blue-400/10"
        />
      </div>

      {/* Recent Sessions */}
      <div>
        <h2 className="text-lg font-semibold text-dv-text mb-4">
          {t('dashboard.recent_sessions')}
        </h2>

        {loading ? (
          <div className="text-dv-text-muted py-8 text-center">{t('common.loading')}</div>
        ) : sessions.length === 0 ? (
          <div className="bg-dv-surface rounded-xl border border-dv-border p-8 text-center">
            <FolderSearch size={48} className="mx-auto mb-4 text-dv-text-muted" />
            <p className="text-dv-text-muted">{t('dashboard.no_sessions')}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {sessions.map((session) => (
              <button
                key={session.id}
                onClick={() => handleSessionClick(session)}
                className="w-full bg-dv-surface hover:bg-dv-surface-hover rounded-xl border border-dv-border p-4 flex items-center justify-between transition-colors text-left"
              >
                <div>
                  <div className="font-medium text-dv-text">{session.name}</div>
                  <div className="text-sm text-dv-text-muted mt-1">
                    {session.file_count} {t('dashboard.session.files')} &middot;{' '}
                    {new Date(session.created_at).toLocaleDateString()}
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-medium ${
                      session.status === 'complete'
                        ? 'bg-dv-success/10 text-dv-success'
                        : session.status === 'paused'
                          ? 'bg-dv-warning/10 text-dv-warning'
                          : session.status === 'in_progress'
                            ? 'bg-dv-info/10 text-dv-info'
                            : 'bg-dv-danger/10 text-dv-danger'
                    }`}
                  >
                    {session.status}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
