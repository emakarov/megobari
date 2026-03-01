import { createFileRoute, Link } from "@tanstack/react-router";
import { useSuspenseQuery, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bot, User, Cpu, Clock, DollarSign } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Separator } from "@/components/ui/separator";
import { ScrollArea } from "@/components/ui/scroll-area";
import { sessionQueryOptions, messagesQueryOptions } from "@/lib/query-options";
import { CopyMd, messagesToMd, singleMessageToMd } from "@/components/copy-md";

export const Route = createFileRoute("/sessions/$name")({
  loader: async ({ context, params }) => {
    await context.queryClient.ensureQueryData(sessionQueryOptions(params.name));
  },
  component: SessionDetailPage,
  pendingComponent: () => (
    <div className="space-y-6">
      <Skeleton className="h-8 w-48" />
      <div className="grid gap-4 md:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
    </div>
  ),
});

function SessionDetailPage() {
  const { name } = Route.useParams();
  const { data: session } = useSuspenseQuery(sessionQueryOptions(name));
  const { data: messages } = useQuery(messagesQueryOptions(name, 50));

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button asChild variant="ghost" size="sm">
          <Link to="/sessions">
            <ArrowLeft className="h-4 w-4" />
          </Link>
        </Button>
        <div>
          <h1 className="text-2xl font-bold">{session.name}</h1>
          <p className="text-sm text-muted-foreground font-mono">{session.cwd}</p>
        </div>
        <div className="ml-auto flex items-center gap-2">
          {session.is_busy && <Badge>Busy</Badge>}
          {session.streaming && <Badge variant="secondary">Streaming</Badge>}
          {session.is_active && !session.is_busy && (
            <Badge variant="outline">Active</Badge>
          )}
          {!session.is_active && <Badge variant="secondary">Inactive</Badge>}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Current Run</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold font-mono">
              ${session.current_run.cost_usd.toFixed(4)}
            </div>
            <p className="text-xs text-muted-foreground">
              {session.current_run.messages} messages
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">All Time Cost</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold font-mono">
              ${(session.all_time?.total_cost_usd ?? 0).toFixed(4)}
            </div>
            <p className="text-xs text-muted-foreground">
              {session.all_time?.total_turns ?? 0} turns
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Tokens</CardTitle>
            <Cpu className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold font-mono">
              {formatNumber(
                session.current_run.input_tokens +
                  session.current_run.output_tokens
              )}
            </div>
            <p className="text-xs text-muted-foreground">
              {formatNumber(session.current_run.input_tokens)} in /{" "}
              {formatNumber(session.current_run.output_tokens)} out
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Config</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="space-y-1 text-sm">
              <div>
                Model: <span className="font-mono">{session.model}</span>
              </div>
              <div>Effort: {session.effort}</div>
              <div>Mode: {session.permission_mode}</div>
              {session.thinking && <div>Thinking: on</div>}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Recent Messages
            {messages && messages.length > 0 && (
              <CopyMd
                label="Copy all"
                toMarkdown={() => messagesToMd(messages)}
              />
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-[500px]">
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
    </div>
  );
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}
