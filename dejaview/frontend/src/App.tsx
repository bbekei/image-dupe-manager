import { HashRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout.tsx'
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

export default function App() {
  return (
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
  )
}
