/**
 * Phase 2: Zustand store tests — useSettingsStore.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useSettingsStore } from '../stores/useSettingsStore'

const mockConfig = () => ({
  language: 'auto',
  theme: 'system',
  max_scan_workers: 4,
  perf_logging: false,
  scan_delay_ms: 0,
})

function getState() {
  return useSettingsStore.getState()
}

describe('useSettingsStore', () => {
  beforeEach(() => {
    useSettingsStore.setState({ config: null, loaded: false })
  })

  it('starts unloaded with null config', () => {
    expect(getState().config).toBeNull()
    expect(getState().loaded).toBe(false)
  })

  it('setConfig stores config and marks loaded', () => {
    getState().setConfig(mockConfig())
    expect(getState().config).toEqual(mockConfig())
    expect(getState().loaded).toBe(true)
  })

  it('updateConfig patches a single key', () => {
    getState().setConfig(mockConfig())
    getState().updateConfig('theme', 'dark')
    expect(getState().config!.theme).toBe('dark')
    expect(getState().config!.language).toBe('auto')
  })

  it('updateConfig is a no-op when config is null', () => {
    getState().updateConfig('theme', 'dark')
    expect(getState().config).toBeNull()
  })

  it('updateConfig handles numeric values', () => {
    getState().setConfig(mockConfig())
    getState().updateConfig('max_scan_workers', 8)
    expect(getState().config!.max_scan_workers).toBe(8)
  })

  it('updateConfig handles boolean values', () => {
    getState().setConfig(mockConfig())
    getState().updateConfig('perf_logging', true)
    expect(getState().config!.perf_logging).toBe(true)
  })
})
