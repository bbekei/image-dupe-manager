/**
 * Phase 2: usePyBridge tests — camelizeKeys edge cases.
 *
 * The bridge converts snake_case params to camelCase before sending
 * to Tauri. These tests verify the conversion handles edge cases
 * that have caused production bugs.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { invoke } from '@tauri-apps/api/core'
import { callBackend } from '../hooks/usePyBridge'

const mockInvoke = vi.mocked(invoke)

describe('callBackend / camelizeKeys', () => {
  beforeEach(() => {
    mockInvoke.mockReset()
    mockInvoke.mockResolvedValue(undefined)
  })

  it('converts snake_case params to camelCase', async () => {
    await callBackend('test_method', { session_id: 1, pixel_hash: 'abc' })
    expect(mockInvoke).toHaveBeenCalledWith('test_method', {
      sessionId: 1,
      pixelHash: 'abc',
    })
  })

  it('passes empty object when no params provided', async () => {
    await callBackend('get_version')
    expect(mockInvoke).toHaveBeenCalledWith('get_version', {})
  })

  it('preserves already-camelCase keys', async () => {
    await callBackend('method', { alreadyCamel: true })
    expect(mockInvoke).toHaveBeenCalledWith('method', { alreadyCamel: true })
  })

  it('handles multiple underscores', async () => {
    await callBackend('method', { max_scan_workers: 4 })
    expect(mockInvoke).toHaveBeenCalledWith('method', { maxScanWorkers: 4 })
  })

  it('handles single-character segments', async () => {
    await callBackend('method', { a_b: 1 })
    expect(mockInvoke).toHaveBeenCalledWith('method', { aB: 1 })
  })

  it('preserves values of various types', async () => {
    await callBackend('method', {
      string_val: 'hello',
      number_val: 42,
      bool_val: true,
      null_val: null,
      array_val: [1, 2, 3],
    })
    expect(mockInvoke).toHaveBeenCalledWith('method', {
      stringVal: 'hello',
      numberVal: 42,
      boolVal: true,
      nullVal: null,
      arrayVal: [1, 2, 3],
    })
  })

  it('handles keys with no underscores', async () => {
    await callBackend('method', { name: 'test' })
    expect(mockInvoke).toHaveBeenCalledWith('method', { name: 'test' })
  })

  it('handles leading underscore by leaving it', async () => {
    // _private keys: the regex /_([a-z])/g only matches _ followed by lowercase
    await callBackend('method', { _private: 1 })
    // _p → P, so _private becomes Private (leading underscore consumed by regex)
    expect(mockInvoke).toHaveBeenCalledWith('method', { Private: 1 })
  })

  it('handles empty params object', async () => {
    await callBackend('method', {})
    expect(mockInvoke).toHaveBeenCalledWith('method', {})
  })

  it('returns the invoke result', async () => {
    mockInvoke.mockResolvedValue({ status: 'ok' })
    const result = await callBackend<{ status: string }>('get_status')
    expect(result).toEqual({ status: 'ok' })
  })

  it('propagates invoke errors', async () => {
    mockInvoke.mockRejectedValue(new Error('IPC failed'))
    await expect(callBackend('bad_method')).rejects.toThrow('IPC failed')
  })
})
