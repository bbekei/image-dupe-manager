/**
 * Phase 2: Zustand store tests — useReviewStore.
 */

import { describe, it, expect, beforeEach } from 'vitest'
import { useReviewStore } from '../stores/useReviewStore'

const mockGroup = (hash: string) => ({
  pixel_hash: hash,
  hash_algorithm: 'xxhash',
  file_count: 2,
  files: [],
})

function getState() {
  return useReviewStore.getState()
}

describe('useReviewStore', () => {
  beforeEach(() => {
    useReviewStore.getState().reset()
  })

  it('starts empty', () => {
    const s = getState()
    expect(s.sessionId).toBeNull()
    expect(s.groups).toEqual([])
    expect(s.totalGroups).toBe(0)
    expect(s.filters).toEqual({})
    expect(s.selectedGroupHash).toBeNull()
    expect(s.planSummary).toBeNull()
    expect(s.loading).toBe(false)
  })

  it('setGroups replaces groups and total', () => {
    const groups = [mockGroup('a'), mockGroup('b')]
    getState().setGroups(groups, 10)
    expect(getState().groups).toHaveLength(2)
    expect(getState().totalGroups).toBe(10)
  })

  it('appendGroups adds to existing groups', () => {
    getState().setGroups([mockGroup('a')], 3)
    getState().appendGroups([mockGroup('b'), mockGroup('c')])
    expect(getState().groups).toHaveLength(3)
  })

  it('setFilters updates filter criteria', () => {
    getState().setFilters({ folder: '/photos', min_size: 1000 })
    expect(getState().filters).toEqual({ folder: '/photos', min_size: 1000 })
  })

  it('setSelectedGroup tracks selection', () => {
    getState().setSelectedGroup('abc123')
    expect(getState().selectedGroupHash).toBe('abc123')
    getState().setSelectedGroup(null)
    expect(getState().selectedGroupHash).toBeNull()
  })

  it('setPlanSummary stores plan', () => {
    const summary = { keep_count: 5, delete_count: 3, ignore_count: 0, total_size_bytes: 1024, actions: [] }
    getState().setPlanSummary(summary)
    expect(getState().planSummary).toEqual(summary)
  })

  it('reset clears all state', () => {
    getState().setSessionId(1)
    getState().setGroups([mockGroup('a')], 5)
    getState().setFilters({ folder: '/x' })
    getState().setLoading(true)

    getState().reset()

    expect(getState().sessionId).toBeNull()
    expect(getState().groups).toEqual([])
    expect(getState().totalGroups).toBe(0)
    expect(getState().loading).toBe(false)
  })
})
