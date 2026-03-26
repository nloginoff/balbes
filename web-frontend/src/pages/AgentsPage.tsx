import { useQuery } from '@tanstack/react-query'
import { Activity, Circle } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { agentsAPI } from '@/lib/api'

export default function AgentsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['agents'],
    queryFn: agentsAPI.getAll,
  })

  const agents = data?.agents || []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Agents</h1>
        <p className="text-muted-foreground">Manage your AI agents</p>
      </div>

      {isLoading ? (
        <div className="text-center text-muted-foreground">Loading agents...</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {agents.map((agent: any) => (
            <Card key={agent.agent_id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">{agent.name || agent.agent_id}</CardTitle>
                  <Circle
                    className={`h-3 w-3 ${
                      agent.status === 'online' ? 'fill-green-500 text-green-500' : 'fill-gray-400 text-gray-400'
                    }`}
                  />
                </div>
                <CardDescription>{agent.agent_id}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Status:</span>
                    <span className="font-medium capitalize">{agent.status || 'unknown'}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Tokens Used:</span>
                    <span className="font-medium">{agent.total_tokens_used?.toLocaleString() || 0}</span>
                  </div>
                  <div className="flex justify-between text-sm">
                    <span className="text-muted-foreground">Tasks:</span>
                    <span className="font-medium">{agent.tasks_completed || 0}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          {agents.length === 0 && (
            <div className="col-span-full text-center text-muted-foreground">
              No agents available
            </div>
          )}
        </div>
      )}
    </div>
  )
}
