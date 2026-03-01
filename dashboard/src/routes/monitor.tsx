import { useCallback, useMemo, useRef, useState } from "react";
import { createFileRoute } from "@tanstack/react-router";
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  Radar,
  Building2,
  Globe,
  FileText,
  Copy,
  FileCode,
  Check,
} from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { MonitorDigest } from "@/lib/api";
import {
  monitorTopicsQueryOptions,
  monitorEntitiesQueryOptions,
  monitorDigestsQueryOptions,
  monitorReportQueryOptions,
} from "@/lib/query-options";

const RESOURCE_ICONS: Record<string, string> = {
  blog: "\ud83d\udcdd",
  pricing: "\ud83d\udcb0",
  repo: "\ud83d\udcbb",
  jobs: "\ud83d\udc65",
  deals: "\ud83e\udd1d",
  changelog: "\ud83d\udd04",
  website: "\ud83c\udf10",
};

export const Route = createFileRoute("/monitor")({
  loader: async ({ context }) => {
    await context.queryClient.ensureQueryData(monitorTopicsQueryOptions);
  },
  component: MonitorPage,
  pendingComponent: () => (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Monitor</h1>
      <div className="grid gap-4 md:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-32" />
        ))}
      </div>
    </div>
  ),
});

function groupByEntity(digests: MonitorDigest[]) {
  const groups: { name: string; url: string; digests: MonitorDigest[] }[] = [];
  const idx = new Map<string, number>();
  for (const d of digests) {
    const name = d.entity_name || "Unknown";
    if (!idx.has(name)) {
      idx.set(name, groups.length);
      groups.push({ name, url: d.entity_url || "", digests: [] });
    }
    groups[idx.get(name)!].digests.push(d);
  }
  groups.sort((a, b) => a.name.localeCompare(b.name));
  return groups;
}

function MonitorPage() {
  const { data: topics } = useSuspenseQuery(monitorTopicsQueryOptions);
  const [selectedTopicId, setSelectedTopicId] = useState<number | undefined>();
  const [selectedEntityId, setSelectedEntityId] = useState<
    number | undefined
  >();

  const selectedTopicName = topics.find(
    (t) => t.id === selectedTopicId
  )?.name;

  const { data: entities } = useQuery(
    monitorEntitiesQueryOptions(selectedTopicId)
  );
  const { data: digests } = useQuery(
    monitorDigestsQueryOptions({
      topicId: selectedTopicId,
      entityId: selectedEntityId,
      limit: 200,
    })
  );
  const { data: report } = useQuery(
    monitorReportQueryOptions(selectedTopicName)
  );

  const grouped = useMemo(
    () => groupByEntity(digests ?? []),
    [digests]
  );

  const totalEntities = topics.reduce((s, t) => s + t.entity_count, 0);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold flex items-center gap-2">
        <Radar className="h-6 w-6" />
        Website Monitor
      </h1>

      {/* Summary cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Topics</CardTitle>
            <FileText className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <span className="text-2xl font-bold">{topics.length}</span>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Entities</CardTitle>
            <Building2 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <span className="text-2xl font-bold">{totalEntities}</span>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium">Digests</CardTitle>
            <Globe className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <span className="text-2xl font-bold">
              {digests?.length ?? "..."}
            </span>
          </CardContent>
        </Card>
      </div>

      {/* Topic selector */}
      <div className="flex flex-wrap gap-2">
        <Button
          variant={selectedTopicId === undefined ? "default" : "outline"}
          size="sm"
          onClick={() => {
            setSelectedTopicId(undefined);
            setSelectedEntityId(undefined);
          }}
        >
          All Topics
        </Button>
        {topics.map((t) => (
          <Button
            key={t.id}
            variant={selectedTopicId === t.id ? "default" : "outline"}
            size="sm"
            onClick={() => {
              setSelectedTopicId(t.id);
              setSelectedEntityId(undefined);
            }}
          >
            {t.name}
            <Badge variant="secondary" className="ml-1.5">
              {t.entity_count}
            </Badge>
          </Button>
        ))}
      </div>

      {/* Tabs: Report vs Cards */}
      <Tabs defaultValue="report">
        <TabsList>
          <TabsTrigger value="report">Report</TabsTrigger>
          <TabsTrigger value="cards">Cards</TabsTrigger>
        </TabsList>

        <TabsContent value="report" className="mt-4">
          <ReportView report={report} />
        </TabsContent>

        <TabsContent value="cards" className="mt-4">
          {entities && entities.length > 0 && (
            <div className="flex flex-wrap gap-2 mb-4">
              <Button
                variant={
                  selectedEntityId === undefined ? "default" : "outline"
                }
                size="sm"
                onClick={() => setSelectedEntityId(undefined)}
              >
                All Entities
              </Button>
              {entities.map((e) => (
                <Button
                  key={e.id}
                  variant={
                    selectedEntityId === e.id ? "default" : "outline"
                  }
                  size="sm"
                  onClick={() => setSelectedEntityId(e.id)}
                >
                  {e.name}
                </Button>
              ))}
            </div>
          )}

          {grouped.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                No digests yet. Run <code>/monitor check</code> or{" "}
                <code>/monitor baseline</code> to generate.
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              {grouped.map((group) => (
                <EntityCard key={group.name} group={group} />
              ))}
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}

function ReportView({ report }: { report: string | undefined }) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [copied, setCopied] = useState<"md" | "content" | null>(null);

  const copyMarkdown = useCallback(() => {
    if (!report) return;
    navigator.clipboard.writeText(report).then(() => {
      setCopied("md");
      setTimeout(() => setCopied(null), 2000);
    });
  }, [report]);

  const copyContent = useCallback(() => {
    if (!contentRef.current) return;
    // Select rendered content and copy as rich text
    const selection = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(contentRef.current);
    selection?.removeAllRanges();
    selection?.addRange(range);
    document.execCommand("copy");
    selection?.removeAllRanges();
    setCopied("content");
    setTimeout(() => setCopied(null), 2000);
  }, []);

  if (!report) {
    return (
      <Card>
        <CardContent className="py-8 text-center text-muted-foreground">
          No report available. Generate one with{" "}
          <code>/monitor report [topic]</code>.
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-end gap-2 pb-0 pt-4 px-6">
        <Button
          variant="outline"
          size="sm"
          onClick={copyMarkdown}
          className="gap-1.5"
        >
          {copied === "md" ? (
            <Check className="h-3.5 w-3.5" />
          ) : (
            <FileCode className="h-3.5 w-3.5" />
          )}
          {copied === "md" ? "Copied!" : "Copy Markdown"}
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={copyContent}
          className="gap-1.5"
        >
          {copied === "content" ? (
            <Check className="h-3.5 w-3.5" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
          {copied === "content" ? "Copied!" : "Copy Content"}
        </Button>
      </CardHeader>
      <CardContent className="py-6">
        <div ref={contentRef}>
        <Markdown
          remarkPlugins={[remarkGfm]}
          components={{
            h1: ({ children }) => (
              <h1 className="text-xl font-bold mt-0 mb-3">{children}</h1>
            ),
            h2: ({ children }) => (
              <h2 className="text-lg font-semibold mt-8 mb-3 border-b pb-1">
                {children}
              </h2>
            ),
            h3: ({ children }) => (
              <h3 className="text-base font-semibold mt-5 mb-2">
                {children}
              </h3>
            ),
            p: ({ children }) => (
              <p className="text-sm leading-relaxed my-2">{children}</p>
            ),
            ul: ({ children }) => (
              <ul className="list-disc list-inside space-y-1 my-2 text-sm">
                {children}
              </ul>
            ),
            ol: ({ children }) => (
              <ol className="list-decimal list-inside space-y-1 my-2 text-sm">
                {children}
              </ol>
            ),
            li: ({ children }) => (
              <li className="leading-relaxed">{children}</li>
            ),
            a: ({ href, children }) => (
              <a
                href={href}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline hover:text-primary/80"
              >
                {children}
              </a>
            ),
            table: ({ children }) => (
              <div className="overflow-x-auto my-4">
                <table className="w-full text-sm border-collapse">
                  {children}
                </table>
              </div>
            ),
            thead: ({ children }) => (
              <thead className="bg-muted/50">{children}</thead>
            ),
            th: ({ children }) => (
              <th className="border border-border px-3 py-2 text-left font-medium text-xs">
                {children}
              </th>
            ),
            td: ({ children }) => (
              <td className="border border-border px-3 py-2 text-sm">
                {children}
              </td>
            ),
            tr: ({ children }) => (
              <tr className="hover:bg-muted/30">{children}</tr>
            ),
            blockquote: ({ children }) => (
              <blockquote className="border-l-2 border-muted-foreground/30 pl-3 text-sm text-muted-foreground italic my-2">
                {children}
              </blockquote>
            ),
            hr: () => <Separator className="my-4" />,
            strong: ({ children }) => (
              <strong className="font-semibold">{children}</strong>
            ),
            code: ({ children }) => (
              <code className="bg-muted px-1 py-0.5 rounded text-xs">
                {children}
              </code>
            ),
          }}
        >
          {report}
        </Markdown>
        </div>
      </CardContent>
    </Card>
  );
}

function EntityCard({
  group,
}: {
  group: { name: string; url: string; digests: MonitorDigest[] };
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <Card>
      <CardHeader
        className="cursor-pointer pb-3"
        onClick={() => setExpanded(!expanded)}
      >
        <CardTitle className="flex items-center gap-2 text-base">
          <Building2 className="h-4 w-4 shrink-0" />
          {group.url ? (
            <a
              href={group.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary underline hover:text-primary/80"
              onClick={(e) => e.stopPropagation()}
            >
              {group.name}
            </a>
          ) : (
            <span>{group.name}</span>
          )}
          <Badge variant="secondary" className="ml-auto">
            {group.digests.length} resource
            {group.digests.length !== 1 && "s"}
          </Badge>
        </CardTitle>
      </CardHeader>
      {expanded && (
        <CardContent className="pt-0">
          <div className="space-y-3">
            {group.digests.map((d, i) => (
              <div key={d.id}>
                {i > 0 && <Separator className="mb-3" />}
                <div className="flex items-start gap-2">
                  <span className="text-base shrink-0 mt-0.5">
                    {RESOURCE_ICONS[d.resource_type] || "\ud83d\udcc4"}
                  </span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      {d.resource_url ? (
                        <a
                          href={d.resource_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="font-medium text-sm text-primary underline hover:text-primary/80"
                        >
                          {d.resource_name || d.resource_type}
                        </a>
                      ) : (
                        <span className="font-medium text-sm">
                          {d.resource_name || d.resource_type}
                        </span>
                      )}
                      <Badge variant="outline" className="text-xs">
                        {d.resource_type}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground leading-relaxed">
                      {d.summary}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      )}
    </Card>
  );
}
