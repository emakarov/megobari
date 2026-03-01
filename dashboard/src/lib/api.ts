const API_BASE = "/api";

const isBrowser = typeof window !== "undefined";

function getToken(): string {
  if (!isBrowser) return "";
  return localStorage.getItem("dashboard_token") || "";
}

export function setToken(token: string) {
  if (isBrowser) localStorage.setItem("dashboard_token", token);
}

export function clearToken() {
  if (isBrowser) localStorage.removeItem("dashboard_token");
}

export function hasToken(): boolean {
  return !!getToken();
}

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });

  if (res.status === 401) {
    clearToken();
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }

  return res.json();
}

async function apiFetchText(path: string, init?: RequestInit): Promise<string> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${token}`,
      ...init?.headers,
    },
  });

  if (res.status === 401) {
    clearToken();
    throw new Error("Unauthorized");
  }

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }

  return res.text();
}

// --- Types ---

export interface HealthResponse {
  bot_running: boolean;
  scheduler_running: boolean;
  active_session: string | null;
  busy_sessions: string[];
  total_sessions: number;
  sessions_with_context: number;
  db_stats: {
    users: number;
    memories: number;
    messages: number;
    summaries: number;
    error?: string;
  };
}

export interface SessionListItem {
  name: string;
  is_active: boolean;
  is_busy: boolean;
  has_context: boolean;
  streaming: boolean;
  permission_mode: string;
  model: string;
  thinking: boolean;
  effort: string;
  cwd: string;
  created_at: string;
  last_used_at: string;
  current_run_cost: number;
  current_run_messages: number;
}

export interface SessionDetail {
  name: string;
  session_id: string | null;
  is_active: boolean;
  is_busy: boolean;
  streaming: boolean;
  permission_mode: string;
  model: string;
  thinking: boolean;
  thinking_budget: number | null;
  effort: string;
  max_turns: number | null;
  cwd: string;
  dirs: string[];
  created_at: string;
  last_used_at: string;
  current_run: {
    cost_usd: number;
    messages: number;
    input_tokens: number;
    output_tokens: number;
  };
  all_time: UsageStats;
  recent_messages: {
    role: string;
    content: string;
    created_at: string;
  }[];
}

export interface UsageStats {
  total_cost_usd: number;
  total_input_tokens: number;
  total_output_tokens: number;
  total_messages: number;
  total_turns: number;
  total_duration_ms: number;
}

export interface UsageRecord {
  id: number;
  session_name: string;
  cost_usd: number;
  num_turns: number;
  duration_ms: number;
  input_tokens: number;
  output_tokens: number;
  created_at: string;
}

export interface Message {
  id: number;
  session_name: string;
  role: string;
  content: string;
  summarized: boolean;
  created_at: string;
}

export interface Summary {
  id: number;
  session_name: string;
  summary: string;
  short_summary: string;
  topics: string[];
  message_count: number;
  is_milestone: boolean;
  created_at: string;
}

export interface Persona {
  id: number;
  name: string;
  description: string;
  system_prompt: string;
  mcp_servers: unknown[];
  skills: unknown[];
  config: Record<string, unknown>;
  is_default: boolean;
  created_at: string;
}

export interface Memory {
  id: number;
  category: string;
  key: string;
  content: string;
  metadata: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface CronJob {
  id: number;
  name: string;
  cron_expression: string;
  prompt: string;
  session_name: string;
  isolated: boolean;
  enabled: boolean;
  timezone: string;
  last_run_at: string | null;
  created_at: string;
}

export interface HeartbeatCheck {
  id: number;
  name: string;
  prompt: string;
  enabled: boolean;
  created_at: string;
}

export interface MonitorTopic {
  id: number;
  name: string;
  description: string | null;
  enabled: boolean;
  entity_count: number;
  created_at: string;
}

export interface MonitorEntity {
  id: number;
  topic_id: number;
  name: string;
  url: string | null;
  entity_type: string;
  description: string | null;
  enabled: boolean;
  resource_count: number;
  created_at: string;
}

export interface MonitorResource {
  id: number;
  topic_id: number;
  entity_id: number;
  name: string;
  url: string;
  resource_type: string;
  enabled: boolean;
  last_checked_at: string | null;
  last_changed_at: string | null;
  created_at: string;
}

export interface MonitorDigest {
  id: number;
  topic_id: number;
  entity_id: number;
  resource_id: number;
  snapshot_id: number;
  summary: string;
  change_type: string;
  created_at: string;
  entity_name: string;
  entity_url: string;
  resource_name: string;
  resource_type: string;
  resource_url: string;
}

// --- API Functions ---

export const api = {
  health: () => apiFetch<HealthResponse>("/health"),

  sessions: {
    list: () => apiFetch<SessionListItem[]>("/sessions"),
    get: (name: string) => apiFetch<SessionDetail>(`/sessions/${encodeURIComponent(name)}`),
  },

  usage: {
    total: () => apiFetch<UsageStats>("/usage"),
    records: (params?: { session?: string; limit?: number }) => {
      const sp = new URLSearchParams();
      if (params?.session) sp.set("session", params.session);
      if (params?.limit) sp.set("limit", String(params.limit));
      const qs = sp.toString();
      return apiFetch<UsageRecord[]>(`/usage/records${qs ? `?${qs}` : ""}`);
    },
    bySession: (name: string) => apiFetch<UsageStats>(`/usage/${encodeURIComponent(name)}`),
  },

  messages: {
    list: (session: string, limit = 50) =>
      apiFetch<Message[]>(`/messages/${encodeURIComponent(session)}?limit=${limit}`),
    recent: (limit = 30) =>
      apiFetch<Message[]>(`/messages/recent?limit=${limit}`),
  },

  summaries: {
    list: (params?: { session?: string; limit?: number }) => {
      const sp = new URLSearchParams();
      if (params?.session) sp.set("session", params.session);
      if (params?.limit) sp.set("limit", String(params.limit));
      const qs = sp.toString();
      return apiFetch<Summary[]>(`/summaries${qs ? `?${qs}` : ""}`);
    },
  },

  personas: {
    list: () => apiFetch<Persona[]>("/personas"),
    get: (name: string) => apiFetch<Persona>(`/personas/${encodeURIComponent(name)}`),
  },

  memories: {
    list: (category?: string) => {
      const qs = category ? `?category=${encodeURIComponent(category)}` : "";
      return apiFetch<Memory[]>(`/memories${qs}`);
    },
  },

  scheduling: {
    cronJobs: () => apiFetch<CronJob[]>("/cron-jobs"),
    heartbeatChecks: () => apiFetch<HeartbeatCheck[]>("/heartbeat-checks"),
  },

  monitor: {
    topics: () => apiFetch<MonitorTopic[]>("/monitor/topics"),
    entities: (topicId?: number) => {
      const qs = topicId ? `?topic_id=${topicId}` : "";
      return apiFetch<MonitorEntity[]>(`/monitor/entities${qs}`);
    },
    resources: (params?: { entityId?: number; topicId?: number }) => {
      const sp = new URLSearchParams();
      if (params?.entityId) sp.set("entity_id", String(params.entityId));
      if (params?.topicId) sp.set("topic_id", String(params.topicId));
      const qs = sp.toString();
      return apiFetch<MonitorResource[]>(`/monitor/resources${qs ? `?${qs}` : ""}`);
    },
    report: (topic?: string) => {
      const qs = topic ? `?topic=${encodeURIComponent(topic)}` : "";
      return apiFetchText(`/monitor/report${qs}`);
    },
    digests: (params?: { topicId?: number; entityId?: number; limit?: number }) => {
      const sp = new URLSearchParams();
      if (params?.topicId) sp.set("topic_id", String(params.topicId));
      if (params?.entityId) sp.set("entity_id", String(params.entityId));
      if (params?.limit) sp.set("limit", String(params.limit));
      const qs = sp.toString();
      return apiFetch<MonitorDigest[]>(`/monitor/digests${qs ? `?${qs}` : ""}`);
    },
  },
};
