import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  FolderSearch, Images, Users, HardDrive, Plus,
  Pause, Square, Search, Loader2, AlertTriangle,
} from 'lucide-react'
import { callBackend, usePyBridgeReady, useScanProgress, useBackendEvent } from '../hooks/usePyBridge.ts'
import { useScanStore } from '../stores/useScanStore.ts'
import type { Session, ScanSummary, ScanProgress } from '../types/api.ts'

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

function ScanProgressPanel() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const {
    phase, sessionId, current, total, discovered,
    duplicatesFound, scanErrors,
    setProgress, setStatus, setDiscovered, incrementDuplicates, addScanError,
  } = useScanStore()

  const isActive = phase !== 'idle' && phase !== 'complete' && phase !== 'stopped' && phase !== 'error'

  // Seed initial state from backend (recovery after navigation away and back).
  // Only poll when the store is still in 'idle' — if real-time events have
  // already moved the phase forward (e.g. 'started', 'hashing'), the poll
  // must not overwrite with a later phase that arrived faster via IPC
  // (e.g. 'complete' for a scan with no size-duplicate candidates).
  useEffect(() => {
    if (!sessionId) return
    const currentPhase = useScanStore.getState().phase
    if (currentPhase !== 'idle') return  // real-time events already active
    callBackend<ScanProgress>('get_scan_progress').then(p => {
      // Double-check: if events arrived while the poll was in-flight, don't overwrite
      if (useScanStore.getState().phase !== 'idle') return
      setDiscovered(p.discovered)
      if (p.phase === 'hashing' || p.phase === 'similarity') {
        setProgress(p.current, p.total, p.phase)
      } else {
        setStatus(p.phase, p.message)
      }
    }).catch(() => {})
  }, [sessionId, setProgress, setStatus, setDiscovered])

  // Push events from backend (replaces polling)
  useScanProgress({
    onProgress: (c, t, p) => setProgress(c, t, p),
    onStatus: (status, message) => setStatus(status, message),
    onDuplicateFound: (_hash, count) => incrementDuplicates(count),
    onError: (path, message) => addScanError(path, message),
  })

  useBackendEvent<{ discovered: number }>('scan:discovery_progress', (payload) => {
    setDiscovered(payload.discovered)
  })

  const handlePause = async () => {
    await callBackend('pause_scan')
  }

  const handleStop = async () => {
    await callBackend('stop_scan')
  }

  const handleResume = async () => {
    if (sessionId) await callBackend('resume_scan', { session_id: sessionId })
  }

  if (phase === 'idle') return null

  const pct = total > 0
    ? Math.round((current / total) * 100)
    : 0

  return (
    <div data-testid="scan-progress-panel" className="bg-dv-surface rounded-xl border border-dv-border p-5 mb-8">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-3">
          {isActive && <Loader2 size={20} className="text-dv-primary animate-spin" />}
          <h3 className="font-semibold text-dv-text">{t('scan.title')}</h3>
        </div>
        <div className="flex items-center gap-2">
          {isActive && phase !== 'paused' && (
            <button
              onClick={handlePause}
              className="p-1.5 rounded bg-dv-surface-hover hover:bg-dv-border text-dv-text-muted"
              title={t('scan.pause')}
            >
              <Pause size={16} />
            </button>
          )}
          {isActive && (
            <button
              onClick={handleStop}
              className="p-1.5 rounded bg-dv-surface-hover hover:bg-dv-border text-dv-text-muted"
              title={t('scan.stop')}
            >
              <Square size={16} />
            </button>
          )}
          {phase === 'paused' && (
            <button
              onClick={handleResume}
              className="px-3 py-1.5 rounded bg-dv-primary hover:bg-dv-primary-hover text-white text-sm"
            >
              {t('scan.resume')}
            </button>
          )}
          {phase === 'complete' && (
            <button
              data-testid="btn-view-results"
              onClick={() => navigate('/browse')}
              className="flex items-center gap-2 px-3 py-1.5 rounded bg-dv-primary hover:bg-dv-primary-hover text-white text-sm"
            >
              <Search size={14} />
              {t('dashboard.session.view_results')}
            </button>
          )}
        </div>
      </div>

      {/* Phase label */}
      <div className="text-sm text-dv-text-muted mb-2">
        {phase === 'discovery' && t('scan.phase.discovery')}
        {phase === 'hashing' && t('scan.phase.hashing')}
        {phase === 'similarity' && t('scan.phase.similarity')}
        {phase === 'complete' && t('scan.complete')}
        {phase === 'paused' && t('scan.paused')}
        {phase === 'stopped' && t('scan.stopped')}
      </div>

      {/* Progress bar — shown during active scan */}
      {isActive && (
        <>
          <div className="w-full bg-dv-bg rounded-full h-2.5 mb-2">
            <div
              className={`h-2.5 rounded-full transition-all duration-300 ${
                phase === 'paused' ? 'bg-dv-warning' : 'bg-dv-primary'
              }`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="flex items-center justify-between text-xs text-dv-text-muted">
            <span>
              {total > 0
                ? t('scan.progress', { current, total })
                : t('scan.discovered', { count: discovered })}
            </span>
            {total > 0 && <span>{pct}%</span>}
          </div>
        </>
      )}

      {/* Summary stats — shown after completion so fast scans still inform the user */}
      {phase === 'complete' && (
        <div className="flex items-center gap-4 text-xs text-dv-text-muted">
          <span>{t('scan.discovered', { count: discovered })}</span>
          <span>{t('scan.duplicates_found', { count: duplicatesFound })}</span>
        </div>
      )}

      {/* Duplicates found counter — shown during active scan */}
      {isActive && duplicatesFound > 0 && (
        <div className="mt-2 text-xs text-dv-text-muted">
          {t('scan.duplicates_found', { count: duplicatesFound })}
        </div>
      )}

      {/* Scan errors — subtle inline indicator */}
      {scanErrors.length > 0 && (
        <div className="mt-2 flex items-start gap-1.5 text-xs text-dv-warning">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          <span>
            {t('scan.errors_count', { count: scanErrors.length })}
            {' — '}
            <span className="text-dv-text-muted">{scanErrors[scanErrors.length - 1].path}: {scanErrors[scanErrors.length - 1].message}</span>
          </span>
        </div>
      )}
    </div>
  )
}

export function Dashboard() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { setSessionId, phase, reset } = useScanStore()
  const [sessions, setSessions] = useState<Session[]>([])
  const [summary, setSummary] = useState<ScanSummary | null>(null)
  const [loading, setLoading] = useState(true)

  const loadData = useCallback(async () => {
    try {
      const sessions = await callBackend<Session[]>('get_sessions')
      setSessions(sessions)
      if (sessions.length > 0) {
        const latest = sessions[0]
        const sum = await callBackend<ScanSummary>('get_scan_summary', { session_id: latest.id })
        setSummary(sum)
      }
    } catch {
      // backend not available (dev mode)
    } finally {
      setLoading(false)
    }
  }, [])

  usePyBridgeReady(loadData)
  useEffect(() => { loadData() }, [loadData])

  // Reload session data when scan completes so stats update immediately
  useEffect(() => {
    if (phase === 'complete') loadData()
  }, [phase, loadData])

  const isScanning = phase !== 'idle' && phase !== 'complete' && phase !== 'error' && phase !== 'stopped'
  const [enableSimilarity, setEnableSimilarity] = useState(false)

  const handleStartScan = async () => {
    try {
      // select_and_start_scan opens the folder picker and immediately starts
      // the scan in a single Rust command, avoiding a second IPC hop after
      // the dialog closes (unreliable in some GTK environments).
      const sessionId = await callBackend<number | null>(
        'select_and_start_scan',
        {
          session_name: `Scan ${new Date().toLocaleDateString()}`,
          enable_similarity: enableSimilarity,
        },
      )
      if (sessionId != null) {
        // Sidecar emits scan:status 'started' → store updates phase to
        // 'discovery' automatically; just record the session ID here.
        setSessionId(sessionId)
      }
      // null means user cancelled — nothing to do
    } catch {
      reset()
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
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-dv-text-muted cursor-pointer select-none">
            <input
              type="checkbox"
              checked={enableSimilarity}
              onChange={(e) => setEnableSimilarity(e.target.checked)}
              disabled={isScanning}
              className="accent-dv-primary w-4 h-4"
            />
            {t('scan.enable_similarity')}
          </label>
          <button
            onClick={handleStartScan}
            disabled={isScanning}
            className="flex items-center gap-2 px-5 py-2.5 bg-dv-primary hover:bg-dv-primary-hover text-white rounded-lg transition-colors font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Plus size={18} />
            {t('dashboard.start_scan')}
          </button>
        </div>
      </div>

      {/* Scan progress panel — visible during and after scan */}
      <ScanProgressPanel />

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
