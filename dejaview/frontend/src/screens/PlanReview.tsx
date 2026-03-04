import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { ClipboardList, Check, Trash2, EyeOff, AlertTriangle } from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import { callBackend } from '../hooks/usePyBridge.ts'
import { useScanStore } from '../stores/useScanStore.ts'
import type { PlanSummary } from '../types/api.ts'

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

export function PlanReview() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { sessionId } = useScanStore()
  const [summary, setSummary] = useState<PlanSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const loadPlan = useCallback(async () => {
    if (!sessionId) return
    setLoading(true)
    try {
      const plan = await callBackend<PlanSummary>('get_plan_summary', sessionId)
      setSummary(plan)
    } catch {
      // handle error
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => { loadPlan() }, [loadPlan])

  const handleExecute = async () => {
    if (!sessionId) return
    setConfirmOpen(false)
    try {
      await callBackend('execute_plan', sessionId)
      navigate('/execute')
    } catch {
      // handle error
    }
  }

  const handleClearAll = async () => {
    if (!sessionId) return
    try {
      await callBackend('clear_all_actions', sessionId)
      loadPlan()
    } catch {
      // handle error
    }
  }

  if (loading) {
    return <div className="text-dv-text-muted p-8 text-center">{t('common.loading')}</div>
  }

  if (!summary || (summary.keep_count === 0 && summary.delete_count === 0)) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-dv-text-muted gap-4">
        <ClipboardList size={48} />
        <p>{t('plan.no_actions')}</p>
      </div>
    )
  }

  return (
    <div className="max-w-4xl">
      <h1 className="text-2xl font-bold text-dv-text mb-2">{t('plan.title')}</h1>
      <p className="text-dv-text-muted mb-6">{t('plan.summary')}</p>

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-4 mb-8">
        <div className="bg-dv-surface rounded-xl border border-dv-border p-5 flex items-center gap-3">
          <div className="p-2 rounded-lg bg-dv-success/10">
            <Check size={20} className="text-dv-success" />
          </div>
          <div>
            <div className="text-2xl font-bold text-dv-text">{summary.keep_count}</div>
            <div className="text-xs text-dv-text-muted">{t('plan.keep_count', { count: summary.keep_count })}</div>
          </div>
        </div>
        <div className="bg-dv-surface rounded-xl border border-dv-border p-5 flex items-center gap-3">
          <div className="p-2 rounded-lg bg-dv-danger/10">
            <Trash2 size={20} className="text-dv-danger" />
          </div>
          <div>
            <div className="text-2xl font-bold text-dv-text">{summary.delete_count}</div>
            <div className="text-xs text-dv-text-muted">{t('plan.delete_count', { count: summary.delete_count })}</div>
          </div>
        </div>
        <div className="bg-dv-surface rounded-xl border border-dv-border p-5 flex items-center gap-3">
          <div className="p-2 rounded-lg bg-dv-warning/10">
            <EyeOff size={20} className="text-dv-warning" />
          </div>
          <div>
            <div className="text-2xl font-bold text-dv-text">{summary.ignore_count}</div>
            <div className="text-xs text-dv-text-muted">{t('plan.ignore_count', { count: summary.ignore_count })}</div>
          </div>
        </div>
      </div>

      <div className="bg-dv-surface rounded-xl border border-dv-border p-4 mb-6">
        <div className="text-sm text-dv-text-muted">
          {t('plan.total_space', { size: formatBytes(summary.total_size_bytes) })}
        </div>
      </div>

      {/* Action list */}
      {summary.actions.length > 0 && (
        <div className="bg-dv-surface rounded-xl border border-dv-border mb-6 max-h-96 overflow-y-auto">
          {summary.actions.map((action) => (
            <div
              key={action.file_id}
              className="flex items-center gap-3 px-4 py-2.5 border-b border-dv-border last:border-0"
            >
              {action.action === 'delete' ? (
                <Trash2 size={14} className="text-dv-danger shrink-0" />
              ) : action.action === 'keep' ? (
                <Check size={14} className="text-dv-success shrink-0" />
              ) : (
                <EyeOff size={14} className="text-dv-warning shrink-0" />
              )}
              <div className="flex-1 min-w-0 text-sm text-dv-text truncate" title={action.path}>
                {action.path}
              </div>
              <div className="text-xs text-dv-text-muted shrink-0">{formatBytes(action.size)}</div>
            </div>
          ))}
        </div>
      )}

      {/* Action buttons */}
      <div className="flex gap-3">
        <button
          onClick={() => setConfirmOpen(true)}
          className="flex items-center gap-2 px-6 py-2.5 bg-dv-primary hover:bg-dv-primary-hover text-white rounded-lg transition-colors font-medium"
        >
          {t('plan.execute')}
        </button>
        <button
          onClick={handleClearAll}
          className="px-6 py-2.5 bg-dv-surface hover:bg-dv-surface-hover text-dv-text border border-dv-border rounded-lg transition-colors"
        >
          {t('browse.actions.clear_all')}
        </button>
      </div>

      {/* Confirmation dialog */}
      <Dialog.Root open={confirmOpen} onOpenChange={setConfirmOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/50" />
          <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-dv-surface rounded-xl border border-dv-border p-6 w-[420px]">
            <div className="flex items-center gap-3 mb-4">
              <AlertTriangle size={24} className="text-dv-warning" />
              <Dialog.Title className="text-lg font-semibold text-dv-text">
                {t('plan.confirm_title')}
              </Dialog.Title>
            </div>
            <Dialog.Description className="text-sm text-dv-text-muted mb-6">
              {t('plan.confirm_message', { count: summary.delete_count })}
            </Dialog.Description>
            <div className="flex justify-end gap-3">
              <Dialog.Close asChild>
                <button className="px-4 py-2 bg-dv-surface hover:bg-dv-surface-hover text-dv-text border border-dv-border rounded-lg transition-colors">
                  {t('plan.confirm_cancel')}
                </button>
              </Dialog.Close>
              <button
                onClick={handleExecute}
                className="px-4 py-2 bg-dv-danger hover:bg-red-600 text-white rounded-lg transition-colors"
              >
                {t('plan.confirm_execute')}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  )
}
