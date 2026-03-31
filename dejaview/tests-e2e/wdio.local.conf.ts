/**
 * wdio.local.conf.ts — Local-only config for video-recorded smoke & long-running tests.
 *
 * Phase 4: Extends the base CI config with:
 * - Headed mode (watch the app run)
 * - wdio-video-reporter for MP4 recordings
 * - Release binary path via DEJAVIEW_BINARY_PATH env var
 * - Longer timeouts for long-running flows
 * - Flow-based test specs only (flow-runner.spec.ts)
 *
 * Guardrail: This config never runs in GitHub Actions.
 *
 * Usage:
 *   DEJAVIEW_BINARY_PATH=/path/to/installed/app npm run test:local
 *   DEJAVIEW_BINARY_PATH=/path/to/installed/app npm run test:local:smoke
 *   DEJAVIEW_BINARY_PATH=/path/to/installed/app npm run test:local:long
 */

import { spawn, type ChildProcess } from 'child_process'
import path from 'path'
import fs from 'fs'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// Release binary — must be set for local tests
const APP_BINARY = process.env.DEJAVIEW_BINARY_PATH
if (!APP_BINARY) {
  console.error('ERROR: DEJAVIEW_BINARY_PATH must be set to the installed app binary.')
  console.error('Example: DEJAVIEW_BINARY_PATH=/usr/local/bin/dejaview npm run test:local')
  process.exit(1)
}

// Determine which suite to run from --suite flag or DEJAVIEW_TEST_SUITE env
const suite = process.env.DEJAVIEW_TEST_SUITE ?? 'all'

// Determine specific flow file from --flow flag or DEJAVIEW_TEST_FLOW env
const flowFile = process.env.DEJAVIEW_TEST_FLOW

// Recordings directory — each run gets a timestamped subdirectory
const recordingsRoot = path.resolve(__dirname, 'recordings')
const timestamp = new Date().toISOString().replace(/[:.]/g, '-').replace('T', '_').slice(0, 19)
const recordingsDir = path.join(recordingsRoot, timestamp)

let tauriDriver: ChildProcess | undefined

// Video reporter config (wdio-video-reporter)
const videoReporter: [string, Record<string, unknown>] = ['video', {
  saveAllVideos: true,
  videoSlowdownMultiplier: 3,
  outputDir: recordingsDir,
  screenshotIntervalSecs: 1,
  videoRenderTimeout: 30000,
}]

export const config: WebdriverIO.Config = {
  specs: ['./specs/flow-runner.spec.ts'],
  exclude: [],
  maxInstances: 1,

  capabilities: [{
    'tauri:options': {
      application: APP_BINARY,
    },
  }],

  logLevel: 'info',
  bail: 0,
  baseUrl: '',
  waitforTimeout: 60000,
  connectionRetryTimeout: 120000,
  connectionRetryCount: 3,

  hostname: '127.0.0.1',
  port: 4444,
  path: '/',

  framework: 'mocha',
  reporters: ['spec', videoReporter],
  mochaOpts: {
    ui: 'bdd',
    timeout: 600000, // 10 minutes for long-running flows
  },

  onPrepare: async () => {
    // Clean run directories older than 30 days
    if (fs.existsSync(recordingsRoot)) {
      const now = Date.now()
      const thirtyDays = 30 * 24 * 60 * 60 * 1000
      for (const entry of fs.readdirSync(recordingsRoot)) {
        const entryPath = path.join(recordingsRoot, entry)
        const stat = fs.statSync(entryPath)
        if (stat.isDirectory() && now - stat.mtimeMs > thirtyDays) {
          fs.rmSync(entryPath, { recursive: true, force: true })
        }
      }
    }

    // Create timestamped directory for this run
    fs.mkdirSync(recordingsDir, { recursive: true })

    // Set env vars for the flow runner
    process.env.DEJAVIEW_TEST_SUITE = suite
    if (flowFile) {
      process.env.DEJAVIEW_TEST_FLOW = flowFile
    }

    // On Windows, tauri-driver needs msedgedriver.exe (WebView2 is Edge-based).
    // Use the edgedriver npm package to download it on demand.
    const tauriArgs: string[] = []
    if (process.platform === 'win32') {
      const { download } = await import('edgedriver')
      const driverPath = await download()
      console.log(`Edge WebDriver downloaded: ${driverPath}`)
      tauriArgs.push('--native-driver', driverPath)
    }

    tauriDriver = spawn('tauri-driver', tauriArgs, {
      stdio: [null, process.stdout, process.stderr],
      shell: true,
    })
    await new Promise((resolve) => setTimeout(resolve, 3000))
  },

  onComplete: async () => {
    tauriDriver?.kill()
  },
}
