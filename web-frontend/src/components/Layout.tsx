import { Outlet, Link, useLocation } from 'react-router-dom'
import { Home, Users, CheckSquare, Zap, LogOut, Moon, Sun } from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'
import { useTheme } from './ThemeProvider'
import { Button } from './ui/button'

export default function Layout() {
  const location = useLocation()
  const logout = useAuthStore((state) => state.logout)
  const user = useAuthStore((state) => state.user)
  const { theme, setTheme } = useTheme()

  const navigation = [
    { name: 'Dashboard', href: '/', icon: Home },
    { name: 'Agents', href: '/agents', icon: Users },
    { name: 'Tasks', href: '/tasks', icon: CheckSquare },
    { name: 'Skills', href: '/skills', icon: Zap },
  ]

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <div className="w-64 border-r bg-card">
        <div className="flex h-16 items-center border-b px-6">
          <h1 className="text-xl font-bold text-primary">Balbes</h1>
        </div>

        <nav className="space-y-1 p-4">
          {navigation.map((item) => {
            const Icon = item.icon
            const isActive = location.pathname === item.href

            return (
              <Link
                key={item.name}
                to={item.href}
                className={`flex items-center space-x-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-accent hover:text-accent-foreground'
                }`}
              >
                <Icon className="h-5 w-5" />
                <span>{item.name}</span>
              </Link>
            )
          })}
        </nav>

        <div className="absolute bottom-0 w-64 border-t p-4">
          <div className="flex items-center justify-between">
            <div className="text-sm">
              <p className="font-medium">{user?.username || 'User'}</p>
              <p className="text-muted-foreground">{user?.email || ''}</p>
            </div>

            <div className="flex space-x-2">
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setTheme(theme === 'dark' ? 'light' : 'dark')}
              >
                {theme === 'dark' ? <Sun className="h-5 w-5" /> : <Moon className="h-5 w-5" />}
              </Button>

              <Button
                variant="ghost"
                size="icon"
                onClick={logout}
              >
                <LogOut className="h-5 w-5" />
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="flex-1 overflow-auto">
        <main className="container mx-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
