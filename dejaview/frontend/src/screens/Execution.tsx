import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Play, CheckCircle, XCircle } from 'lucide-react'
import { useBackendEvent } from '../hooks/usePyBridge.ts'

export function Execution() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const [current, setCurrent] = useState(0)
  const [total, setTotal] = useState(0)
  const [stage, setStage] = useState('cleanup')
  const [logs, setLogs] = useState<string[]>([])
  const [complete, setComplete] = useState(false)
  const [successCount, setSuccessCount] = useState(0)
  const [errorCount, setErrorCount] = useState(0)
  const logEndRef = useRef<HTMLDivElement>(null)

  useBackendEvent('exec:progress', (e: CustomEvent) => {
    if (e.detail.current != null) setCurrent(e.detail.current)
    if (e.detail.total != null) setTotal(e.detail.total)
    if (e.detail.action && e.detail.action !== 'log') setStage(e.detail.action)
    if (e.detail.file_path) {
      setLogs((prev) => [...prev, e.detail.file_path])
    }
  })

  useBackendEvent('exec:complete', (e: CustomEvent) => {
    setComplete(true)
    setSuccessCount(e.detail.success)
    setErrorCount(e.detail.errors)
  })

  useBackendEvent('exec:error', (e: CustomEvent) => {
    setLogs((prev) => [...prev, `ERROR: ${e.detail.message} — ${e.detail.file_path}`])
  })

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  const progress = total > 0 ? (current / total) * 100 : 0

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold text-dv-text mb-6">{t('execution.title')}</h1>

      {/* Progress section */}
      <div className="bg-dv-surface rounded-xl border border-dv-border p-6 mb-6">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            {complete ? (
              errorCount > 0 ? (
                <XCircle size={20} className="text-dv-warning" />
              ) : (
                <CheckCircle size={20} className="text-dv-success" />
              )
            ) : (
              <Play size={20} className="text-dv-primary" />
            )}
            <span className="font-medium text-dv-text">
              {complete
                ? t('execution.complete')
                : stage === 'cleanup'
                  ? t('execution.stage_cleanup')
                  : t('execution.stage_sync')}
            </span>
          </div>
          <span className="text-sm text-dv-text-muted">
            {t('execution.progress', { current, total })}
          </span>
        </div>

        <div className="w-full h-3 bg-dv-bg rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${
              complete ? 'bg-dv-success' : 'bg-dv-primary'
            }`}
            style={{ width: `${progress}%` }}
          />
        </div>

        {complete && (
          <div data-testid="execution-complete" className="flex gap-4 mt-4 text-sm">
            <span className="text-dv-success">
              {t('execution.success_count', { count: successCount })}
            </span>
            {errorCount > 0 && (
              <span className="text-dv-danger">
                {t('execution.error_count', { count: errorCount })}
              </span>
            )}
          </div>
        )}
      </div>

      {/* Log output */}
      <div className="bg-dv-bg rounded-xl border border-dv-border p-4 h-80 overflow-y-auto font-mono text-xs text-dv-text-muted">
        {logs.map((log, i) => (
          <div key={i} className={`py-0.5 ${log.startsWith('ERROR') ? 'text-dv-danger' : ''}`}>
            {log}
          </div>
        ))}
        <div ref={logEndRef} />
      </div>

      {/* Action buttons */}
      <div className="flex gap-3 mt-6">
        {complete && (
          <button
            data-testid="btn-view-bin"
            onClick={() => navigate('/bin')}
            className="px-5 py-2.5 bg-dv-primary hover:bg-dv-primary-hover text-white rounded-lg transition-colors font-medium"
          >
            {t('execution.view_bin')}
          </button>
        )}
      </div>
    </div>
  )
}
