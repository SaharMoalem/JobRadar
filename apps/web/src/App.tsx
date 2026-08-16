import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'

import { AppShell } from './components/AppShell.tsx'
import { AlertsDigestPage } from './pages/AlertsDigestPage.tsx'
import { DraftsPage } from './pages/DraftsPage.tsx'
import { NotFoundPage } from './pages/NotFoundPage.tsx'
import { NotificationsPage } from './pages/NotificationsPage.tsx'
import { OpportunitiesPage } from './pages/OpportunitiesPage.tsx'
import { SourcesPage } from './pages/SourcesPage.tsx'
import { TrackerPage } from './pages/TrackerPage.tsx'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Navigate to="/sources" replace />} />
          <Route path="sources" element={<SourcesPage />} />
          <Route path="opportunities" element={<OpportunitiesPage />} />
          <Route path="tracker" element={<TrackerPage />} />
          <Route path="drafts" element={<DraftsPage />} />
          <Route path="alerts" element={<AlertsDigestPage />} />
          <Route path="notifications" element={<NotificationsPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
