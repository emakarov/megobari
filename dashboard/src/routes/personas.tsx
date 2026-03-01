import { createFileRoute } from "@tanstack/react-router";
import { useSuspenseQuery } from "@tanstack/react-query";
import { Users, Star, Settings, Wrench } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { personasQueryOptions, memoriesQueryOptions } from "@/lib/query-options";
import { CopyMd, personaToMd, memoriesToMd } from "@/components/copy-md";
import type { Memory } from "@/lib/api";

export const Route = createFileRoute("/personas")({
  loader: async ({ context }) => {
    await Promise.all([
      context.queryClient.ensureQueryData(personasQueryOptions),
      context.queryClient.ensureQueryData(memoriesQueryOptions()),
    ]);
  },
  component: PersonasPage,
  pendingComponent: () => (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Personas & Memories</h1>
      <div className="space-y-4">
        {Array.from({ length: 2 }).map((_, i) => (
          <Skeleton key={i} className="h-48" />
        ))}
      </div>
    </div>
  ),
});

function PersonasPage() {
  const { data: personas } = useSuspenseQuery(personasQueryOptions);
  const { data: memories } = useSuspenseQuery(memoriesQueryOptions());

  const memoryGroups = new Map<string, Memory[]>();
  if (memories) {
    for (const m of memories) {
      const existing = memoryGroups.get(m.category) ?? [];
      existing.push(m);
      memoryGroups.set(m.category, existing);
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold flex items-center gap-2">
        <Users className="h-6 w-6" />
        Personas & Memories
      </h1>

      <Tabs defaultValue="personas">
        <TabsList>
          <TabsTrigger value="personas">
            <Users className="mr-1 h-4 w-4" />
            Personas
          </TabsTrigger>
          <TabsTrigger value="memories">
            <Settings className="mr-1 h-4 w-4" />
            Memories
          </TabsTrigger>
        </TabsList>

        <TabsContent value="personas" className="mt-4">
          {personas.length === 0 ? (
            <Card>
              <CardContent className="pt-6">
                <p className="text-center text-muted-foreground">
                  No personas configured
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {personas.map((p) => (
                <Card key={p.id}>
                  <CardHeader>
                    <div className="flex items-center justify-between">
                      <CardTitle className="flex items-center gap-2">
                        {p.name}
                        {p.is_default && (
                          <Star className="h-4 w-4 text-yellow-500 fill-yellow-500" />
                        )}
                      </CardTitle>
                      <div className="flex items-center gap-2">
                        <CopyMd toMarkdown={() => personaToMd(p)} />
                        <span className="text-xs text-muted-foreground">
                          {new Date(p.created_at).toLocaleDateString()}
                        </span>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {p.description && (
                      <p className="text-sm text-muted-foreground">
                        {p.description}
                      </p>
                    )}
                    {p.system_prompt && (
                      <div>
                        <h4 className="text-xs font-medium text-muted-foreground mb-1">
                          System Prompt
                        </h4>
                        <ScrollArea className="h-32">
                          <pre className="text-xs bg-muted p-3 rounded-lg whitespace-pre-wrap">
                            {p.system_prompt}
                          </pre>
                        </ScrollArea>
                      </div>
                    )}
                    <div className="flex flex-wrap gap-2">
                      {p.mcp_servers &&
                        (p.mcp_servers as string[]).length > 0 && (
                          <Badge variant="outline" className="gap-1">
                            <Settings className="h-3 w-3" />
                            {(p.mcp_servers as string[]).length} MCP servers
                          </Badge>
                        )}
                      {p.skills && (p.skills as string[]).length > 0 && (
                        <Badge variant="outline" className="gap-1">
                          <Wrench className="h-3 w-3" />
                          {(p.skills as string[]).length} skills
                        </Badge>
                      )}
                      {p.config && Object.keys(p.config).length > 0 && (
                        <Badge variant="secondary">
                          {Object.keys(p.config).length} config options
                        </Badge>
                      )}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="memories" className="mt-4">
          {memoryGroups.size === 0 ? (
            <Card>
              <CardContent className="pt-6">
                <p className="text-center text-muted-foreground">
                  No memories stored
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {Array.from(memoryGroups.entries()).map(([category, mems]) => (
                <Card key={category}>
                  <CardHeader>
                    <CardTitle className="flex items-center gap-2">
                      {category}
                      <Badge variant="secondary">{mems.length}</Badge>
                      <CopyMd
                        toMarkdown={() => memoriesToMd(category, mems)}
                      />
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div className="space-y-2">
                      {mems.map((m) => (
                        <div
                          key={m.id}
                          className="flex items-start justify-between rounded-lg border p-3"
                        >
                          <div className="space-y-1">
                            <span className="font-mono text-sm font-medium">
                              {m.key}
                            </span>
                            <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                              {m.content}
                            </p>
                          </div>
                          <span className="text-xs text-muted-foreground whitespace-nowrap ml-4">
                            {new Date(m.updated_at).toLocaleDateString()}
                          </span>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
