import { spawn, type ChildProcess } from 'child_process'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// Path to the compiled Tauri app binary (debug build for speed in CI)
// On Linux: target/debug/app   On Windows: target/debug/app.exe
const APP_BINARY = process.env.TAURI_APP_BINARY
  ?? path.resolve(__dirname, '../src-tauri/target/debug/app')

let tauriDriver: ChildProcess | undefined

export const config: WebdriverIO.Config = {
  specs: ['./specs/**/*.spec.ts'],
  exclude: [],
  maxInstances: 1,

  capabilities: [{
    'tauri:options': {
      application: APP_BINARY,
    },
  }],

  logLevel: 'warn',
  bail: 0,
  baseUrl: '',
  waitforTimeout: 30000,
  connectionRetryTimeout: 120000,
  connectionRetryCount: 3,

  // tauri-driver runs as the WebDriver server
  hostname: '127.0.0.1',
  port: 4444,
  path: '/',

  framework: 'mocha',
  reporters: ['spec'],
  mochaOpts: {
    ui: 'bdd',
    timeout: 120000,
  },

  onPrepare: async () => {
    tauriDriver = spawn('tauri-driver', [], {
      stdio: [null, process.stdout, process.stderr],
    })
    // Give the driver a moment to bind
    await new Promise((resolve) => setTimeout(resolve, 2000))
  },

  onComplete: async () => {
    tauriDriver?.kill()
  },

  before: async () => {
    // Extend default waitFor timeout (WDIO v9 API)
    await browser.setTimeouts({ implicit: 10000 })
  },
}
