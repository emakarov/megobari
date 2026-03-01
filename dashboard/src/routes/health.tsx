import { createFileRoute } from "@tanstack/react-router";
import { useSuspenseQuery } from "@tanstack/react-query";
import {
  Heart,
  Clock,
  Activity,
  CheckCircle2,
  XCircle,
  Timer,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  healthQueryOptions,
  cronJobsQueryOptions,
  heartbeatChecksQueryOptions,
} from "@/lib/query-options";
import { CopyMd, tableToMd } from "@/components/copy-md";

export const Route = createFileRoute("/health")({
  loader: async ({ context }) => {
    await Promise.all([
      context.queryClient.ensureQueryData(healthQueryOptions),
      context.queryClient.ensureQueryData(cronJobsQueryOptions),
      context.queryClient.ensureQueryData(heartbeatChecksQueryOptions),
    ]);
  },
  component: HealthPage,
  pendingComponent: () => (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Health</h1>
      <div className="grid gap-4 md:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
    </div>
  ),
});

function HealthPage() {
  const { data: health } = useSuspenseQuery(healthQueryOptions);
  const { data: cronJobs } = useSuspenseQuery(cronJobsQueryOptions);
  const { data: heartbeats } = useSuspenseQuery(heartbeatChecksQueryOptions);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold flex items-center gap-2">
        <Heart className="h-6 w-6" />
        Health & Scheduling
      </h1>

      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Bot</CardTitle>
            <Activity className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              {health.bot_running ? (
                <CheckCircle2 className="h-5 w-5 text-green-500" />
              ) : (
                <XCircle className="h-5 w-5 text-red-500" />
              )}
              <span className="text-lg font-semibold">
                {health.bot_running ? "Running" : "Offline"}
              </span>
            </div>
            {health.active_session && (
              <p className="text-xs text-muted-foreground mt-1">
                Active: {health.active_session}
              </p>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Scheduler</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-2">
              {health.scheduler_running ? (
                <CheckCircle2 className="h-5 w-5 text-green-500" />
              ) : (
                <XCircle className="h-5 w-5 text-yellow-500" />
              )}
              <span className="text-lg font-semibold">
                {health.scheduler_running ? "Active" : "Inactive"}
              </span>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Database</CardTitle>
            <Timer className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="space-y-1 text-sm">
              <div className="flex justify-between">
                <span className="text-muted-foreground">Messages</span>
                <span className="font-mono">{health.db_stats?.messages ?? 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Memories</span>
                <span className="font-mono">{health.db_stats?.memories ?? 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Summaries</span>
                <span className="font-mono">{health.db_stats?.summaries ?? 0}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-muted-foreground">Users</span>
                <span className="font-mono">{health.db_stats?.users ?? 0}</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {health.busy_sessions && health.busy_sessions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Busy Sessions</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-2">
              {health.busy_sessions.map((s) => (
                <Badge key={s}>{s}</Badge>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Cron Jobs
            <Badge variant="secondary">{cronJobs.length}</Badge>
            {cronJobs.length > 0 && (
              <CopyMd
                label="Copy"
                toMarkdown={() =>
                  tableToMd(
                    ["Name", "Schedule", "Session", "Status", "Prompt"],
                    cronJobs.map((j) => [
                      j.name,
                      j.cron_expression,
                      j.session_name,
                      j.enabled ? "Enabled" : "Disabled",
                      j.prompt,
                    ])
                  )
                }
              />
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {cronJobs.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No cron jobs configured
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Schedule</TableHead>
                  <TableHead>Session</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Last Run</TableHead>
                  <TableHead>Prompt</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cronJobs.map((j) => (
                  <TableRow key={j.id}>
                    <TableCell className="font-medium">{j.name}</TableCell>
                    <TableCell className="font-mono text-xs">
                      {j.cron_expression}
                    </TableCell>
                    <TableCell>{j.session_name}</TableCell>
                    <TableCell>
                      <Badge variant={j.enabled ? "default" : "secondary"}>
                        {j.enabled ? "Enabled" : "Disabled"}
                      </Badge>
                      {j.isolated && (
                        <Badge variant="outline" className="ml-1">
                          Isolated
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {j.last_run_at
                        ? new Date(j.last_run_at).toLocaleString()
                        : "Never"}
                    </TableCell>
                    <TableCell className="max-w-48 truncate text-xs text-muted-foreground">
                      {j.prompt}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Heart className="h-5 w-5" />
            Heartbeat Checks
            <Badge variant="secondary">{heartbeats.length}</Badge>
            {heartbeats.length > 0 && (
              <CopyMd
                label="Copy"
                toMarkdown={() =>
                  tableToMd(
                    ["Name", "Status", "Prompt"],
                    heartbeats.map((h) => [
                      h.name,
                      h.enabled ? "Enabled" : "Disabled",
                      h.prompt,
                    ])
                  )
                }
              />
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {heartbeats.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No heartbeat checks configured
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Prompt</TableHead>
                  <TableHead>Created</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {heartbeats.map((h) => (
                  <TableRow key={h.id}>
                    <TableCell className="font-medium">{h.name}</TableCell>
                    <TableCell>
                      <Badge variant={h.enabled ? "default" : "secondary"}>
                        {h.enabled ? "Enabled" : "Disabled"}
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-64 truncate text-xs text-muted-foreground">
                      {h.prompt}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(h.created_at).toLocaleDateString()}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
