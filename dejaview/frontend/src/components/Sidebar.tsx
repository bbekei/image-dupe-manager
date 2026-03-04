import { NavLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  LayoutDashboard,
  Search,
  ClipboardList,
  Play,
  Images,
  Trash2,
  Users,
  MessageSquare,
  Settings,
} from 'lucide-react'

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'nav.dashboard' },
  { to: '/browse', icon: Search, label: 'nav.browse' },
  { to: '/plan', icon: ClipboardList, label: 'nav.plan' },
  { to: '/execute', icon: Play, label: 'nav.execute' },
  { to: '/similarity', icon: Images, label: 'nav.similarity' },
  { to: '/bin', icon: Trash2, label: 'nav.bin' },
  { to: '/family', icon: Users, label: 'nav.family' },
  { to: '/requests', icon: MessageSquare, label: 'nav.requests' },
  { to: '/settings', icon: Settings, label: 'nav.settings' },
] as const

export function Sidebar() {
  const { t } = useTranslation()

  return (
    <nav className="flex flex-col w-56 h-full bg-dv-sidebar border-r border-dv-border shrink-0">
      <div className="flex items-center gap-2 px-4 py-5 border-b border-dv-border">
        <div className="w-8 h-8 rounded-lg bg-dv-primary flex items-center justify-center text-white font-bold text-sm">
          DV
        </div>
        <span className="text-dv-text font-semibold text-lg">DejaView</span>
      </div>

      <div className="flex-1 py-2 overflow-y-auto">
        {navItems.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-2.5 mx-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-dv-primary text-white'
                  : 'text-dv-text-muted hover:bg-dv-surface-hover hover:text-dv-text'
              }`
            }
          >
            <Icon size={18} />
            <span>{t(label)}</span>
          </NavLink>
        ))}
      </div>

      <div className="px-4 py-3 border-t border-dv-border text-xs text-dv-text-muted">
        DejaView v2.0
      </div>
    </nav>
  )
}
