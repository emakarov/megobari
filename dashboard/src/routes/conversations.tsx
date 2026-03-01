import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useSuspenseQuery, useQuery } from "@tanstack/react-query";
import { Brain, BookOpen, Tag, Bot, User } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  sessionsQueryOptions,
  summariesQueryOptions,
  messagesQueryOptions,
} from "@/lib/query-options";
import { CopyMd, summaryToMd, messagesToMd, singleMessageToMd } from "@/components/copy-md";

export const Route = createFileRoute("/conversations")({
  loader: async ({ context }) => {
    await Promise.all([
      context.queryClient.ensureQueryData(sessionsQueryOptions),
      context.queryClient.ensureQueryData(summariesQueryOptions()),
    ]);
  },
  component: ConversationsPage,
  pendingComponent: () => (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Conversations</h1>
      <div className="space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
    </div>
  ),
});

function ConversationsPage() {
  const { data: sessions } = useSuspenseQuery(sessionsQueryOptions);
  const [selectedSession, setSelectedSession] = useState<string>("__all__");
  const sessionFilter =
    selectedSession === "__all__" ? undefined : selectedSession;

  const { data: summaries, isLoading: summariesLoading } = useQuery(
    summariesQueryOptions(sessionFilter)
  );
  const { data: messages, isLoading: messagesLoading } = useQuery(
    messagesQueryOptions(sessionFilter || "", 200)
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Brain className="h-6 w-6" />
          Conversations
        </h1>
        <Select value={selectedSession} onValueChange={setSelectedSession}>
          <SelectTrigger className="w-48">
            <SelectValue placeholder="All sessions" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="__all__">All sessions</SelectItem>
            {sessions.map((s) => (
              <SelectItem key={s.name} value={s.name}>
                {s.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <Tabs defaultValue="summaries">
        <TabsList>
          <TabsTrigger value="summaries">
            <BookOpen className="mr-1 h-4 w-4" />
            Summaries
          </TabsTrigger>
          <TabsTrigger value="messages" disabled={!sessionFilter}>
            <Brain className="mr-1 h-4 w-4" />
            Messages
          </TabsTrigger>
        </TabsList>

        <TabsContent value="summaries" className="mt-4">
          {summariesLoading ? (
            <div className="space-y-4">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-32" />
              ))}
            </div>
          ) : !summaries || summaries.length === 0 ? (
            <Card>
              <CardContent className="pt-6">
                <p className="text-center text-muted-foreground">
                  No conversation summaries yet
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {summaries.map((s) => (
                <Card key={s.id}>
                  <CardHeader className="pb-2">
                    <div className="flex items-center justify-between">
                      <CardTitle className="text-sm flex items-center gap-2">
                        <span className="font-mono text-xs text-muted-foreground">
                          {s.session_name}
                        </span>
                        {s.is_milestone && <Badge>Milestone</Badge>}
                        <Badge variant="secondary">{s.message_count} msgs</Badge>
                      </CardTitle>
                      <div className="flex items-center gap-2">
                        <CopyMd toMarkdown={() => summaryToMd(s)} />
                        <span className="text-xs text-muted-foreground">
                          {new Date(s.created_at).toLocaleString()}
                        </span>
                      </div>
                    </div>
                  </CardHeader>
                  <CardContent className="space-y-2">
                    {s.short_summary && (
                      <p className="text-sm font-medium">{s.short_summary}</p>
                    )}
                    <p className="text-sm text-muted-foreground whitespace-pre-wrap">
                      {s.summary}
                    </p>
                    {s.topics && s.topics.length > 0 && (
                      <div className="flex items-center gap-1 pt-1">
                        <Tag className="h-3 w-3 text-muted-foreground" />
                        {s.topics.map((t) => (
                          <Badge key={t} variant="outline" className="text-xs">
                            {t}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </CardContent>
                </Card>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="messages" className="mt-4">
          {!sessionFilter ? (
            <Card>
              <CardContent className="pt-6">
                <p className="text-center text-muted-foreground">
                  Select a session to view messages
                </p>
              </CardContent>
            </Card>
          ) : messagesLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-16" />
              ))}
            </div>
          ) : (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  Messages
                  <Badge variant="secondary">
                    {messages?.length ?? 0}
                  </Badge>
                  {messages && messages.length > 0 && (
                    <CopyMd
                      label="Copy all"
                      toMarkdown={() => messagesToMd(messages)}
                    />
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ScrollArea className="h-[600px]">
                  {!messages || messages.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No messages</p>
                  ) : (
                    <div className="space-y-3">
                      {messages.map((m) => (
                        <div key={m.id}>
                          <div className="flex items-start gap-3">
                            <div className="mt-0.5">
                              {m.role === "user" ? (
                                <User className="h-4 w-4 text-blue-500" />
                              ) : (
                                <Bot className="h-4 w-4 text-green-500" />
                              )}
                            </div>
                            <div className="flex-1 space-y-1">
                              <div className="flex items-center gap-2">
                                <span className="text-xs font-medium capitalize">
                                  {m.role}
                                </span>
                                <span className="text-xs text-muted-foreground">
                                  {new Date(m.created_at).toLocaleString()}
                                </span>
                                {m.summarized && (
                                  <Badge variant="outline" className="text-xs">
                                    Summarized
                                  </Badge>
                                )}
                              </div>
                              <p className="text-sm whitespace-pre-wrap break-words">
                                {m.content}
                              </p>
                            </div>
                            <CopyMd toMarkdown={() => singleMessageToMd(m)} />
                          </div>
                          <Separator className="mt-3" />
                        </div>
                      ))}
                    </div>
                  )}
                </ScrollArea>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
