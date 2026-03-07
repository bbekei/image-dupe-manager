import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import type { MigrationStatus } from '../types/api.ts'

interface Props {
  children: React.ReactNode
}

export function MigrationGate({ children }: Props) {
  const { t } = useTranslation()
  const [status, setStatus] = useState<MigrationStatus | null>(null)
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)

  useEffect(() => {
    const check = async () => {
      const api = window.pywebview?.api
      if (!api) return
      try {
        const s = await api.get_migration_status()
        setStatus(s)
        if (!s.needed) setDone(true)
      } catch {
        setDone(true)
      }
    }

    if (window.pywebview?.api) {
      check()
    } else {
      window.addEventListener('pywebviewready', () => check(), { once: true })
    }
  }, [])

  const handleConfirm = async () => {
    setConfirming(true)
    setError(null)
    try {
      const api = window.pywebview?.api
      if (!api) return
      const result = await api.confirm_migration()
      if (result.ok) {
        setDone(true)
      } else {
        setError(result.error ?? t('migration.error', { error: 'Unknown' }))
      }
    } catch (e) {
      setError(String(e))
    } finally {
      setConfirming(false)
    }
  }

  const handleCancel = () => {
    window.close()
  }

  if (done) return <>{children}</>

  if (!status || !status.needed) return <>{children}</>

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-lg w-full mx-4 p-6">
        <h2 className="text-xl font-semibold mb-3 text-gray-900 dark:text-white">
          {t('migration.title')}
        </h2>

        <p className="text-gray-600 dark:text-gray-300 mb-4">
          {t('migration.description')}
        </p>

        {status.breaking_changes.length > 0 && (
          <div className="mb-4">
            <p className="text-amber-600 dark:text-amber-400 font-medium mb-2">
              {t('migration.breaking_warning')}
            </p>
            <ul className="list-disc list-inside text-sm text-gray-600 dark:text-gray-300 space-y-1">
              {status.breaking_changes.map((bc) => (
                <li key={bc.version}>
                  {bc.reason_key ? t(bc.reason_key) : bc.description}
                </li>
              ))}
            </ul>
          </div>
        )}

        {status.backup_path && (
          <p className="text-sm text-gray-500 dark:text-gray-400 mb-4">
            {t('migration.backup_notice', { path: status.backup_path })}
          </p>
        )}

        {error && (
          <p className="text-red-600 dark:text-red-400 text-sm mb-4">{error}</p>
        )}

        <div className="flex justify-end gap-3">
          <button
            onClick={handleCancel}
            className="px-4 py-2 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
          >
            {t('migration.cancel')}
          </button>
          <button
            onClick={handleConfirm}
            disabled={confirming}
            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
          >
            {confirming ? '...' : t('migration.confirm')}
          </button>
        </div>
      </div>
    </div>
  )
}
