import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar.tsx'
import { Toaster } from 'sonner'
import { useSettingsStore } from '../stores/useSettingsStore.ts'

export function Layout() {
  const theme = useSettingsStore((s) => s.config?.theme)

  return (
    <div className="flex w-full h-full">
      <Sidebar />
      <main className="flex-1 overflow-y-auto p-6">
        <Outlet />
      </main>
      <Toaster
        position="bottom-right"
        theme={theme === 'light' ? 'light' : 'dark'}
        toastOptions={{
          style: {
            background: 'var(--color-dv-surface)',
            border: '1px solid var(--color-dv-border)',
            color: 'var(--color-dv-text)',
          },
        }}
      />
    </div>
  )
}
