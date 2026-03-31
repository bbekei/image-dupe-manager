import { startScan, waitForScanComplete, navigateTo, pythonCmd } from '../helpers/tauri.js'
import { execSync } from 'child_process'
import path from 'path'
import os from 'os'
import fs from 'fs'

describe('Scan flow', () => {
  let fixtureDir: string

  before(async () => {
    // Generate synthetic fixture images into a temp dir
    const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'dejaview-e2e-'))
    const script = path.resolve(__dirname, '../fixtures/generate_fixtures.py')
    execSync(`${pythonCmd} "${script}" "${tmpDir}"`, { stdio: 'pipe' })
    fixtureDir = tmpDir
  })

  after(async () => {
    // Clean up fixture dir
    fs.rmSync(fixtureDir, { recursive: true, force: true })
  })

  it('starts a scan and reaches the complete phase', async () => {
    // startScan invokes start_scan and populates the Zustand store session ID
    const sessionId = await startScan([fixtureDir], 'E2E Scan Test')
    expect(typeof sessionId).toBe('number')

    // Wait for the scan-progress panel to show completion
    await waitForScanComplete(60000)

    // "View Results" button should now be visible
    const viewResultsBtn = await $('[data-testid="btn-view-results"]')
    await viewResultsBtn.waitForDisplayed({ timeout: 5000 })
    expect(await viewResultsBtn.isDisplayed()).toBe(true)
  })

  it('shows at least one duplicate group after scan', async () => {
    // Navigate to browse
    await navigateTo('/browse')

    const groupsList = await $('[data-testid="duplicate-groups-list"]')
    await groupsList.waitForDisplayed({ timeout: 10000 })

    // WebKit WebDriver rejects relative '> *' selectors; count via JS instead
    const childCount = await browser.execute(
      (el: Element) => el.childElementCount,
      groupsList,
    )
    expect(childCount).toBeGreaterThanOrEqual(1)
  })
})
