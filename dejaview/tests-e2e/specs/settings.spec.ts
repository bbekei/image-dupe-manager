/**
 * E2E: Settings screen.
 *
 * Phase 2: Verifies settings load, persist, and round-trip through
 * the sidecar without data loss.
 */

import { invoke, navigateTo } from '../helpers/tauri.js'

interface AppConfig {
  language: string
  theme: string
  max_scan_workers: number
  perf_logging: boolean
  scan_delay_ms: number
}

describe('Settings', () => {
  it('navigates to settings page', async () => {
    await navigateTo('/settings')
    const heading = await $('h1, h2, [data-testid="settings-heading"]')
    await heading.waitForDisplayed({ timeout: 5000 })
  })

  it('loads app config via IPC', async () => {
    const config = await invoke<AppConfig>('get_app_config')
    expect(config).toBeDefined()
    expect(typeof config.language).toBe('string')
    expect(typeof config.theme).toBe('string')
    expect(typeof config.max_scan_workers).toBe('number')
    expect(typeof config.perf_logging).toBe('boolean')
    expect(typeof config.scan_delay_ms).toBe('number')
  })

  it('updates a setting and reads it back', async () => {
    // Read current value
    const before = await invoke<AppConfig>('get_app_config')
    const originalTheme = before.theme

    // Toggle theme
    const newTheme = originalTheme === 'dark' ? 'light' : 'dark'
    await invoke('set_app_config', { key: 'theme', value: newTheme })

    // Read back
    const after = await invoke<AppConfig>('get_app_config')
    expect(after.theme).toBe(newTheme)

    // Restore
    await invoke('set_app_config', { key: 'theme', value: originalTheme })
  })

  it('preserves numeric settings', async () => {
    const before = await invoke<AppConfig>('get_app_config')
    const originalWorkers = before.max_scan_workers

    await invoke('set_app_config', { key: 'max_scan_workers', value: 2 })
    const after = await invoke<AppConfig>('get_app_config')
    expect(after.max_scan_workers).toBe(2)

    // Restore
    await invoke('set_app_config', { key: 'max_scan_workers', value: originalWorkers })
  })
})
