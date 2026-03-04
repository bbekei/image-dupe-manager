import { create } from 'zustand'
import type { AppConfig } from '../types/api.ts'

interface SettingsState {
  config: AppConfig | null
  loaded: boolean

  setConfig: (config: AppConfig) => void
  updateConfig: (key: keyof AppConfig, value: string | number | boolean) => void
}

export const useSettingsStore = create<SettingsState>((set) => ({
  config: null,
  loaded: false,

  setConfig: (config) => set({ config, loaded: true }),
  updateConfig: (key, value) =>
    set((s) => ({
      config: s.config ? { ...s.config, [key]: value } : null,
    })),
}))
