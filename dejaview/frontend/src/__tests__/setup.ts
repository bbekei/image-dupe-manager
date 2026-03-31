import '@testing-library/jest-dom/vitest'

// Mock Tauri APIs — tests run outside the Tauri webview
vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}))

vi.mock('@tauri-apps/api/event', () => ({
  listen: vi.fn(() => Promise.resolve(() => {})),
}))
