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

    // Apply preset via Tauri invoke directly for speed
    const sessions = await invoke<Array<{ id: number }>>('get_sessions')
    const sessionId = sessions[0].id
    await invoke('apply_selection_preset', {
      sessionId,
      preset: 'KEEP_LARGEST_FILE',
    })

    // Navigate to plan and execute
    await navigateTo('/plan')
    const executePlanBtn = await $('[data-testid="btn-execute-plan"]')
    await executePlanBtn.waitForDisplayed({ timeout: 10000 })
    await executePlanBtn.click()
    const confirmBtn = await $('[data-testid="btn-confirm-execute"]')
    await confirmBtn.waitForDisplayed({ timeout: 5000 })
    await confirmBtn.click()
    await waitForExecutionComplete(60000)
  })

  after(async () => {
    fs.rmSync(fixtureDir, { recursive: true, force: true })
  })

  it('navigates to the Duplicates Bin and shows items', async () => {
    await navigateTo('/bin')

    const binList = await $('[data-testid="bin-items-list"]')
    await binList.waitForDisplayed({ timeout: 10000 })

    const items = await binList.$$('> *')
    expect(items.length).toBeGreaterThanOrEqual(1)
  })

  it('restores one item from the bin', async () => {
    await navigateTo('/bin')

    const binList = await $('[data-testid="bin-items-list"]')
    await binList.waitForDisplayed({ timeout: 10000 })

    const itemsBefore = await binList.$$('> *')
    const countBefore = itemsBefore.length

    // Click the restore button on the first item
    const firstRestoreBtn = await $('[data-testid^="btn-restore-"]')
    await firstRestoreBtn.waitForDisplayed({ timeout: 5000 })
    await firstRestoreBtn.click()

    // Wait for the list to update
    await browser.pause(1500)

    const itemsAfter = await binList.$$('> *')
    expect(itemsAfter.length).toBe(countBefore - 1)
  })
})
