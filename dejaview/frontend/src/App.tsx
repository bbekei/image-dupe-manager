import { HashRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout.tsx'
import { MigrationGate } from './components/MigrationGate.tsx'
import i18n from './i18n/index.ts'
import { resolveLanguage } from './i18n/resolveLanguage.ts'
import { Dashboard } from './screens/Dashboard.tsx'
import { BrowseResults } from './screens/BrowseResults.tsx'
import { PlanReview } from './screens/PlanReview.tsx'
import { Execution } from './screens/Execution.tsx'
import { SimilarityReview } from './screens/SimilarityReview.tsx'
import { DuplicatesBin } from './screens/DuplicatesBin.tsx'
import { Family } from './screens/Family.tsx'
import { Requests } from './screens/Requests.tsx'
import { Settings } from './screens/Settings.tsx'
import { Help } from './screens/Help.tsx'
import { callBackend, usePyBridgeReady } from './hooks/usePyBridge.ts'
import type { AppConfig } from './types/api.ts'
import { useScanStore } from './stores/useScanStore.ts'

// Minimal E2E test bridge: lets automation set Zustand store state that would
// normally be populated by UI-driven flows (e.g. after invoking start_scan
// directly via IPC instead of going through the Dashboard scan button).
;(window as unknown as Record<string, unknown>).__e2e = {
  setScanSessionId: (id: number) => useScanStore.getState().setSessionId(id),
}

export function applyTheme(theme: string) {
  if (theme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light')
  } else {
    document.documentElement.removeAttribute('data-theme')
  }
}

export default function App() {
  usePyBridgeReady(() => {
    callBackend<AppConfig>('get_app_config')
      .then((config) => {
        i18n.changeLanguage(resolveLanguage(config.language))
        applyTheme(config.theme)
      })
      .catch(() => {
        // leave i18n at its default
      })
  })

  return (
    <MigrationGate>
      <HashRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route path="/" element={<Dashboard />} />
            <Route path="/browse" element={<BrowseResults />} />
            <Route path="/plan" element={<PlanReview />} />
            <Route path="/execute" element={<Execution />} />
            <Route path="/similarity" element={<SimilarityReview />} />
            <Route path="/bin" element={<DuplicatesBin />} />
            <Route path="/family" element={<Family />} />
            <Route path="/requests" element={<Requests />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/help" element={<Help />} />
          </Route>
        </Routes>
      </HashRouter>
    </MigrationGate>
  )
}
