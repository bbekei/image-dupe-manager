/**
 * Invoke a Tauri command from within the WebView.
 * Uses browser.executeAsync so we can await the Promise.
 */
export async function invoke<T>(command: string, args: Record<string, unknown> = {}): Promise<T> {
  const result = await browser.executeAsync((cmd, a, done) => {
    // @ts-ignore — __TAURI_INTERNALS__ is the Tauri v2 IPC object
    window.__TAURI_INTERNALS__.invoke(cmd, a).then(done).catch((err: unknown) => done({ __error: String(err) }))
  }, command, args)
  if (result && typeof result === 'object' && '__error' in (result as object)) {
    throw new Error(`invoke '${command}' failed: ${(result as { __error: string }).__error}`)
  }
  return result as T
}

/**
 * Navigate to a hash route by clicking the sidebar NavLink.
 * Clicking the anchor is more reliable than hash assignment because React Router
 * listens to click events, not just hashchange, in some environments.
 */
export async function navigateTo(route: string): Promise<void> {
  // HashRouter renders NavLink as <a href="#/route">
  const link = await $(`a[href="#${route}"]`)
  if (await link.isExisting()) {
    await link.click()
  } else {
    // Fallback: direct hash assignment
    await browser.execute((h) => { window.location.hash = h }, route)
  }
  await browser.waitUntil(
    async () => {
      const url = await browser.getUrl()
      return url.includes('#' + route)
    },
    { timeout: 5000, timeoutMsg: `Navigation to ${route} did not complete` },
  )
  // Allow React Router and components to finish rendering
  await browser.pause(1500)
}

/**
 * Poll until condition is true or timeout is reached.
 */
export async function waitUntil(
  condition: () => Promise<boolean>,
  { timeout = 60000, interval = 1000, message = 'Condition not met' } = {},
): Promise<void> {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    if (await condition()) return
    await new Promise((r) => setTimeout(r, interval))
  }
  throw new Error(`Timeout: ${message}`)
}

/**
 * Wait for scan to reach the 'complete' phase by polling get_scan_progress.
 */
export async function waitForScanComplete(timeoutMs = 60000): Promise<void> {
  await waitUntil(
    async () => {
      const progress = await invoke<{ phase: string }>('get_scan_progress')
      return progress.phase === 'complete'
    },
    { timeout: timeoutMs, interval: 500, message: 'Scan did not complete' },
  )
}

/**
 * Wait for execution to complete by watching for the exec:complete event.
 * We poll get_scan_progress is not useful here — instead wait for the
 * "View Duplicates Bin" button to appear (data-testid="btn-view-bin").
 */
export async function waitForExecutionComplete(timeoutMs = 60000): Promise<void> {
  await $('[data-testid="execution-complete"]').waitForDisplayed({ timeout: timeoutMs })
}
