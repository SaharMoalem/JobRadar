import { Outlet } from 'react-router-dom'

import { ConnectionStatus } from './ConnectionStatus.tsx'
import { Nav } from './Nav.tsx'

export function AppShell() {
  return (
    <div className="shell">
      <header className="shell-header">
        <div className="brand-block">
          <p className="brand">JobRadar</p>
          <p className="brand-sub">Local job intelligence</p>
        </div>
        <ConnectionStatus />
      </header>
      <Nav />
      <main className="shell-main">
        <Outlet />
      </main>
    </div>
  )
}
