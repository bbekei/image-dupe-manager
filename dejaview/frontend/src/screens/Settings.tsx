import { useEffect, useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { Info } from 'lucide-react'
import { callBackend } from '../hooks/usePyBridge.ts'
import { useSettingsStore } from '../stores/useSettingsStore.ts'
import type { AppConfig, SyncConfig, RemotePeer } from '../types/api.ts'
import i18n from '../i18n/index.ts'

function extractFolderId(input: string): string {
  const trimmed = input.trim()
  try {
    const url = new URL(trimmed)
    if (url.hostname === 'drive.google.com') {
      const match = url.pathname.match(/\/folders\/([A-Za-z0-9_-]+)/)
      if (match) return match[1]
    }
  } catch {
    // not a URL — treat as raw folder ID
  }
  return trimmed
}

export function Settings() {
  const { t } = useTranslation()
  const { config, setConfig, updateConfig } = useSettingsStore()
  const [loading, setLoading] = useState(true)

  // Sync config state
  const [syncConfig, setSyncConfig] = useState<SyncConfig | null>(null)
  const [syncUsername, setSyncUsername] = useState('')
  const [syncFolderId, setSyncFolderId] = useState('')
  const [syncPrivacy, setSyncPrivacy] = useState('filename')
  const [authenticating, setAuthenticating] = useState(false)
  const [savingSync, setSavingSync] = useState(false)
  const [peers, setPeers] = useState<RemotePeer[]>([])

  const loadConfig = useCallback(async () => {
    setLoading(true)
    try {
      const result = await callBackend<AppConfig>('get_app_config')
      setConfig(result)
    } catch {
      // handle error
    } finally {
      setLoading(false)
    }
  }, [setConfig])

  const loadSyncConfig = useCallback(async () => {
    try {
      const result = await callBackend<SyncConfig>('get_sync_config')
      setSyncConfig(result)
      setSyncUsername(result.local_username)
      setSyncFolderId(result.gdrive_folder_id)
      setSyncPrivacy(result.export_privacy)
    } catch {
      // handle error
    }
  }, [])

  const loadPeers = useCallback(async () => {
    try {
      const result = await callBackend<RemotePeer[]>('get_remote_peers')
      setPeers(result)
    } catch {
      // handle error
    }
  }, [])

  useEffect(() => {
    loadConfig()
    loadSyncConfig()
    loadPeers()
  }, [loadConfig, loadSyncConfig, loadPeers])

  const handleChange = async (key: keyof AppConfig, value: string | number | boolean) => {
    updateConfig(key, value)
    try {
      await callBackend('set_app_config', key, value)
      if (key === 'language') {
        i18n.changeLanguage(value as string)
      }
      toast.success(t('settings.saved'))
    } catch {
      toast.error(t('common.error'))
    }
  }

  const handleAuthenticate = async () => {
    setAuthenticating(true)
    try {
      const result = await callBackend<{ ok: boolean; error?: string }>('authenticate_drive')
      if (result.ok) {
        toast.success(t('settings.auth_success'))
        loadSyncConfig()
      } else {
        toast.error(t('settings.auth_failed', { error: result.error }))
      }
    } catch {
      toast.error(t('common.error'))
    } finally {
      setAuthenticating(false)
    }
  }

  const handleSaveSync = async () => {
    setSavingSync(true)
    try {
      const result = await callBackend<{ ok: boolean; error?: string }>(
        'save_sync_config', syncUsername, syncFolderId, syncPrivacy
      )
      if (result.ok) {
        toast.success(t('settings.sync_saved'))
        loadSyncConfig()
      } else if (result.error === 'invalid_username') {
        toast.error(t('settings.invalid_username'))
      } else if (result.error === 'invalid_folder_id') {
        toast.error(t('settings.invalid_folder_id'))
      }
    } catch {
      toast.error(t('common.error'))
    } finally {
      setSavingSync(false)
    }
  }

  const handleRemovePeer = async (username: string) => {
    try {
      await callBackend('remove_peer', username)
      loadPeers()
    } catch {
      toast.error(t('common.error'))
    }
  }

  if (loading || !config) {
    return <div className="text-dv-text-muted p-8 text-center">{t('common.loading')}</div>
  }

  const syncDirty =
    syncConfig != null && (
      syncUsername !== syncConfig.local_username ||
      syncFolderId !== syncConfig.gdrive_folder_id ||
      syncPrivacy !== syncConfig.export_privacy
    )

  return (
    <div className="max-w-2xl">
      <h1 className="text-2xl font-bold text-dv-text mb-6">{t('settings.title')}</h1>

      <div className="space-y-6">
        {/* Language */}
        <div className="bg-dv-surface rounded-xl border border-dv-border p-5">
          <label className="block text-sm font-medium text-dv-text mb-2">
            {t('settings.language')}
          </label>
          <select
            value={config.language}
            onChange={(e) => handleChange('language', e.target.value)}
            className="w-full bg-dv-bg border border-dv-border rounded-lg px-3 py-2 text-sm text-dv-text"
          >
            <option value="en">English</option>
            <option value="hu">Magyar</option>
            <option value="auto">Auto-detect</option>
          </select>
        </div>

        {/* Theme */}
        <div className="bg-dv-surface rounded-xl border border-dv-border p-5">
          <label className="block text-sm font-medium text-dv-text mb-2">
            {t('settings.theme')}
          </label>
          <select
            value={config.theme}
            onChange={(e) => handleChange('theme', e.target.value)}
            className="w-full bg-dv-bg border border-dv-border rounded-lg px-3 py-2 text-sm text-dv-text"
          >
            <option value="dark">Dark</option>
            <option value="light">Light</option>
          </select>
        </div>

        {/* Max Workers */}
        <div className="bg-dv-surface rounded-xl border border-dv-border p-5">
          <label className="block text-sm font-medium text-dv-text mb-2">
            {t('settings.max_workers')}
          </label>
          <input
            type="number"
            min={1}
            max={16}
            value={config.max_scan_workers}
            onChange={(e) => handleChange('max_scan_workers', parseInt(e.target.value, 10))}
            className="w-full bg-dv-bg border border-dv-border rounded-lg px-3 py-2 text-sm text-dv-text"
          />
        </div>

        {/* Scan Delay */}
        <div className="bg-dv-surface rounded-xl border border-dv-border p-5">
          <label className="block text-sm font-medium text-dv-text mb-2">
            {t('settings.scan_delay')}
          </label>
          <input
            type="number"
            min={0}
            max={5000}
            step={100}
            value={config.scan_delay_ms}
            onChange={(e) => handleChange('scan_delay_ms', parseInt(e.target.value, 10))}
            className="w-full bg-dv-bg border border-dv-border rounded-lg px-3 py-2 text-sm text-dv-text"
          />
          <p className="text-xs text-dv-text-muted mt-1">
            0 = no throttling, higher values reduce CPU usage during scan
          </p>
        </div>

        {/* Perf Logging */}
        <div className="bg-dv-surface rounded-xl border border-dv-border p-5">
          <label className="flex items-center gap-3 cursor-pointer">
            <input
              type="checkbox"
              checked={config.perf_logging}
              onChange={(e) => handleChange('perf_logging', e.target.checked)}
              className="w-4 h-4"
            />
            <span className="text-sm font-medium text-dv-text">
              {t('settings.perf_logging')}
            </span>
          </label>
        </div>

        {/* Google Drive Sync */}
        <div className="bg-dv-surface rounded-xl border border-dv-border p-5 space-y-4">
          <h2 className="text-lg font-semibold text-dv-text">{t('settings.google_drive')}</h2>

          {/* Display Name */}
          <div>
            <label className="block text-sm font-medium text-dv-text mb-1">
              {t('settings.display_name')}
            </label>
            <input
              type="text"
              maxLength={64}
              value={syncUsername}
              onChange={(e) => setSyncUsername(e.target.value)}
              placeholder={t('settings.display_name_placeholder')}
              className="w-full bg-dv-bg border border-dv-border rounded-lg px-3 py-2 text-sm text-dv-text"
            />
            <p className="text-xs text-dv-text-muted mt-1">{t('settings.display_name_hint')}</p>
          </div>

          {/* Google Sign In */}
          <div className="flex items-center gap-3">
            <button
              onClick={handleAuthenticate}
              disabled={authenticating}
              className="px-4 py-2 bg-dv-primary hover:bg-dv-primary-hover text-white rounded-lg text-sm transition-colors disabled:opacity-50"
            >
              {authenticating ? t('settings.signing_in') : t('settings.sign_in_google')}
            </button>
            <span className={`text-sm ${syncConfig?.authenticated ? 'text-green-400' : 'text-dv-text-muted'}`}>
              {syncConfig?.authenticated ? t('settings.signed_in') : t('settings.not_signed_in')}
            </span>
          </div>

          {/* Folder ID */}
          <div>
            <label className="flex items-center gap-1.5 text-sm font-medium text-dv-text mb-1">
              {t('settings.folder_id')}
              <span className="relative group">
                <Info size={14} className="text-dv-text-muted cursor-help" />
                <span className="absolute left-1/2 -translate-x-1/2 bottom-full mb-1.5 px-3 py-1.5 rounded bg-dv-bg border border-dv-border text-xs text-dv-text-muted whitespace-nowrap opacity-0 pointer-events-none group-hover:opacity-100 transition-opacity z-10">
                  {t('settings.folder_id_hint')}
                </span>
              </span>
            </label>
            <input
              type="text"
              value={syncFolderId}
              onChange={(e) => setSyncFolderId(extractFolderId(e.target.value))}
              placeholder={t('settings.folder_id_placeholder')}
              className="w-full bg-dv-bg border border-dv-border rounded-lg px-3 py-2 text-sm text-dv-text"
            />
          </div>

          {/* Privacy Level */}
          <div>
            <label className="block text-sm font-medium text-dv-text mb-1">
              {t('settings.privacy_level')}
            </label>
            <select
              value={syncPrivacy}
              onChange={(e) => setSyncPrivacy(e.target.value)}
              className="w-full bg-dv-bg border border-dv-border rounded-lg px-3 py-2 text-sm text-dv-text"
            >
              <option value="filename">{t('settings.privacy_filename')}</option>
              <option value="hash_only">{t('settings.privacy_hash_only')}</option>
              <option value="full_path">{t('settings.privacy_full_path')}</option>
            </select>
          </div>

          {/* Save Sync Settings */}
          <button
            onClick={handleSaveSync}
            disabled={savingSync || !syncDirty}
            className="px-4 py-2 bg-dv-primary hover:bg-dv-primary-hover text-white rounded-lg text-sm transition-colors disabled:opacity-50"
          >
            {t('settings.save_sync')}
          </button>

          {/* Synced Peers */}
          {peers.length > 0 && (
            <div className="mt-4">
              <h3 className="text-sm font-medium text-dv-text mb-2">{t('family.peers')}</h3>
              <div className="space-y-2">
                {peers.map((peer) => (
                  <div
                    key={peer.id}
                    className="flex items-center justify-between bg-dv-bg border border-dv-border rounded-lg px-3 py-2"
                  >
                    <div className="flex items-center gap-2">
                      <div className="w-7 h-7 rounded-full bg-dv-primary/10 flex items-center justify-center text-dv-primary text-xs font-bold">
                        {peer.username[0].toUpperCase()}
                      </div>
                      <span className="text-sm text-dv-text">{peer.username}</span>
                    </div>
                    <button
                      onClick={() => handleRemovePeer(peer.username)}
                      className="text-xs text-red-400 hover:text-red-300 transition-colors"
                    >
                      {t('common.delete')}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
