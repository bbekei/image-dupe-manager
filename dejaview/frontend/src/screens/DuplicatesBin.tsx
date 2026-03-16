import { useEffect, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { Trash2, RotateCcw, AlertTriangle } from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import { differenceInDays } from 'date-fns'
import { callBackend } from '../hooks/usePyBridge.ts'
import { useScanStore } from '../stores/useScanStore.ts'
import type { BinItem } from '../types/api.ts'

export function DuplicatesBin() {
  const { t } = useTranslation()
  const { sessionId } = useScanStore()
  const [items, setItems] = useState<BinItem[]>([])
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [confirmPurge, setConfirmPurge] = useState(false)
  const [confirmEmptyBin, setConfirmEmptyBin] = useState(false)

  const loadItems = useCallback(async () => {
    if (!sessionId) return
    setLoading(true)
    try {
      const result = await callBackend<BinItem[]>('get_bin_items', sessionId)
      setItems(result)
    } catch {
      // handle error
    } finally {
      setLoading(false)
    }
  }, [sessionId])

  useEffect(() => { loadItems() }, [loadItems])

  const handleRestore = async (id: number) => {
    try {
      await callBackend('restore_from_bin', id)
      loadItems()
    } catch {
      // handle error
    }
  }

  const handlePermanentDelete = async () => {
    if (selected.size === 0) return
    try {
      await callBackend('permanent_delete', Array.from(selected))
      setSelected(new Set())
      loadItems()
    } catch {
      // handle error
    }
  }

  const handleEmptyBin = async () => {
    setConfirmEmptyBin(false)
    try {
      await callBackend('permanent_delete', items.map((i) => i.id))
      setSelected(new Set())
      loadItems()
    } catch {
      // handle error
    }
  }

  const handlePurgeExpired = async () => {
    setConfirmPurge(false)
    try {
      await callBackend('purge_expired')
      loadItems()
    } catch {
      // handle error
    }
  }

  const toggleSelect = (id: number) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  if (loading) {
    return <div className="text-dv-text-muted p-8 text-center">{t('common.loading')}</div>
  }

  return (
    <div className="max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-dv-text">{t('bin.title')}</h1>
          <p className="text-sm text-dv-text-muted mt-1">
            {t('bin.items', { count: items.length })}
          </p>
        </div>
        <div className="flex gap-2">
          {selected.size > 0 && (
            <button
              onClick={handlePermanentDelete}
              className="flex items-center gap-2 px-4 py-2 bg-dv-danger hover:bg-red-600 text-white rounded-lg text-sm transition-colors"
            >
              <Trash2 size={14} />
              {t('bin.permanent_delete')} ({selected.size})
            </button>
          )}
          {items.length > 0 && (
            <button
              onClick={() => setConfirmEmptyBin(true)}
              className="flex items-center gap-2 px-4 py-2 bg-dv-danger hover:bg-red-600 text-white rounded-lg text-sm transition-colors"
            >
              <Trash2 size={14} />
              {t('bin.empty_bin')}
            </button>
          )}
          <button
            onClick={() => setConfirmPurge(true)}
            className="flex items-center gap-2 px-4 py-2 bg-dv-surface hover:bg-dv-surface-hover text-dv-text border border-dv-border rounded-lg text-sm transition-colors"
          >
            {t('bin.purge_expired')}
          </button>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 text-dv-text-muted gap-4">
          <Trash2 size={48} />
          <p>{t('bin.empty')}</p>
        </div>
      ) : (
        <div className="space-y-2">
          {items.map((item) => {
            const daysLeft = differenceInDays(new Date(item.expires_at), new Date())
            const expired = daysLeft <= 0

            return (
              <div
                key={item.id}
                className={`bg-dv-surface rounded-lg border p-4 flex items-center gap-4 ${
                  selected.has(item.id) ? 'border-dv-primary' : 'border-dv-border'
                }`}
              >
                <input
                  type="checkbox"
                  checked={selected.has(item.id)}
                  onChange={() => toggleSelect(item.id)}
                  className="shrink-0"
                />
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-dv-text truncate" title={item.original_path}>
                    {item.original_path.split(/[/\\]/).pop()}
                  </div>
                  <div className="text-xs text-dv-text-muted mt-1 truncate">
                    {item.original_path}
                  </div>
                </div>
                <div className="text-xs text-dv-text-muted shrink-0">
                  {expired ? (
                    <span className="text-dv-danger">{t('bin.expired')}</span>
                  ) : (
                    t('bin.expires_in', { days: daysLeft })
                  )}
                </div>
                <button
                  onClick={() => handleRestore(item.id)}
                  className="p-2 bg-dv-bg hover:bg-dv-surface-hover rounded-lg transition-colors"
                  title={t('bin.restore')}
                >
                  <RotateCcw size={16} className="text-dv-text-muted" />
                </button>
              </div>
            )
          })}
        </div>
      )}

      {/* Empty bin confirmation */}
      <Dialog.Root open={confirmEmptyBin} onOpenChange={setConfirmEmptyBin}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/50" />
          <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-dv-surface rounded-xl border border-dv-border p-6 w-105">
            <div className="flex items-center gap-3 mb-4">
              <AlertTriangle size={24} className="text-dv-warning" />
              <Dialog.Title className="text-lg font-semibold text-dv-text">
                {t('bin.empty_bin')}
              </Dialog.Title>
            </div>
            <Dialog.Description className="text-sm text-dv-text-muted mb-6">
              {t('bin.confirm_empty_bin', { count: items.length })}
            </Dialog.Description>
            <div className="flex justify-end gap-3">
              <Dialog.Close asChild>
                <button className="px-4 py-2 bg-dv-surface hover:bg-dv-surface-hover text-dv-text border border-dv-border rounded-lg">
                  {t('common.cancel')}
                </button>
              </Dialog.Close>
              <button
                onClick={handleEmptyBin}
                className="px-4 py-2 bg-dv-danger hover:bg-red-600 text-white rounded-lg"
              >
                {t('common.confirm')}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      {/* Purge confirmation */}
      <Dialog.Root open={confirmPurge} onOpenChange={setConfirmPurge}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 bg-black/50" />
          <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 bg-dv-surface rounded-xl border border-dv-border p-6 w-[420px]">
            <div className="flex items-center gap-3 mb-4">
              <AlertTriangle size={24} className="text-dv-warning" />
              <Dialog.Title className="text-lg font-semibold text-dv-text">
                {t('bin.purge_expired')}
              </Dialog.Title>
            </div>
            <Dialog.Description className="text-sm text-dv-text-muted mb-6">
              {t('bin.confirm_purge')}
            </Dialog.Description>
            <div className="flex justify-end gap-3">
              <Dialog.Close asChild>
                <button className="px-4 py-2 bg-dv-surface hover:bg-dv-surface-hover text-dv-text border border-dv-border rounded-lg">
                  {t('common.cancel')}
                </button>
              </Dialog.Close>
              <button
                onClick={handlePurgeExpired}
                className="px-4 py-2 bg-dv-danger hover:bg-red-600 text-white rounded-lg"
              >
                {t('common.confirm')}
              </button>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  )
}
