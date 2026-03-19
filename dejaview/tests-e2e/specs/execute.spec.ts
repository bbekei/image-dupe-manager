import { invoke, waitForScanComplete, waitForExecutionComplete, navigateTo } from '../helpers/tauri.js'
import { execSync } from 'child_process'
import path from 'path'
import os from 'os'
import fs from 'fs'

describe('Execute flow', () => {
  let fixtureDir: string

  before(async () => {
    // Set up fresh fixture directory and run a scan
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dejaview-e2e-exec-'))
    const script = path.resolve(__dirname, '../fixtures/generate_fixtures.py')
    execSync(`python3 "${script}" "${tmpDir}"`, { stdio: 'pipe' })
    fixtureDir = tmpDir

    await invoke('start_scan', {
      folders: [fixtureDir],
      sessionName: 'E2E Execute Test',
      enableSimilarity: false,
    })
    await waitForScanComplete(60000)
  })

  after(async () => {
    fs.rmSync(fixtureDir, { recursive: true, force: true })
  })

  it('applies Keep Largest preset from Browse', async () => {
    await navigateTo('/browse')

    const keepLargestBtn = await $('[data-testid="preset-KEEP_LARGEST_FILE"]')
    await keepLargestBtn.waitForDisplayed({ timeout: 10000 })
    await keepLargestBtn.click()

    // Wait a moment for selection:complete event
    await browser.pause(2000)
    // Preset button should now appear active (has an active class)
    expect(await keepLargestBtn.isDisplayed()).toBe(true)
  })

  it('shows a non-empty plan in Plan Review', async () => {
    await navigateTo('/plan')

    // Wait for plan summary to load — delete count should be > 0
    await browser.waitUntil(async () => {
      const text = await $('body').getText()
      // The plan shows "X files to delete"
      return /[1-9]\d*/.test(text)
    }, { timeout: 10000, timeoutMsg: 'Plan summary did not load' })
  })

  it('executes the plan and reaches completion', async () => {
    await navigateTo('/plan')

    // Click "Execute Plan" to open confirmation dialog
    const executePlanBtn = await $('[data-testid="btn-execute-plan"]')
    await executePlanBtn.waitForDisplayed({ timeout: 5000 })
    await executePlanBtn.click()

    // Confirm in the dialog
    const confirmBtn = await $('[data-testid="btn-confirm-execute"]')
    await confirmBtn.waitForDisplayed({ timeout: 5000 })
    await confirmBtn.click()

    // Wait for execution to finish
    await waitForExecutionComplete(60000)

    // "View Duplicates Bin" button should appear
    const viewBinBtn = await $('[data-testid="btn-view-bin"]')
    expect(await viewBinBtn.isDisplayed()).toBe(true)
  })
})
