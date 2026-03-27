import { useQuery } from '@tanstack/react-query'
import { Activity, Users, CheckSquare, Zap } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { dashboardAPI } from '@/lib/api'

export default function DashboardPage() {
  const { data: status } = useQuery({
    queryKey: ['dashboard-status'],
    queryFn: dashboardAPI.getStatus,
    refetchInterval: 5000,
  })

  const stats = [
    {
      title: 'Agents Online',
      value: status?.agents_online || 0,
      icon: Users,
      color: 'text-blue-500',
    },
    {
      title: 'Total Tasks',
      value: status?.total_tasks || 0,
      icon: CheckSquare,
      color: 'text-green-500',
    },
    {
      title: 'Completed Tasks',
      value: status?.completed_tasks || 0,
      icon: Activity,
      color: 'text-purple-500',
    },
    {
      title: 'Total Skills',
      value: '0',
      icon: Zap,
      color: 'text-yellow-500',
    },
  ]

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <p className="text-muted-foreground">Overview of your multi-agent system</p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => {
          const Icon = stat.icon
          return (
            <Card key={stat.title}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{stat.title}</CardTitle>
                <Icon className={`h-4 w-4 ${stat.color}`} />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{stat.value}</div>
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* Services Status */}
      <Card>
        <CardHeader>
          <CardTitle>Services Status</CardTitle>
          <CardDescription>Health status of all microservices</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-2">
            {status?.services && Object.entries(status.services as Record<string, string>).map(([name, serviceStatus]) => (
              <div key={name} className="flex items-center justify-between">
                <span className="text-sm font-medium capitalize">
                  {name.replace('_', ' ')}
                </span>
                <span
                  className={`rounded-full px-2 py-1 text-xs font-semibold ${
                    serviceStatus === 'healthy'
                      ? 'bg-green-500/20 text-green-500'
                      : serviceStatus === 'offline'
                      ? 'bg-red-500/20 text-red-500'
                      : 'bg-yellow-500/20 text-yellow-500'
                  }`}
                >
                  {String(serviceStatus)}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* System Info */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Token Usage</CardTitle>
            <CardDescription>LLM token consumption</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {status?.total_tokens_used?.toLocaleString() || '0'}
            </div>
            <p className="text-sm text-muted-foreground">tokens used</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Memory Usage</CardTitle>
            <CardDescription>System resource utilization</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {status?.memory_usage_percent?.toFixed(1) || '0'}%
            </div>
            <p className="text-sm text-muted-foreground">memory used</p>
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
