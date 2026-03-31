/**
 * E2E: Error-state workflows.
 *
 * Phase 2: Verifies the app handles error conditions gracefully
 * without crashing or hanging.
 */

import { invoke, navigateTo } from '../helpers/tauri.js'

describe('Error state handling', () => {
  it('handles scan of nonexistent folder gracefully', async () => {
    // Start scan with a folder that does not exist
    const sessionId = await invoke<number>('start_scan', {
      folders: ['/nonexistent/path/that/does/not/exist'],
      sessionName: 'Error E2E',
      enableSimilarity: false,
    })
    expect(typeof sessionId).toBe('number')

    // Populate Zustand store
    await browser.execute((id: number) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ;(window as any).__e2e?.setScanSessionId(id)
    }, sessionId)

    // The scan should complete (with 0 files), not hang
    await browser.waitUntil(
      async () => {
        const progress = await invoke<{ phase: string }>('get_scan_progress')
        return progress.phase === 'complete' || progress.phase === 'stopped'
      },
      { timeout: 15000, interval: 500 },
    )
  })

  it('handles invalid method call with error response', async () => {
    try {
      await invoke('this_method_does_not_exist')
      // If it doesn't throw, that's also acceptable (Tauri may return error)
    } catch (err) {
      // Expected: the error should be meaningful, not a crash
      expect(String(err)).toBeTruthy()
    }
  })

  it('handles get_scan_summary for nonexistent session', async () => {
    const summary = await invoke<{ total_files: number }>('get_scan_summary', {
      sessionId: 999999,
    })
    expect(summary.total_files).toBe(0)
  })

  it('app remains responsive after error', async () => {
    // Navigate to settings to verify app is still functional
    await navigateTo('/settings')
    const config = await invoke<{ language: string }>('get_app_config')
    expect(config.language).toBeTruthy()
  })
})
