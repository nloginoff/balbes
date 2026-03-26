import { useQuery } from '@tanstack/react-query'
import { Star, TrendingUp } from 'lucide-react'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { skillsAPI } from '@/lib/api'

export default function SkillsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ['skills'],
    queryFn: skillsAPI.getAll,
  })

  const skills = data?.skills || []

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Skills</h1>
        <p className="text-muted-foreground">Available agent capabilities</p>
      </div>

      {isLoading ? (
        <div className="text-center text-muted-foreground">Loading skills...</div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {skills.map((skill: any) => (
            <Card key={skill.skill_id}>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-lg">{skill.name}</CardTitle>
                  <div className="flex items-center space-x-1 text-sm text-yellow-500">
                    <Star className="h-4 w-4 fill-current" />
                    <span>{skill.rating?.toFixed(1) || '0.0'}</span>
                  </div>
                </div>
                <CardDescription className="line-clamp-2">{skill.description}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Category:</span>
                    <span className="rounded-full bg-primary/20 px-2 py-0.5 text-xs font-medium text-primary">
                      {skill.category}
                    </span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Usage:</span>
                    <span className="font-medium">{skill.usage_count || 0}x</span>
                  </div>
                  <div className="flex items-center justify-between text-sm">
                    <span className="text-muted-foreground">Version:</span>
                    <span className="font-medium">{skill.version || '1.0.0'}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}

          {skills.length === 0 && (
            <div className="col-span-full text-center text-muted-foreground">
              No skills available
            </div>
          )}
        </div>
      )}
    </div>
  )
}
