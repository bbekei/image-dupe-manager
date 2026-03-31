/**
 * Phase 2: Zustand store tests — useScanStore.
 *
 * Tests phase transitions, concurrent updates, counter resets,
 * and the phaseMap that converts backend status strings.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useScanStore } from '../stores/useScanStore'

function getState() {
  return useScanStore.getState()
}

describe('useScanStore', () => {
  beforeEach(() => {
    useScanStore.getState().reset()
  })

  // ── Initial state ─────────────────────────────────────────────────

  it('starts in idle phase with null sessionId', () => {
    const s = getState()
    expect(s.phase).toBe('idle')
    expect(s.sessionId).toBeNull()
    expect(s.current).toBe(0)
    expect(s.total).toBe(0)
    expect(s.discovered).toBe(0)
    expect(s.duplicatesFound).toBe(0)
    expect(s.error).toBeNull()
    expect(s.scanErrors).toEqual([])
  })

  // ── Phase transitions via setStatus ───────────────────────────────

  it('maps "started" status to discovery phase', () => {
    getState().setStatus('started', 'Scan started')
    expect(getState().phase).toBe('discovery')
  })

  it('maps "hashing" to hashing phase via setProgress', () => {
    getState().setProgress(10, 100, 'hashing')
    expect(getState().phase).toBe('hashing')
    expect(getState().current).toBe(10)
    expect(getState().total).toBe(100)
  })

  it('maps "similarity" to similarity phase', () => {
    getState().setProgress(5, 50, 'similarity')
    expect(getState().phase).toBe('similarity')
  })

  it('maps "complete" status to complete phase', () => {
    getState().setStatus('complete', 'Scan complete')
    expect(getState().phase).toBe('complete')
  })

  it('maps "paused" status to paused phase', () => {
    getState().setStatus('paused', 'Scan paused')
    expect(getState().phase).toBe('paused')
  })

  it('maps "stopped" status to stopped phase', () => {
    getState().setStatus('stopped', 'Scan stopped')
    expect(getState().phase).toBe('stopped')
  })

  it('maps "resumed" status to hashing phase', () => {
    getState().setStatus('resumed', 'Scan resumed')
    expect(getState().phase).toBe('hashing')
  })

  it('maps unknown status to idle', () => {
    getState().setStatus('unknown_status', 'msg')
    expect(getState().phase).toBe('idle')
  })

  // ── "info" status preserves current phase ─────────────────────────

  it('info status does not change current phase', () => {
    getState().setStatus('started', 'Scan started')
    expect(getState().phase).toBe('discovery')

    getState().setStatus('info', 'Probing network...')
    expect(getState().phase).toBe('discovery')
    expect(getState().statusMessage).toBe('Probing network...')
  })

  // ── Counter resets on "started" ───────────────────────────────────

  it('resets counters when a new scan starts', () => {
    // Accumulate some state
    getState().setDiscovered(100)
    getState().incrementDuplicates(50)
    getState().addScanError('/bad', 'err')
    getState().setError('something broke')

    // Start new scan
    getState().setStatus('started', 'Scan started')

    const s = getState()
    expect(s.current).toBe(0)
    expect(s.total).toBe(0)
    expect(s.discovered).toBe(0)
    expect(s.duplicatesFound).toBe(0)
    expect(s.error).toBeNull()
    expect(s.scanErrors).toEqual([])
  })

  // ── Incremental duplicate counting ────────────────────────────────

  it('increments duplicatesFound additively', () => {
    getState().incrementDuplicates(3)
    getState().incrementDuplicates(5)
    expect(getState().duplicatesFound).toBe(8)
  })

  // ── Scan errors accumulate ────────────────────────────────────────

  it('accumulates scan errors', () => {
    getState().addScanError('/path/a', 'permission denied')
    getState().addScanError('/path/b', 'corrupt file')
    expect(getState().scanErrors).toHaveLength(2)
    expect(getState().scanErrors[0]).toEqual({ path: '/path/a', message: 'permission denied' })
  })

  // ── setError transitions to error phase ───────────────────────────

  it('setError sets error phase', () => {
    getState().setError('fatal error')
    expect(getState().phase).toBe('error')
    expect(getState().error).toBe('fatal error')
  })

  it('clearing error resets to idle', () => {
    getState().setError('fatal error')
    getState().setError(null)
    expect(getState().phase).toBe('idle')
    expect(getState().error).toBeNull()
  })

  // ── Full lifecycle sequence ───────────────────────────────────────

  it('supports a full scan lifecycle', () => {
    const s = getState

    s().setSessionId(42)
    expect(s().sessionId).toBe(42)

    s().setStatus('started', 'Scan started')
    expect(s().phase).toBe('discovery')

    s().setDiscovered(100)
    expect(s().discovered).toBe(100)

    s().setProgress(10, 50, 'hashing')
    expect(s().phase).toBe('hashing')

    s().incrementDuplicates(5)
    s().incrementDuplicates(3)
    expect(s().duplicatesFound).toBe(8)

    s().setProgress(5, 20, 'similarity')
    expect(s().phase).toBe('similarity')

    s().setStatus('complete', 'Scan complete')
    expect(s().phase).toBe('complete')
  })

  // ── Concurrent update safety ──────────────────────────────────────
  // Zustand is synchronous, but verify rapid updates don't lose data

  it('handles rapid sequential updates without data loss', () => {
    for (let i = 0; i < 100; i++) {
      getState().incrementDuplicates(1)
    }
    expect(getState().duplicatesFound).toBe(100)
  })

  // ── setProgress with unknown phase defaults to hashing ────────────

  it('setProgress defaults unknown phase to hashing', () => {
    getState().setProgress(1, 10, 'unknown_phase')
    expect(getState().phase).toBe('hashing')
  })
})
