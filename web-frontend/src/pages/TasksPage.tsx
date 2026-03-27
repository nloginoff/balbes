import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Clock, CheckCircle, XCircle } from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { tasksAPI } from '@/lib/api'
import { formatDistanceToNow } from 'date-fns'

export default function TasksPage() {
  const queryClient = useQueryClient()
  const [agentId, setAgentId] = useState('orchestrator')
  const [description, setDescription] = useState('')
  const [createError, setCreateError] = useState('')

  const { data, isLoading } = useQuery({
    queryKey: ['tasks'],
    queryFn: () => tasksAPI.getAll(),
    refetchInterval: 3000,
  })

  const tasks = data?.tasks || []

  const createTaskMutation = useMutation({
    mutationFn: () => tasksAPI.create(agentId, description),
    onSuccess: () => {
      setDescription('')
      setCreateError('')
      queryClient.invalidateQueries({ queryKey: ['tasks'] })
    },
    onError: (err: any) => {
      setCreateError(err?.response?.data?.detail || 'Failed to create task')
    },
  })

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

      <Card>
        <CardHeader>
          <CardTitle>Create Task</CardTitle>
          <CardDescription>Send a task to an agent from the web interface</CardDescription>
        </CardHeader>
        <CardContent>
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault()
              if (!description.trim()) {
                setCreateError('Description is required')
                return
              }
              createTaskMutation.mutate()
            }}
          >
            <div>
              <label htmlFor="agentId" className="mb-1 block text-sm font-medium">
                Agent
              </label>
              <select
                id="agentId"
                value={agentId}
                onChange={(e) => setAgentId(e.target.value)}
                className="h-10 w-full rounded-md border border-input bg-background px-3 text-sm"
              >
                <option value="orchestrator">orchestrator</option>
                <option value="coder">coder</option>
              </select>
            </div>

            <div>
              <label htmlFor="taskDescription" className="mb-1 block text-sm font-medium">
                Description
              </label>
              <Input
                id="taskDescription"
                placeholder="Describe what agent should do"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>

            {createError && (
              <div className="rounded-md bg-destructive/15 p-2 text-sm text-destructive">
                {createError}
              </div>
            )}

            <Button type="submit" disabled={createTaskMutation.isPending}>
              {createTaskMutation.isPending ? 'Creating...' : 'Create Task'}
            </Button>
          </form>
        </CardContent>
      </Card>

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
