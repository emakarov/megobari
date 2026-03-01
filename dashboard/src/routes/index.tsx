import { useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useSuspenseQuery, useQuery } from "@tanstack/react-query";
import {
  Activity,
  Brain,
  Database,
  MessageSquare,
  Clock,
  DollarSign,
  User,
  Bot,
  ChevronDown,
  ChevronUp,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  healthQueryOptions,
  sessionsQueryOptions,
  usageTotalQueryOptions,
  recentMessagesQueryOptions,
} from "@/lib/query-options";
import { useLiveMessages } from "@/hooks/use-live-messages";
import { CopyMd, singleMessageToMd, messagesToMd } from "@/components/copy-md";
import type { Message } from "@/lib/api";

export const Route = createFileRoute("/")({
  loader: async ({ context }) => {
    await Promise.all([
      context.queryClient.ensureQueryData(healthQueryOptions),
      context.queryClient.ensureQueryData(sessionsQueryOptions),
      context.queryClient.ensureQueryData(usageTotalQueryOptions),
      context.queryClient.ensureQueryData(recentMessagesQueryOptions),
    ]);
  },
  component: DashboardPage,
  pendingComponent: DashboardSkeleton,
});

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Card key={i}>
            <CardHeader className="pb-2">
              <Skeleton className="h-4 w-24" />
            </CardHeader>
            <CardContent>
              <Skeleton className="h-8 w-16" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

function StatCard({
  title,
  value,
  icon: Icon,
  description,
}: {
  title: string;
  value: string | number;
  icon: React.ElementType;
  description?: string;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {description && (
          <p className="text-xs text-muted-foreground">{description}</p>
        )}
      </CardContent>
    </Card>
  );
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  return `${days}d ago`;
}

const PREVIEW_LEN = 300;

function MessageItem({ m }: { m: Message }) {
  const isLong = m.content.length > PREVIEW_LEN;
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={`flex gap-3 rounded-lg border p-3 transition-colors ${isLong ? "cursor-pointer hover:bg-muted/50" : ""}`}
      onClick={isLong ? () => setExpanded((v) => !v) : undefined}
    >
      <div className="mt-0.5 flex-shrink-0">
        {m.role === "user" ? (
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-primary text-primary-foreground">
            <User className="h-3.5 w-3.5" />
          </div>
        ) : (
          <div className="flex h-7 w-7 items-center justify-center rounded-full bg-secondary text-secondary-foreground">
            <Bot className="h-3.5 w-3.5" />
          </div>
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-xs font-medium">
            {m.role === "user" ? "You" : "Assistant"}
          </span>
          <Badge variant="outline" className="text-[10px] px-1.5 py-0">
            {m.session_name}
          </Badge>
          <CopyMd toMarkdown={() => singleMessageToMd(m)} />
          <span className="ml-auto text-[10px] text-muted-foreground whitespace-nowrap">
            {timeAgo(m.created_at)}
          </span>
        </div>
        <p className={`text-sm text-muted-foreground whitespace-pre-wrap break-words ${!expanded && isLong ? "line-clamp-3" : ""}`}>
          {expanded ? m.content : isLong ? m.content.slice(0, PREVIEW_LEN) + "..." : m.content}
        </p>
        {isLong && (
          <button
            className="mt-1 flex items-center gap-1 text-xs text-primary hover:underline"
            onClick={(e) => { e.stopPropagation(); setExpanded((v) => !v); }}
          >
            {expanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            {expanded ? "Show less" : "Show more"}
          </button>
        )}
      </div>
    </div>
  );
}

function LiveMessagesFeed({ initial }: { initial: Message[] }) {
  const messages = useLiveMessages(initial);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <MessageSquare className="h-5 w-5" />
          Recent Messages
          <CopyMd
            toMarkdown={() => messagesToMd(messages)}
            label="Copy all"
          />
          <span className="ml-auto flex items-center gap-1.5 text-xs font-normal text-muted-foreground">
            <span className="h-2 w-2 rounded-full bg-green-500 animate-pulse" />
            Live
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {messages.length === 0 ? (
          <p className="text-sm text-muted-foreground">No messages yet</p>
        ) : (
          <div className="space-y-3 max-h-[600px] overflow-y-auto">
            {messages.map((m) => (
              <MessageItem key={m.id} m={m} />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function DashboardPage() {
  const { data: health } = useSuspenseQuery(healthQueryOptions);
  const { data: sessions } = useSuspenseQuery(sessionsQueryOptions);
  const { data: usage } = useQuery(usageTotalQueryOptions);
  const { data: recentMessages } = useQuery(recentMessagesQueryOptions);

  const activeSessions = sessions?.filter((s) => s.is_active) || [];
  const busySessions = sessions?.filter((s) => s.is_busy) || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Dashboard</h1>
        <div className="flex items-center gap-2">
          <Badge variant={health?.bot_running ? "default" : "destructive"}>
            {health?.bot_running ? "Bot Running" : "Bot Offline"}
          </Badge>
          {health?.scheduler_running && (
            <Badge variant="secondary">Scheduler Active</Badge>
          )}
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Sessions"
          value={health?.total_sessions ?? 0}
          icon={MessageSquare}
          description={`${activeSessions.length} active, ${busySessions.length} busy`}
        />
        <StatCard
          title="Total Cost"
          value={`$${(usage?.total_cost_usd ?? 0).toFixed(4)}`}
          icon={DollarSign}
          description={`${usage?.total_turns ?? 0} turns`}
        />
        <StatCard
          title="Total Tokens"
          value={formatNumber(
            (usage?.total_input_tokens ?? 0) + (usage?.total_output_tokens ?? 0)
          )}
          icon={Brain}
          description={`${formatNumber(usage?.total_input_tokens ?? 0)} in / ${formatNumber(usage?.total_output_tokens ?? 0)} out`}
        />
        <StatCard
          title="DB Records"
          value={health?.db_stats?.messages ?? 0}
          icon={Database}
          description={`${health?.db_stats?.memories ?? 0} memories, ${health?.db_stats?.summaries ?? 0} summaries`}
        />
      </div>

      {/* Live Messages Feed — newest first, WebSocket-powered */}
      <LiveMessagesFeed initial={recentMessages ?? []} />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Active Sessions
          </CardTitle>
        </CardHeader>
        <CardContent>
          {activeSessions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No active sessions</p>
          ) : (
            <div className="space-y-3">
              {activeSessions.map((s) => (
                <div
                  key={s.name}
                  className="flex items-center justify-between rounded-lg border p-3"
                >
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-medium">{s.name}</span>
                      {s.is_busy && <Badge className="text-xs">Busy</Badge>}
                      {s.streaming && (
                        <Badge variant="secondary" className="text-xs">
                          Streaming
                        </Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      {s.model} &middot; {s.effort} effort &middot;{" "}
                      {s.permission_mode}
                    </p>
                  </div>
                  <div className="text-right text-sm">
                    <div className="font-mono">${s.current_run_cost.toFixed(4)}</div>
                    <div className="text-xs text-muted-foreground">
                      {s.current_run_messages} msgs
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Recent Sessions
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!sessions || sessions.length === 0 ? (
            <p className="text-sm text-muted-foreground">No sessions yet</p>
          ) : (
            <div className="space-y-2">
              {sessions.slice(0, 10).map((s) => (
                <div
                  key={s.name}
                  className="flex items-center justify-between rounded-lg border p-3"
                >
                  <div>
                    <span className="font-medium">{s.name}</span>
                    <p className="text-xs text-muted-foreground">
                      Last used: {new Date(s.last_used_at).toLocaleString()}
                    </p>
                  </div>
                  <Badge variant={s.has_context ? "default" : "secondary"}>
                    {s.has_context ? "Has Context" : "No Context"}
                  </Badge>
                </div>
              ))}
            </div>
          )}
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
