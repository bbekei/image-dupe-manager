/**
 * Hook for communicating with the Python backend via pywebview bridge.
 * Provides type-safe access to window.pywebview.api.* methods with
 * fallback behavior for development without pywebview.
 */

import { useEffect, useRef } from 'react'
import type { PyWebViewAPI } from '../types/api.ts'

/**
 * Returns the pywebview API object, or null if not available.
 * In dev mode without pywebview, returns null.
 */
export function usePyBridge(): PyWebViewAPI | null {
  return window.pywebview?.api ?? null
}

/**
 * Call a Python backend function via the pywebview bridge.
 * Returns a Promise that resolves with the result.
 * Throws if pywebview is not available.
 */
export async function callBackend<T>(
  method: keyof PyWebViewAPI,
  ...args: unknown[]
): Promise<T> {
  const api = window.pywebview?.api
  if (!api) {
    throw new Error(`pywebview not available — cannot call ${method}`)
  }
  const fn = api[method] as (...a: unknown[]) => Promise<T>
  return fn(...args)
}

/**
 * Hook to listen for CustomEvent dispatched by the Python backend.
 * Automatically cleans up the listener on unmount.
 *
 * @example
 * useBackendEvent('scan:progress', (e) => {
 *   console.log(e.detail.current, e.detail.total)
 * })
 */
export function useBackendEvent<T = unknown>(
  eventName: string,
  handler: (event: CustomEvent<T>) => void,
): void {
  const handlerRef = useRef(handler)
  handlerRef.current = handler

  useEffect(() => {
    const listener = (e: Event) => {
      handlerRef.current(e as CustomEvent<T>)
    }
    window.addEventListener(eventName, listener)
    return () => window.removeEventListener(eventName, listener)
  }, [eventName])
}

/**
 * Hook that waits for pywebview to be ready.
 * pywebview dispatches 'pywebviewready' when the bridge is initialized.
 */
export function usePyBridgeReady(callback: () => void): void {
  const callbackRef = useRef(callback)
  callbackRef.current = callback

  useEffect(() => {
    if (window.pywebview?.api) {
      callbackRef.current()
      return
    }
    const listener = () => callbackRef.current()
    window.addEventListener('pywebviewready', listener)
    return () => window.removeEventListener('pywebviewready', listener)
  }, [])
}

/**
 * Hook for scan progress events. Aggregates multiple event types
 * into a single state update callback.
 */
export function useScanProgress(callbacks: {
  onProgress?: (current: number, total: number, phase: string) => void
  onStatus?: (status: string, message: string) => void
  onDuplicateFound?: (pixelHash: string, count: number) => void
  onComplete?: () => void
  onError?: (path: string, message: string) => void
}): void {
  const cbRef = useRef(callbacks)
  cbRef.current = callbacks

  useBackendEvent('scan:progress', (e: CustomEvent) => {
    cbRef.current.onProgress?.(e.detail.current, e.detail.total, e.detail.phase)
  })

  useBackendEvent('scan:status', (e: CustomEvent) => {
    const { status, message } = e.detail
    cbRef.current.onStatus?.(status, message)
    if (status === 'complete') cbRef.current.onComplete?.()
  })

  useBackendEvent('scan:error', (e: CustomEvent) => {
    cbRef.current.onError?.(e.detail.path, e.detail.message)
  })

  useBackendEvent('scan:duplicate_found', (e: CustomEvent) => {
    cbRef.current.onDuplicateFound?.(e.detail.pixel_hash, e.detail.count)
  })
}

