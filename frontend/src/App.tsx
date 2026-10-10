import { Route, Routes } from 'react-router-dom'
import Shell from './components/Shell'
import Overview from './pages/Overview'
import NetworkPage from './pages/NetworkPage'
import Builder from './pages/Builder'
import Results from './pages/Results'
import EntityPage from './pages/EntityPage'
import Mitigation from './pages/Mitigation'
import Methodology from './pages/Methodology'
import Finder from './pages/Finder'

export default function App() {
  return (
    <Routes>
      <Route element={<Shell />}>
        <Route index element={<Overview />} />
        <Route path="finder" element={<Finder />} />
        <Route path="network" element={<NetworkPage />} />
        <Route path="scenario" element={<Builder />} />
        <Route path="results" element={<Results />} />
        <Route path="entity/:id?" element={<EntityPage />} />
        <Route path="mitigation" element={<Mitigation />} />
        <Route path="methodology" element={<Methodology />} />
        <Route path="*" element={<p className="text-sm text-warm">Page not found.</p>} />
      </Route>
    </Routes>
  )
}
