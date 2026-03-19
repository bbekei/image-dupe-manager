import { startScan, invoke, waitForScanComplete, waitForExecutionComplete, navigateTo } from '../helpers/tauri.js'
import { execSync } from 'child_process'
import path from 'path'
import os from 'os'
import fs from 'fs'

describe('Duplicates Bin flow', () => {
  let fixtureDir: string

  before(async () => {
    // Set up fixture dir, scan, apply preset, and execute so the bin has items
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dejaview-e2e-bin-'))
    const script = path.resolve(__dirname, '../fixtures/generate_fixtures.py')
    execSync(`python3 "${script}" "${tmpDir}"`, { stdio: 'pipe' })
    fixtureDir = tmpDir

    await startScan([fixtureDir], 'E2E Bin Test')
    await waitForScanComplete(60000)

    // Apply preset and execute via IPC directly (avoids UI navigation + exec:complete
    // race condition where the event fires before Execution component mounts)
    const sessions = await invoke<Array<{ id: number }>>('get_sessions')
    const sessionId = sessions[0].id
    await invoke('apply_selection_preset', {
      sessionId,
      preset: 'KEEP_LARGEST_FILE',
    })
    await invoke('execute_plan', { sessionId })
    await waitForExecutionComplete(60000)
  })

  after(async () => {
    fs.rmSync(fixtureDir, { recursive: true, force: true })
  })

  it('navigates to the Duplicates Bin and shows items', async () => {
    await navigateTo('/bin')

    const binList = await $('[data-testid="bin-items-list"]')
    await binList.waitForDisplayed({ timeout: 10000 })

    // WebKit WebDriver rejects relative '> *' selectors; count via JS instead
    const childCount = await browser.execute(
      (el: Element) => el.childElementCount,
      binList,
    )
    expect(childCount).toBeGreaterThanOrEqual(1)
  })

  it('restores one item from the bin', async () => {
    await navigateTo('/bin')

    const binList = await $('[data-testid="bin-items-list"]')
    await binList.waitForDisplayed({ timeout: 10000 })

    const countBefore = await browser.execute(
      (el: Element) => el.childElementCount,
      binList,
    )

    // Click the restore button on the first item
    const firstRestoreBtn = await $('[data-testid^="btn-restore-"]')
    await firstRestoreBtn.waitForDisplayed({ timeout: 5000 })
    await firstRestoreBtn.click()

    // Wait for the list to update
    await browser.pause(1500)

    const countAfter = await browser.execute(
      (el: Element) => el.childElementCount,
      binList,
    )
    expect(countAfter).toBe(countBefore - 1)
  })
})
