import { NavLink } from 'react-router-dom'

const LINKS = [
  { to: '/sources', label: 'Sources' },
  { to: '/opportunities', label: 'Opportunities' },
  { to: '/tracker', label: 'Tracker' },
  { to: '/drafts', label: 'Drafts' },
  { to: '/alerts', label: 'Alerts / Digest' },
  { to: '/notifications', label: 'Notifications' },
] as const

export function Nav() {
  return (
    <nav className="nav" aria-label="Primary">
      {LINKS.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}
        >
          {link.label}
        </NavLink>
      ))}
    </nav>
  )
}
