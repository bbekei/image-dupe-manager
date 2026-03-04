import { create } from 'zustand'

export type ScanPhase = 'idle' | 'discovery' | 'hashing' | 'similarity' | 'complete' | 'paused' | 'stopped' | 'error'

interface ScanState {
  sessionId: number | null
  phase: ScanPhase
  current: number
  total: number
  statusMessage: string
  duplicatesFound: number
  error: string | null

  setSessionId: (id: number | null) => void
  setPhase: (phase: ScanPhase) => void
  setProgress: (current: number, total: number, phase: string) => void
  setStatus: (status: string, message: string) => void
  incrementDuplicates: (count: number) => void
  setError: (error: string | null) => void
  reset: () => void
}

const phaseMap: Record<string, ScanPhase> = {
  discovery: 'discovery',
  hashing: 'hashing',
  similarity: 'similarity',
  complete: 'complete',
  paused: 'paused',
  stopped: 'stopped',
  error: 'error',
  started: 'discovery',
  resumed: 'hashing',
}

export const useScanStore = create<ScanState>((set) => ({
  sessionId: null,
  phase: 'idle',
  current: 0,
  total: 0,
  statusMessage: '',
  duplicatesFound: 0,
  error: null,

  setSessionId: (id) => set({ sessionId: id }),
  setPhase: (phase) => set({ phase }),
  setProgress: (current, total, phase) =>
    set({ current, total, phase: phaseMap[phase] ?? 'hashing' }),
  setStatus: (status, message) =>
    set({ phase: phaseMap[status] ?? 'idle', statusMessage: message }),
  incrementDuplicates: (count) =>
    set((s) => ({ duplicatesFound: s.duplicatesFound + count })),
  setError: (error) => set({ error, phase: error ? 'error' : 'idle' }),
  reset: () =>
    set({
      sessionId: null,
      phase: 'idle',
      current: 0,
      total: 0,
      statusMessage: '',
      duplicatesFound: 0,
      error: null,
    }),
}))
