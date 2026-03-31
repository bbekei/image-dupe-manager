/**
 * specs/flow-runner.spec.ts — Generic spec that executes YAML flow definitions.
 *
 * Phase 4: Parses YAML flows and executes them using existing helpers.
 *
 * Guardrail: Reuse existing helpers (startScan, navigateTo, waitForScanComplete).
 * No parallel implementation of app control.
 */

import path from 'path'
import { fileURLToPath } from 'url'
import { loadFlows, type FlowDefinition, type FlowStep } from '../helpers/flow-parser.js'
import { invoke, navigateTo, startScan, waitForScanComplete, waitForExecutionComplete } from '../helpers/tauri.js'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const flowsDir = path.resolve(__dirname, '../flows')

// Determine suite/flow from env (set by wdio.local.conf.ts)
const suite = process.env.DEJAVIEW_TEST_SUITE ?? 'all'
const specificFlow = process.env.DEJAVIEW_TEST_FLOW

function resolveFilter(): { mode?: 'smoke' | 'long-running'; file?: string } {
  if (specificFlow) return { file: specificFlow }
  if (suite === 'smoke') return { mode: 'smoke' }
  if (suite === 'long-running') return { mode: 'long-running' }
  return {}
}

const flows = loadFlows(flowsDir, resolveFilter())

if (flows.length === 0) {
  describe('Flow runner', () => {
    it('skips — no flow files found matching filter', () => {
      console.log(`No flows found in ${flowsDir} for suite="${suite}", flow="${specificFlow ?? 'none'}"`)
    })
  })
} else {
  for (const flow of flows) {
    // Separate restore_all from regular steps — it MUST run even if tests fail
    const regularSteps = flow.steps.filter(s => s.action !== 'restore_all')
    const hasRestore = flow.steps.some(s => s.action === 'restore_all')

    describe(`Flow: ${flow.name}`, function () {
      // Set timeout from flow definition
      this.timeout(flow.timeout)

      for (let i = 0; i < regularSteps.length; i++) {
        const step = regularSteps[i]
        it(`Step ${i + 1}: ${step.action}`, async () => {
          await executeStep(step)
        })
      }

      // SAFETY: restore_all runs in after() hook — guaranteed even if tests fail.
      // This prevents permanent deletion of user files.
      if (hasRestore) {
        after(async function () {
          this.timeout(60000)
          console.log('SAFETY: Running restore_all to recover soft-deleted files...')
          try {
            await executeRestoreAll()
            console.log('SAFETY: All files restored successfully.')
          } catch (err) {
            console.error('SAFETY: restore_all FAILED — files may still be in bin!', err)
            // Don't throw — after() failure shouldn't mask the real test failure
          }
        })
      }
    })
  }
}

// ── Step execution ──────────────────────────────────────────────────────────

async function executeStep(step: FlowStep): Promise<void> {
  switch (step.action) {
    case 'scan':
      return executeScan(step)
    case 'apply_preset':
      return executeApplyPreset(step)
    case 'execute':
      return executeExecute(step)
    case 'view_duplicates':
      return executeViewDuplicates()
    case 'view_similarity':
      return executeViewSimilarity()
    case 'restore_all':
      return executeRestoreAll()
    case 'verify_settings':
      return executeVerifySettings(step)
    default:
      throw new Error(`Unknown flow action: ${(step as { action: string }).action}`)
  }
}

async function executeScan(step: Extract<FlowStep, { action: 'scan' }>): Promise<void> {
  // Expand ~ in folder paths
  const folders = step.folders.map(f =>
    f.startsWith('~/') ? path.join(process.env.HOME ?? '', f.slice(2)) : f
  )

  const sessionId = await startScan(folders, step.session_name, step.enable_similarity ?? false)
  expect(typeof sessionId).toBe('number')

  const timeoutMs = step.expect?.completes_without_hang ? 300000 : 120000
  await waitForScanComplete(timeoutMs)

  if (step.expect?.min_duplicates != null) {
    const summary = await invoke<{ total_duplicates: number }>('get_scan_summary', {
      sessionId,
    })
    expect(summary.total_duplicates).toBeGreaterThanOrEqual(step.expect.min_duplicates)
  }

  if (step.expect?.min_files_scanned != null) {
    const summary = await invoke<{ total_files: number }>('get_scan_summary', {
      sessionId,
    })
    expect(summary.total_files).toBeGreaterThanOrEqual(step.expect.min_files_scanned)
  }
}

async function executeApplyPreset(step: Extract<FlowStep, { action: 'apply_preset' }>): Promise<void> {
  await navigateTo('/browse')

  // Apply preset via IPC (more reliable than UI clicks for local flows)
  const sessions = await invoke<Array<{ id: number }>>('get_sessions')
  const sessionId = sessions[0]?.id
  if (sessionId == null) throw new Error('No session found for apply_preset')

  const presetMap: Record<string, string> = {
    keep_largest: 'KEEP_LARGEST_FILE',
    keep_newest: 'KEEP_NEWEST',
    keep_oldest: 'KEEP_OLDEST',
    keep_shortest_path: 'KEEP_SHORTEST_PATH',
    keep_highest_resolution: 'KEEP_HIGHEST_RESOLUTION',
  }

  const preset = presetMap[step.preset] ?? step.preset
  await invoke('apply_selection_preset', { sessionId, preset })
}

async function executeExecute(step: Extract<FlowStep, { action: 'execute' }>): Promise<void> {
  const sessions = await invoke<Array<{ id: number }>>('get_sessions')
  const sessionId = sessions[0]?.id
  if (sessionId == null) throw new Error('No session found for execute')

  await invoke('execute_plan', { sessionId })
  await waitForExecutionComplete(120000)

  if (step.expect?.bin_items_min != null) {
    const items = await invoke<Array<{ id: number }>>('get_bin_items', { sessionId })
    expect(items.map(i => i.id).length).toBeGreaterThanOrEqual(step.expect.bin_items_min)
  }
}

async function executeViewDuplicates(): Promise<void> {
  await navigateTo('/browse')
  await browser.pause(2000)

  // Verify duplicate groups list is rendered
  const groupsList = await $('[data-testid="duplicate-groups-list"]')
  await groupsList.waitForDisplayed({ timeout: 10000 })

  // Click the first duplicate group to show its files
  const firstGroup = await browser.execute(() => {
    const list = document.querySelector('[data-testid="duplicate-groups-list"]')
    const btn = list?.querySelector('button')
    if (btn) { btn.click(); return true }
    return false
  })
  expect(firstGroup).toBe(true)

  // Wait for the detail panel to load with file thumbnails
  await browser.pause(2000)

  // Verify at least 2 files are shown (it's a duplicate group)
  const fileCount = await browser.execute(() => {
    // File cards have thumbnail images in the detail panel
    const images = document.querySelectorAll('img[src*="data:image"], img[src*="thumbnail"], img[alt]')
    return images.length
  })
  expect(fileCount).toBeGreaterThanOrEqual(2)
}

async function executeViewSimilarity(): Promise<void> {
  await navigateTo('/similarity')
  await browser.pause(3000)

  // Verify the similarity screen rendered by checking for the heading
  const hasHeading = await browser.execute(() =>
    !!document.querySelector('h1')
  )
  expect(hasHeading).toBe(true)
}

async function executeRestoreAll(): Promise<void> {
  await navigateTo('/bin')
  await browser.pause(1000)

  // Try all sessions — restore everything in every bin
  const sessions = await invoke<Array<{ id: number }>>('get_sessions')
  let totalRestored = 0

  for (const session of sessions) {
    const rawItems = await invoke<Array<{ id: number; thumbnail_data?: string }>>('get_bin_items', { sessionId: session.id })
    const items = rawItems.map(({ id }) => ({ id }))
    for (const item of items) {
      await invoke('restore_from_bin', { softDeleteId: item.id })
      totalRestored++
    }
  }

  console.log(`Restored ${totalRestored} files across ${sessions.length} sessions.`)

  // Verify all bins are empty
  for (const session of sessions) {
    const remaining = await invoke<Array<{ id: number }>>('get_bin_items', { sessionId: session.id })
    expect(remaining.map(i => i.id).length).toBe(0)
  }
}

async function executeVerifySettings(step: Extract<FlowStep, { action: 'verify_settings' }>): Promise<void> {
  await navigateTo('/settings')
  const config = await invoke<Record<string, unknown>>('get_app_config')

  for (const [key, expected] of Object.entries(step.expect)) {
    expect(config[key]).toBe(expected)
  }
}
