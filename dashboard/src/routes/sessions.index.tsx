import { useState } from "react";
import { createFileRoute, Link } from "@tanstack/react-router";
import { useSuspenseQuery } from "@tanstack/react-query";
import { MessageSquare, ArrowRight } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { sessionsQueryOptions } from "@/lib/query-options";
import { CopyMd, tableToMd } from "@/components/copy-md";

export const Route = createFileRoute("/sessions/")({
  loader: async ({ context }) => {
    await context.queryClient.ensureQueryData(sessionsQueryOptions);
  },
  component: SessionsPage,
  pendingComponent: () => (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Sessions</h1>
      <div className="space-y-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-12 w-full" />
        ))}
      </div>
    </div>
  ),
});

function SessionsPage() {
  const { data: sessions } = useSuspenseQuery(sessionsQueryOptions);
  const [filter, setFilter] = useState("");

  const filtered = sessions.filter((s) =>
    s.name.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <MessageSquare className="h-6 w-6" />
          Sessions
        </h1>
        <Badge variant="secondary">{sessions.length} total</Badge>
      </div>

      <Input
        placeholder="Filter sessions..."
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        className="max-w-sm"
      />

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            All Sessions
            <CopyMd
              label="Copy"
              toMarkdown={() =>
                tableToMd(
                  ["Name", "Status", "Model", "Effort", "Cost", "Messages", "Last Used"],
                  filtered.map((s) => [
                    s.name,
                    s.is_busy ? "Busy" : s.is_active ? "Active" : "Inactive",
                    s.model,
                    s.effort,
                    `$${s.current_run_cost.toFixed(4)}`,
                    String(s.current_run_messages),
                    new Date(s.last_used_at).toLocaleString(),
                  ])
                )
              }
            />
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Model</TableHead>
                <TableHead>Effort</TableHead>
                <TableHead className="text-right">Cost</TableHead>
                <TableHead className="text-right">Messages</TableHead>
                <TableHead>Last Used</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={8}
                    className="text-center text-muted-foreground"
                  >
                    No sessions found
                  </TableCell>
                </TableRow>
              ) : (
                filtered.map((s) => (
                  <TableRow key={s.name}>
                    <TableCell className="font-medium">
                      <Link
                        to="/sessions/$name"
                        params={{ name: s.name }}
                        className="hover:underline"
                      >
                        {s.name}
                      </Link>
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        {s.is_busy && <Badge>Busy</Badge>}
                        {s.streaming && (
                          <Badge variant="secondary">Streaming</Badge>
                        )}
                        {s.is_active && !s.is_busy && (
                          <Badge variant="outline">Active</Badge>
                        )}
                        {!s.is_active && (
                          <Badge variant="secondary">Inactive</Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{s.model}</TableCell>
                    <TableCell>{s.effort}</TableCell>
                    <TableCell className="text-right font-mono">
                      ${s.current_run_cost.toFixed(4)}
                    </TableCell>
                    <TableCell className="text-right">
                      {s.current_run_messages}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(s.last_used_at).toLocaleString()}
                    </TableCell>
                    <TableCell>
                      <Button asChild variant="ghost" size="sm">
                        <Link to="/sessions/$name" params={{ name: s.name }}>
                          <ArrowRight className="h-4 w-4" />
                        </Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
