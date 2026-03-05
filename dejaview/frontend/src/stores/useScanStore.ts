import { create } from 'zustand'

export type ScanPhase = 'idle' | 'discovery' | 'hashing' | 'similarity' | 'complete' | 'paused' | 'stopped' | 'error'

interface ScanError {
  path: string
  message: string
}

interface ScanState {
  sessionId: number | null
  phase: ScanPhase
  current: number
  total: number
  discovered: number
  statusMessage: string
  duplicatesFound: number
  error: string | null
  scanErrors: ScanError[]

  setSessionId: (id: number | null) => void
  setPhase: (phase: ScanPhase) => void
  setProgress: (current: number, total: number, phase: string) => void
  setStatus: (status: string, message: string) => void
  setDiscovered: (count: number) => void
  incrementDuplicates: (count: number) => void
  addScanError: (path: string, message: string) => void
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
  // "info" is handled specially in setStatus — not mapped here
}

export const useScanStore = create<ScanState>((set) => ({
  sessionId: null,
  phase: 'idle',
  current: 0,
  total: 0,
  discovered: 0,
  statusMessage: '',
  duplicatesFound: 0,
  error: null,
  scanErrors: [],

  setSessionId: (id) => set({ sessionId: id }),
  setPhase: (phase) => set({ phase }),
  setProgress: (current, total, phase) =>
    set({ current, total, phase: phaseMap[phase] ?? 'hashing' }),
  setStatus: (status, message) =>
    set((s) => ({
      // "info" status messages are informational — keep the current phase
      phase: status === 'info' ? s.phase : (phaseMap[status] ?? 'idle'),
      statusMessage: message,
      // Reset counters when a new scan starts
      ...(status === 'started' ? { current: 0, total: 0, discovered: 0, duplicatesFound: 0, error: null, scanErrors: [] } : {}),
    })),
  setDiscovered: (count) => set({ discovered: count }),
  incrementDuplicates: (count) =>
    set((s) => ({ duplicatesFound: s.duplicatesFound + count })),
  addScanError: (path, message) =>
    set((s) => ({ scanErrors: [...s.scanErrors, { path, message }] })),
  setError: (error) => set({ error, phase: error ? 'error' : 'idle' }),
  reset: () =>
    set({
      sessionId: null,
      phase: 'idle',
      current: 0,
      total: 0,
      discovered: 0,
      statusMessage: '',
      duplicatesFound: 0,
      error: null,
      scanErrors: [],
    }),
}))
