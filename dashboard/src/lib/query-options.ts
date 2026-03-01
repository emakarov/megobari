import { queryOptions } from "@tanstack/react-query";
import { api } from "./api";

export const healthQueryOptions = queryOptions({
  queryKey: ["health"],
  queryFn: api.health,
  refetchInterval: 5000,
});

export const sessionsQueryOptions = queryOptions({
  queryKey: ["sessions"],
  queryFn: api.sessions.list,
  refetchInterval: 5000,
});

export const sessionQueryOptions = (name: string) =>
  queryOptions({
    queryKey: ["session", name],
    queryFn: () => api.sessions.get(name),
    refetchInterval: 3000,
    enabled: !!name,
  });

export const usageTotalQueryOptions = queryOptions({
  queryKey: ["usage", "total"],
  queryFn: api.usage.total,
  refetchInterval: 10000,
});

export const usageRecordsQueryOptions = (session?: string, limit = 100) =>
  queryOptions({
    queryKey: ["usage", "records", session, limit],
    queryFn: () => api.usage.records({ session, limit }),
    refetchInterval: 10000,
  });

export const recentMessagesQueryOptions = queryOptions({
  queryKey: ["messages", "recent"],
  queryFn: () => api.messages.recent(30),
  refetchInterval: 10000,
});

export const messagesQueryOptions = (session: string, limit = 100) =>
  queryOptions({
    queryKey: ["messages", session, limit],
    queryFn: () => api.messages.list(session, limit),
    enabled: !!session,
  });

export const summariesQueryOptions = (session?: string) =>
  queryOptions({
    queryKey: ["summaries", session],
    queryFn: () => api.summaries.list({ session, limit: 100 }),
  });

export const personasQueryOptions = queryOptions({
  queryKey: ["personas"],
  queryFn: api.personas.list,
});

export const memoriesQueryOptions = (category?: string) =>
  queryOptions({
    queryKey: ["memories", category],
    queryFn: () => api.memories.list(category),
  });

export const cronJobsQueryOptions = queryOptions({
  queryKey: ["cron-jobs"],
  queryFn: api.scheduling.cronJobs,
  refetchInterval: 10000,
});

export const heartbeatChecksQueryOptions = queryOptions({
  queryKey: ["heartbeat-checks"],
  queryFn: api.scheduling.heartbeatChecks,
  refetchInterval: 10000,
});

export const monitorTopicsQueryOptions = queryOptions({
  queryKey: ["monitor", "topics"],
  queryFn: api.monitor.topics,
  refetchInterval: 30000,
});

export const monitorEntitiesQueryOptions = (topicId?: number) =>
  queryOptions({
    queryKey: ["monitor", "entities", topicId],
    queryFn: () => api.monitor.entities(topicId),
    refetchInterval: 30000,
  });

export const monitorResourcesQueryOptions = (params?: {
  entityId?: number;
  topicId?: number;
}) =>
  queryOptions({
    queryKey: ["monitor", "resources", params?.entityId, params?.topicId],
    queryFn: () => api.monitor.resources(params),
    refetchInterval: 30000,
  });

export const monitorReportQueryOptions = (topic?: string) =>
  queryOptions({
    queryKey: ["monitor", "report", topic],
    queryFn: () => api.monitor.report(topic),
    refetchInterval: 60000,
  });

export const monitorDigestsQueryOptions = (params?: {
  topicId?: number;
  entityId?: number;
  limit?: number;
}) =>
  queryOptions({
    queryKey: ["monitor", "digests", params?.topicId, params?.entityId],
    queryFn: () => api.monitor.digests(params),
    refetchInterval: 30000,
  });
