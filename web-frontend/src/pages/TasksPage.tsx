import { useQuery } from '@tanstack/react-query'
import { Clock, CheckCircle, XCircle } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { tasksAPI } from '@/lib/api'
import { formatDistanceToNow } from 'date-fns'

export default function TasksPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['tasks'],
    queryFn: () => tasksAPI.getAll(),
    refetchInterval: 3000,
  })

  const tasks = data?.tasks || []

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
      case 'success':
        return <CheckCircle className="h-5 w-5 text-green-500" />
      case 'failed':
      case 'error':
        return <XCircle className="h-5 w-5 text-red-500" />
      default:
        return <Clock className="h-5 w-5 text-yellow-500" />
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Tasks</h1>
        <p className="text-muted-foreground">Track execution history</p>
      </div>

      {isLoading ? (
        <div className="text-center text-muted-foreground">Loading tasks...</div>
      ) : (
        <div className="space-y-3">
          {tasks.map((task: any) => (
            <Card key={task.task_id || task.id}>
              <CardContent className="p-4">
                <div className="flex items-start justify-between">
                  <div className="flex-1 space-y-1">
                    <div className="flex items-center space-x-2">
                      {getStatusIcon(task.status)}
                      <h3 className="font-medium">{task.description}</h3>
                    </div>
                    <div className="flex items-center space-x-4 text-sm text-muted-foreground">
                      <span>Agent: {task.agent_id}</span>
                      <span>•</span>
                      <span>
                        {task.created_at
                          ? formatDistanceToNow(new Date(task.created_at), { addSuffix: true })
                          : 'Just now'}
                      </span>
                      {task.duration_ms && (
                        <>
                          <span>•</span>
                          <span>{task.duration_ms.toFixed(0)}ms</span>
                        </>
                      )}
                    </div>
                  </div>
                  <span
                    className={`rounded-full px-3 py-1 text-xs font-semibold ${
                      task.status === 'completed' || task.status === 'success'
                        ? 'bg-green-500/20 text-green-500'
                        : task.status === 'failed' || task.status === 'error'
                        ? 'bg-red-500/20 text-red-500'
                        : 'bg-yellow-500/20 text-yellow-500'
                    }`}
                  >
                    {task.status}
                  </span>
                </div>
              </CardContent>
            </Card>
          ))}

          {tasks.length === 0 && (
            <div className="text-center text-muted-foreground">
              No tasks yet
            </div>
          )}
        </div>
      )}
    </div>
  )
}
