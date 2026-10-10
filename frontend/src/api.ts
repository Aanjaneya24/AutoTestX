import type {
  Comparison, ConfigInfo, LogChunk, LogSearch, MlEvaluation, RunDetail, RunList, RunResults,
} from "./types";

export class ApiError extends Error {
  status: number;
  code: string;
  problems: string[];
  extra: Record<string, unknown>;
  constructor(status: number, code: string, message: string, problems: string[] = [], extra: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.problems = problems;
    this.extra = extra;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, init);
  } catch {
    throw new ApiError(0, "network", "Cannot reach the backend. Is it running on 127.0.0.1:8765?");
  }
  if (res.ok) return (await res.json()) as T;
  let body: any = null;
  try { body = await res.json(); } catch { /* not JSON */ }
  const d = body?.detail;
  if (d && typeof d === "object" && !Array.isArray(d)) {
    throw new ApiError(res.status, d.error ?? "error", d.message ?? res.statusText, d.problems ?? [], d);
  }
  if (Array.isArray(d)) {
    throw new ApiError(res.status, "validation", d.map((x: any) => x.msg).join("; ") || "Invalid request");
  }
  throw new ApiError(res.status, body?.error ?? "error", body?.message ?? res.statusText ?? "Request failed");
}

const q = (o: Record<string, string | number | boolean | undefined>) => {
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(o)) if (v !== undefined) p.set(k, String(v));
  const s = p.toString();
  return s ? `?${s}` : "";
};
const enc = encodeURIComponent;

export const api = {
  health: () => request<{ status: string; version: string; active_run: string | null }>("/api/health"),
  configs: () => request<{ configs: ConfigInfo[] }>("/api/configs"),
  validate: (config_id: string) =>
    request<ConfigInfo>("/api/configs/validate", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ config_id }),
    }),
  startRun: (config_id: string) =>
    request<{ run_id: string; state: string }>("/api/runs", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ config_id }),
    }),
  runs: (limit = 50) => request<RunList>(`/api/runs${q({ limit })}`),
  run: (id: string) => request<RunDetail>(`/api/runs/${enc(id)}`),
  results: (id: string) => request<RunResults>(`/api/runs/${enc(id)}/results`),
  log: (id: string, test: string, opts: { offset?: number; limit?: number; tail?: boolean; around_line?: number } = {}) =>
    request<LogChunk>(`/api/runs/${enc(id)}/logs/${enc(test)}${q(opts)}`),
  searchLog: (id: string, test: string, query: string) =>
    request<LogSearch>(`/api/runs/${enc(id)}/logs/${enc(test)}/search${q({ q: query })}`),
  compare: (before: string, after: string) =>
    request<Comparison>(`/api/runs/compare${q({ before, after })}`),
  mlEvaluation: () => request<MlEvaluation>("/api/ml/evaluation"),
};
