import { useMemo, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useSuspenseQuery, useQuery } from "@tanstack/react-query";
import { BarChart3, DollarSign, Cpu, Clock } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
} from "recharts";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  usageTotalQueryOptions,
  usageRecordsQueryOptions,
} from "@/lib/query-options";
import { CopyMd, tableToMd } from "@/components/copy-md";

const COLORS = [
  "hsl(220, 70%, 55%)",
  "hsl(160, 60%, 45%)",
  "hsl(30, 80%, 55%)",
  "hsl(280, 60%, 55%)",
  "hsl(0, 70%, 55%)",
  "hsl(190, 60%, 45%)",
];

export const Route = createFileRoute("/usage")({
  loader: async ({ context }) => {
    await context.queryClient.ensureQueryData(usageTotalQueryOptions);
  },
  component: UsagePage,
  pendingComponent: () => (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Usage</h1>
      <div className="grid gap-4 md:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-28" />
        ))}
      </div>
    </div>
  ),
});

function UsagePage() {
  const { data: total } = useSuspenseQuery(usageTotalQueryOptions);
  const [limit, setLimit] = useState("100");
  const { data: records, isLoading: recordsLoading } = useQuery(
    usageRecordsQueryOptions(undefined, Number(limit))
  );

  const sessionCosts = useMemo(() => {
    if (!records) return [];
    const map = new Map<string, number>();
    for (const r of records) {
      map.set(r.session_name, (map.get(r.session_name) ?? 0) + r.cost_usd);
    }
    return Array.from(map.entries())
      .map(([name, cost]) => ({ name, cost: Number(cost.toFixed(6)) }))
      .sort((a, b) => b.cost - a.cost);
  }, [records]);

  const dailyCosts = useMemo(() => {
    if (!records) return [];
    const map = new Map<string, number>();
    for (const r of records) {
      const day = r.created_at.slice(0, 10);
      map.set(day, (map.get(day) ?? 0) + r.cost_usd);
    }
    return Array.from(map.entries())
      .map(([date, cost]) => ({ date, cost: Number(cost.toFixed(6)) }))
      .sort((a, b) => a.date.localeCompare(b.date));
  }, [records]);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <BarChart3 className="h-6 w-6" />
          Usage
        </h1>
        <Select value={limit} onValueChange={setLimit}>
          <SelectTrigger className="w-36">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="50">Last 50</SelectItem>
            <SelectItem value="100">Last 100</SelectItem>
            <SelectItem value="200">Last 200</SelectItem>
            <SelectItem value="500">Last 500</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Total Cost</CardTitle>
            <DollarSign className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold font-mono">
              ${(total?.total_cost_usd ?? 0).toFixed(4)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Input Tokens</CardTitle>
            <Cpu className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold font-mono">
              {formatNumber(total?.total_input_tokens ?? 0)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Output Tokens</CardTitle>
            <Cpu className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold font-mono">
              {formatNumber(total?.total_output_tokens ?? 0)}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Total Duration</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold font-mono">
              {formatDuration(total?.total_duration_ms ?? 0)}
            </div>
            <p className="text-xs text-muted-foreground">
              {total?.total_turns ?? 0} turns
            </p>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Daily Cost</CardTitle>
          </CardHeader>
          <CardContent>
            {dailyCosts.length === 0 ? (
              <p className="text-sm text-muted-foreground">No data</p>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <BarChart data={dailyCosts}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                  <XAxis
                    dataKey="date"
                    tickFormatter={(d) => d.slice(5)}
                    className="text-xs"
                  />
                  <YAxis tickFormatter={(v) => `$${v}`} className="text-xs" />
                  <Tooltip
                    formatter={(v) => [`$${Number(v ?? 0).toFixed(6)}`, "Cost"]}
                    contentStyle={{
                      background: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: "8px",
                    }}
                  />
                  <Bar
                    dataKey="cost"
                    fill="hsl(220, 70%, 55%)"
                    radius={[4, 4, 0, 0]}
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Cost by Session</CardTitle>
          </CardHeader>
          <CardContent>
            {sessionCosts.length === 0 ? (
              <p className="text-sm text-muted-foreground">No data</p>
            ) : (
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={sessionCosts}
                    dataKey="cost"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={100}
                    label={({ name, percent }) =>
                      `${name} (${((percent ?? 0) * 100).toFixed(0)}%)`
                    }
                    labelLine={false}
                  >
                    {sessionCosts.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    formatter={(v) => [`$${Number(v ?? 0).toFixed(6)}`, "Cost"]}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Recent Records
            <Badge variant="secondary">{records?.length ?? 0}</Badge>
            {records && records.length > 0 && (
              <CopyMd
                label="Copy"
                toMarkdown={() =>
                  tableToMd(
                    ["Session", "Cost", "Turns", "Input", "Output", "Duration", "Date"],
                    records.map((r) => [
                      r.session_name,
                      `$${r.cost_usd.toFixed(6)}`,
                      String(r.num_turns),
                      formatNumber(r.input_tokens),
                      formatNumber(r.output_tokens),
                      formatDuration(r.duration_ms),
                      new Date(r.created_at).toLocaleString(),
                    ])
                  )
                }
              />
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {recordsLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Session</TableHead>
                  <TableHead className="text-right">Cost</TableHead>
                  <TableHead className="text-right">Turns</TableHead>
                  <TableHead className="text-right">Input</TableHead>
                  <TableHead className="text-right">Output</TableHead>
                  <TableHead className="text-right">Duration</TableHead>
                  <TableHead>Date</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {records?.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell className="font-medium">
                      {r.session_name}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      ${r.cost_usd.toFixed(6)}
                    </TableCell>
                    <TableCell className="text-right">{r.num_turns}</TableCell>
                    <TableCell className="text-right font-mono">
                      {formatNumber(r.input_tokens)}
                    </TableCell>
                    <TableCell className="text-right font-mono">
                      {formatNumber(r.output_tokens)}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatDuration(r.duration_ms)}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {new Date(r.created_at).toLocaleString()}
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

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const remaining = Math.floor(s % 60);
  if (m < 60) return `${m}m ${remaining}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}
