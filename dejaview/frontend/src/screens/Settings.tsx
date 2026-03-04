import { useEffect, useCallback, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'
import { callBackend } from '../hooks/usePyBridge.ts'
import { useSettingsStore } from '../stores/useSettingsStore.ts'
import type { AppConfig } from '../types/api.ts'
import i18n from '../i18n/index.ts'

export function Settings() {
  const { t } = useTranslation()
  const { config, setConfig, updateConfig } = useSettingsStore()
  const [loading, setLoading] = useState(true)

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

  useEffect(() => { loadConfig() }, [loadConfig])

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

  if (loading || !config) {
    return <div className="text-dv-text-muted p-8 text-center">{t('common.loading')}</div>
  }

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
      </div>
    </div>
  )
}
