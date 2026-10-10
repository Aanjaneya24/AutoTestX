import { vi } from "vitest";

type Handler = (url: URL, init?: RequestInit) => { status?: number; body: unknown } | Promise<{ status?: number; body: unknown }>;

/** Install a fetch mock that routes by "METHOD /path". Unmatched requests fail the test loudly. */
export function mockFetch(routes: Record<string, Handler | unknown>) {
  const calls: { method: string; path: string; body?: unknown }[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = new URL(String(input), "http://localhost");
    const method = (init?.method ?? "GET").toUpperCase();
    calls.push({ method, path: url.pathname + url.search, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const key = `${method} ${url.pathname}`;
    if (!(key in routes)) throw new Error(`unmocked request: ${key}`);
    const h = routes[key];
    const isSpec = h && typeof h === "object" && "status" in (h as object) && "body" in (h as object);
    const out = typeof h === "function" ? await (h as Handler)(url, init) : isSpec ? (h as any) : { body: h };
    const status = (out as any).status ?? 200;
    return new Response(JSON.stringify((out as any).body), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return { calls, fn };
}

export const totals = { total: 7, passed: 4, failed: 2, errored: 0, timed_out: 1, unexpected: 0 };

export const runA = {
  run_id: "20261009-100000-aaaa", state: "completed", overall: "as_expected", error: null, project: "demo",
  started: "2026-10-09T10:00:00+00:00", finished: "2026-10-09T10:00:07+00:00", duration_seconds: 7.0,
  totals, all_as_expected: true, unexpected_tests: [],
  ml: { classified: 3, labels: { assertion_failure: 1, compile_error: 1, timeout: 1 }, needs_review: 1, agree_with_rules: 2 },
};
export const runB = { ...runA, run_id: "20261009-090000-bbbb", started: "2026-10-09T09:00:00+00:00", ml: null };

export const test = (over: Record<string, unknown>) => ({
  name: "t", status: "PASS", expected_status: "PASS", outcome: "passed", exit_code: 0, duration_seconds: 0.04,
  rule_category: null, findings: [], ml_prediction: null, log_available: true, log_truncated: false, command: ["echo"],
  status_reason: "exit 0", ...over,
});
export const resultsA = {
  run_id: runA.run_id, state: "completed",
  tests: [
    test({ name: "counter_basic" }),
    test({ name: "counter_fail_intentional", status: "FAIL", expected_status: "FAIL", outcome: "expected_failure", exit_code: 1,
      rule_category: "assertion_failure", findings: [{ line: 3, category: "ASSERT", snippet: "ASSERT FAIL: expected 9" }],
      ml_prediction: { label: "assertion_failure", top_label: "assertion_failure", confidence: 0.91, needs_review: false } }),
    test({ name: "hang_intentional", status: "TIMEOUT", expected_status: "TIMEOUT", outcome: "expected_failure", exit_code: null, rule_category: "timeout" }),
    test({ name: "regressed", status: "FAIL", expected_status: "PASS", outcome: "unexpected_failure", exit_code: 1, rule_category: "runtime_error", log_truncated: true, log_bytes_total: 9999999 }),
  ],
};
