/**
 * Hook for communicating with the Python sidecar via Tauri IPC.
 * Replaces the pywebview bridge with Tauri invoke() / listen().
 */

import { useEffect, useRef } from 'react'
import { invoke } from '@tauri-apps/api/core'
import { listen } from '@tauri-apps/api/event'

/** Convert snake_case key to camelCase. */
function toCamel(s: string): string {
  return s.replace(/_([a-z])/g, (_, c: string) => c.toUpperCase())
}

/** Recursively convert all object keys to camelCase (Tauri v2 default). */
function camelizeKeys(obj: Record<string, unknown>): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(obj).map(([k, v]) => [toCamel(k), v]),
  )
}

/**
 * Call a Tauri command (backed by Python sidecar in Step 6).
 * Returns a Promise resolving with the result.
 */
export async function callBackend<T>(
  method: string,
  params?: Record<string, unknown>,
): Promise<T> {
  return invoke<T>(method, params ? camelizeKeys(params) : {})
}

/**
 * Hook to listen for Tauri events emitted by the sidecar.
 * Automatically cleans up the listener on unmount.
 */
export function useBackendEvent<T = unknown>(
  eventName: string,
  handler: (payload: T) => void,
): void {
  const handlerRef = useRef(handler)
  handlerRef.current = handler

  useEffect(() => {
    let unlisten: (() => void) | undefined

    listen<T>(eventName, (event) => {
      handlerRef.current(event.payload)
    }).then((fn) => {
      unlisten = fn
    })

    return () => {
      unlisten?.()
    }
  }, [eventName])
}

/**
 * Hook that fires the callback immediately — Tauri commands are
 * available as soon as the webview loads (no readiness event needed).
 */
export function usePyBridgeReady(callback: () => void): void {
  const callbackRef = useRef(callback)
  callbackRef.current = callback

  useEffect(() => {
    callbackRef.current()
  }, [])
}

/**
 * Hook for scan progress events.
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

  useBackendEvent<{ current: number; total: number; phase: string }>(
    'scan:progress',
    (payload) => {
      cbRef.current.onProgress?.(payload.current, payload.total, payload.phase)
    },
  )

  useBackendEvent<{ status: string; message: string }>(
    'scan:status',
    (payload) => {
      cbRef.current.onStatus?.(payload.status, payload.message)
      if (payload.status === 'complete') cbRef.current.onComplete?.()
    },
  )

  useBackendEvent<{ path: string; message: string }>(
    'scan:error',
    (payload) => {
      cbRef.current.onError?.(payload.path, payload.message)
    },
  )

  useBackendEvent<{ pixel_hash: string; count: number }>(
    'scan:duplicate_found',
    (payload) => {
      cbRef.current.onDuplicateFound?.(payload.pixel_hash, payload.count)
    },
  )

  useBackendEvent<{ current: number; total: number }>(
    'scan:similarity_progress',
    (payload) => {
      cbRef.current.onProgress?.(payload.current, payload.total, 'similarity')
    },
  )
}
