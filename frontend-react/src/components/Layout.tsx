import { ReactNode, useState } from 'react'
import { useLocation, Link } from 'react-router-dom'
import { Menu, X, TrendingUp, Wallet, BookOpen, BarChart3, Terminal, LayoutDashboard, Package, Moon, Sun } from 'lucide-react'
import { clsx } from 'clsx'
import { useAppStore } from '@/stores'

interface LayoutProps {
  children: ReactNode
}

interface NavItem {
  path: string
  label: string
  icon: ReactNode
  badge?: number
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const location = useLocation()
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const { setCurrentPage, theme, toggleTheme } = useAppStore()

  const navItems: NavItem[] = [
    { path: '/', label: 'Dashboard', icon: <LayoutDashboard size={20} /> },
    { path: '/positions', label: 'Positions', icon: <Wallet size={20} /> },
    { path: '/orderbook', label: 'Orderbook', icon: <BookOpen size={20} /> },
    { path: '/analytics', label: 'Analytics', icon: <BarChart3 size={20} /> },
    { path: '/instruments', label: 'Instruments', icon: <Package size={20} /> },
    { path: '/logs', label: 'Logs', icon: <Terminal size={20} /> },
  ]

  const activeNavItem = navItems.find((item) => item.path === location.pathname)

  return (
    <div className="flex h-screen bg-bg-primary overflow-hidden">
      {/* Sidebar */}
      <aside
        className={clsx(
          'bg-gradient-to-b from-bg-secondary to-bg-primary border-r border-bg-tertiary/50',
          'transition-all duration-300 ease-in-out',
          sidebarOpen ? 'w-64' : 'w-20'
        )}
      >
        <div className="flex flex-col h-full">
          {/* Logo Area */}
          <div
            className={clsx(
              'flex items-center justify-between px-4 py-6 border-b border-bg-tertiary/50',
              'transition-all duration-300',
              'light:shadow-light-card'
            )}
          >
            <div
              className={clsx(
                'flex items-center gap-3',
                !sidebarOpen && 'justify-center w-full'
              )}
            >
              <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-accent-cyan to-accent-blue flex items-center justify-center shadow-glow">
                <TrendingUp size={24} className="text-bg-primary font-bold" />
              </div>
              {sidebarOpen && (
                <div className="flex flex-col">
                  <h1 className="text-sm font-bold text-text-primary">Trading</h1>
                  <p className="text-xs text-text-tertiary">Dashboard</p>
                </div>
              )}
            </div>
            <button
              onClick={() => setSidebarOpen(!sidebarOpen)}
              className={clsx(
                'p-1 hover:bg-bg-tertiary rounded transition-colors duration-200',
                'light:hover:bg-slate-200'
              )}
              aria-label="Toggle sidebar"
            >
              {sidebarOpen ? <X size={18} /> : <Menu size={18} />}
            </button>
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-3 py-6 space-y-2 overflow-y-auto">
            {navItems.map((item) => {
              const isActive = location.pathname === item.path
              return (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={() => setCurrentPage(item.path)}
                  className={clsx(
                    'flex items-center gap-3 px-3 py-3 rounded-lg transition-all duration-200',
                    'group relative',
                    isActive
                      ? 'bg-accent-cyan/10 text-accent-cyan border border-accent-cyan/30 light:bg-blue-50 light:text-blue-600 light:border-blue-200'
                      : 'text-text-secondary hover:text-text-primary hover:bg-bg-tertiary/50 light:hover:bg-slate-100'
                  )}
                  title={!sidebarOpen ? item.label : undefined}
                >
                  <span className="flex-shrink-0">{item.icon}</span>
                  {sidebarOpen && (
                    <>
                      <span className="text-sm font-medium flex-1">{item.label}</span>
                      {item.badge && item.badge > 0 && (
                        <span className="text-xs font-bold bg-accent-red text-bg-primary px-2 py-0.5 rounded-full light:bg-red-500">
                          {item.badge}
                        </span>
                      )}
                    </>
                  )}
                  {!sidebarOpen && item.badge && item.badge > 0 && (
                    <span className="absolute -top-1 -right-1 w-5 h-5 bg-accent-red text-bg-primary text-xs font-bold rounded-full flex items-center justify-center light:bg-red-500">
                      {item.badge}
                    </span>
                  )}

                  {/* Tooltip for collapsed sidebar */}
                  {!sidebarOpen && (
                    <div className="tooltip invisible group-hover:visible bg-bg-tertiary border border-bg-surface text-text-secondary text-xs rounded px-2 py-1 whitespace-nowrap z-50 left-20 top-0 light:bg-slate-200 light:border-slate-300 light:text-slate-700">
                      {item.label}
                    </div>
                  )}
                </Link>
              )
            })}
          </nav>

          {/* Footer */}
          <div className="px-3 py-4 border-t border-bg-tertiary/50 light:shadow-light-card">
            <div className={clsx('space-y-2', !sidebarOpen && 'text-center')}>
              {sidebarOpen && (
                <>
                  <div className="flex items-center justify-between">
                    <div className="flex-1">
                      <p className="text-xs text-text-tertiary font-semibold uppercase tracking-wider">
                        Version
                      </p>
                      <p className="text-xs text-text-secondary font-mono">1.0.0</p>
                    </div>
                    <button
                      onClick={() => {
                        toggleTheme()
                        localStorage.setItem('theme', theme === 'dark' ? 'light' : 'dark')
                      }}
                      className={clsx(
                        'flex items-center justify-center w-8 h-8 rounded hover:bg-bg-tertiary/50 transition-colors',
                        'light:hover:bg-slate-200'
                      )}
                      title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
                      aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
                    >
                      {theme === 'dark' ? (
                        <Sun size={16} className="text-accent-yellow" />
                      ) : (
                        <Moon size={16} className="text-blue-600" />
                      )}
                    </button>
                  </div>
                </>
              )}
              <div className="w-full h-px bg-bg-tertiary/50 light:bg-slate-200" />
              <p className="text-xs text-text-tertiary text-center light:text-slate-600">
                {sidebarOpen ? '© 2026 Trading Setup' : '© 26'}
              </p>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="bg-gradient-to-r from-bg-secondary via-bg-tertiary to-bg-secondary border-b border-bg-tertiary/50 light:bg-white light:from-white light:via-slate-50 light:to-white light:shadow-light-card">
          <div className="px-8 py-4 flex items-center justify-between">
            <div>
              <h2 className="text-2xl font-bold text-text-primary">
                {activeNavItem?.label || 'Dashboard'}
              </h2>
              <p className="text-xs text-text-tertiary mt-1 light:text-slate-600">
                {activeNavItem?.label === 'Dashboard' &&
                  'Real-time control room for your trading account'}
                {activeNavItem?.label === 'Positions' &&
                  'Monitor open positions and pending entries'}
                {activeNavItem?.label === 'Orderbook' &&
                  'Track all orders placed this session'}
                {activeNavItem?.label === 'Analytics' &&
                  'Performance intelligence and trade metrics'}
                {activeNavItem?.label === 'Logs' &&
                  'Detailed strategy activity and system logs'}
              </p>
            </div>

            {/* Header Actions */}
            <div className="flex items-center gap-4">
              <div className="text-right">
                <p className="text-xs text-text-tertiary light:text-slate-600">Last Updated</p>
                <p className="text-sm font-mono text-accent-cyan light:text-blue-600">
                  {new Date().toLocaleTimeString('en-IN', {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: true,
                  })}
                </p>
              </div>
            </div>
          </div>
        </header>

        {/* Page Content */}
        <main className="flex-1 overflow-auto light:bg-white">
          <div className="p-8">{children}</div>
        </main>
      </div>
    </div>
  )
}

export default Layout
