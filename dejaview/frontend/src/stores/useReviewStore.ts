import { create } from 'zustand'
import type { DuplicateGroup, FilterCriteria, PlanSummary } from '../types/api.ts'

interface ReviewState {
  sessionId: number | null
  groups: DuplicateGroup[]
  totalGroups: number
  filters: FilterCriteria
  selectedGroupHash: string | null
  planSummary: PlanSummary | null
  loading: boolean

  setSessionId: (id: number | null) => void
  setGroups: (groups: DuplicateGroup[], total: number) => void
  appendGroups: (groups: DuplicateGroup[]) => void
  setFilters: (filters: FilterCriteria) => void
  setSelectedGroup: (hash: string | null) => void
  setPlanSummary: (summary: PlanSummary | null) => void
  setLoading: (loading: boolean) => void
  reset: () => void
}

export const useReviewStore = create<ReviewState>((set) => ({
  sessionId: null,
  groups: [],
  totalGroups: 0,
  filters: {},
  selectedGroupHash: null,
  planSummary: null,
  loading: false,

  setSessionId: (id) => set({ sessionId: id }),
  setGroups: (groups, total) => set({ groups, totalGroups: total }),
  appendGroups: (newGroups) =>
    set((s) => ({ groups: [...s.groups, ...newGroups] })),
  setFilters: (filters) => set({ filters }),
  setSelectedGroup: (hash) => set({ selectedGroupHash: hash }),
  setPlanSummary: (summary) => set({ planSummary: summary }),
  setLoading: (loading) => set({ loading }),
  reset: () =>
    set({
      sessionId: null,
      groups: [],
      totalGroups: 0,
      filters: {},
      selectedGroupHash: null,
      planSummary: null,
      loading: false,
    }),
}))
