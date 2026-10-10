import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { mockFetch, resultsA, runA, runB, totals } from "./mockApi";
import { ApiError, api } from "../api";

const health = { status: "ok", version: "9.9.9", active_run: null };
function renderAt(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>);
}
beforeEach(() => { vi.unstubAllGlobals(); });

describe("Overview", () => {
  it("shows a loading state, then metrics that come from the API", async () => {
    mockFetch({ "GET /api/health": health, "GET /api/runs": { runs: [runA, runB], latest: runA.run_id, active_run: null },
      [`GET /api/runs/${runA.run_id}/results`]: resultsA });
    renderAt("/");
    expect(screen.getByRole("status")).toHaveTextContent(/loading runs/i);
    expect(await screen.findByText("Total tests")).toBeInTheDocument();
    // 7 is deliberately not the demo's real total: the number must come from the mocked backend
    expect(screen.getByText("Total tests").nextElementSibling).toHaveTextContent(String(totals.total));
    expect(screen.getByText("Passed").nextElementSibling).toHaveTextContent("4");
    expect(screen.getByText("Timed out").nextElementSibling).toHaveTextContent("1");
    expect(screen.getAllByText("All results as expected").length).toBeGreaterThan(0);
    expect(screen.getByText(/failing test log\(s\) classified/)).toBeInTheDocument();
    expect(screen.getByText(/Text-pattern guesses about log wording, not verified root causes/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /launch a new run/i })).toHaveAttribute("href", "/run");
    expect(screen.getByText("latest")).toBeInTheDocument();
  });

  it("shows an empty state with no runs", async () => {
    mockFetch({ "GET /api/health": health, "GET /api/runs": { runs: [], latest: null, active_run: null } });
    renderAt("/");
    expect(await screen.findByText("No runs yet")).toBeInTheDocument();
  });

  it("shows an actionable error and retries", async () => {
    let n = 0;
    mockFetch({ "GET /api/health": health, "GET /api/runs": () => (++n === 1
      ? { status: 500, body: { error: "internal_error", message: "unexpected server error" } }
      : { body: { runs: [], latest: null, active_run: null } }) });
    renderAt("/");
    expect(await screen.findByRole("alert")).toHaveTextContent("unexpected server error");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No runs yet")).toBeInTheDocument();
  });

  it("explains when the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new TypeError("failed"); }));
    renderAt("/");
    expect(await screen.findByRole("alert")).toHaveTextContent(/cannot reach the backend/i);
  });
});

describe("Run page", () => {
  const configs = { configs: [{ id: "demo", path: "configs/demo.yaml", valid: true, problems: [], project: "demo",
    tests: [{ name: "counter_basic", description: "basic", expect: "pass", timeout_seconds: 30, tags: [] },
            { name: "hang_intentional", description: "hang", expect: "timeout", timeout_seconds: 3, tags: [] }] }] };

  it("validates, confirms, starts a run and shows progress to completion", async () => {
    let polls = 0;
    const { calls } = mockFetch({
      "GET /api/health": health, "GET /api/configs": configs,
      "POST /api/configs/validate": { ...configs.configs[0], tools: [{ role: "simulator", executable: "iverilog", found: true, path: "/x", version: "13.0" }] },
      "POST /api/runs": { status: 202, body: { run_id: "r-1", state: "starting" } },
      "GET /api/runs/r-1": () => {
        polls += 1;
        const done = polls >= 3;
        return { body: { ...runA, run_id: "r-1", state: done ? "completed" : "running", overall: done ? "as_expected" : "running",
          totals: { ...totals, total: 2 },
          progress: { completed: done ? 2 : 1, total: 2, current: done ? null : "hang_intentional", tests: [
            { name: "counter_basic", expect: "PASS", state: "done", status: "PASS" },
            done ? { name: "hang_intentional", expect: "TIMEOUT", state: "done", status: "TIMEOUT" } : { name: "hang_intentional", expect: "TIMEOUT", state: "running" }] },
          environment: null, console_tail: "", exit_code: null } };
      },
    });
    renderAt("/run");
    expect(await screen.findByText("hang_intentional")).toBeInTheDocument();   // tests listed before running
    await userEvent.click(screen.getByRole("button", { name: /validate configuration/i }));
    expect(await screen.findByText(/configuration is valid/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /start regression run/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent(/only one run can be active/i);
    expect(calls.some((c) => c.method === "POST" && c.path === "/api/runs")).toBe(false);   // nothing started yet
    await userEvent.click(screen.getByRole("button", { name: "Start run" }));
    expect(await screen.findByRole("progressbar")).toBeInTheDocument();
    const post = calls.find((c) => c.method === "POST" && c.path === "/api/runs")!;
    expect(post.body).toEqual({ config_id: "demo" });                     // only an id, never a command
    await waitFor(() => expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2"), { timeout: 5000 });
    expect(await screen.findByRole("link", { name: /view results/i })).toHaveAttribute("href", "/results?run=r-1");
  }, 15000);

  it("shows validation problems and disables the start button", async () => {
    const bad = { configs: [{ ...configs.configs[0], valid: false, problems: ["tests[a].command is required"], tests: [] }] };
    mockFetch({ "GET /api/health": health, "GET /api/configs": bad });
    renderAt("/run");
    expect(await screen.findByText(/tests\[a\]\.command is required/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /start regression run/i })).toBeDisabled();
  });

  it("reports a conflict when a run is already active and attaches to it", async () => {
    mockFetch({
      "GET /api/health": health, "GET /api/configs": configs,
      "POST /api/runs": { status: 409, body: { detail: { error: "run_active", message: "run r-9 is already in progress", active_run: "r-9" } } },
      "GET /api/runs/r-9": { ...runA, run_id: "r-9", state: "running", overall: "running", progress: { completed: 0, total: 2, current: "counter_basic", tests: [] }, environment: null, console_tail: "", exit_code: null },
    });
    renderAt("/run");
    await screen.findByText("hang_intentional");
    await userEvent.click(screen.getByRole("button", { name: /start regression run/i }));
    await userEvent.click(screen.getByRole("button", { name: "Start run" }));
    expect((await screen.findAllByText(/already in progress/)).length).toBeGreaterThan(0);
    expect(await screen.findByText("r-9")).toBeInTheDocument();
  });

  it("shows the failure details and console output of a failed run", async () => {
    mockFetch({
      "GET /api/health": { ...health, active_run: "r-f" }, "GET /api/configs": configs,
      "GET /api/runs/r-f": { ...runA, run_id: "r-f", state: "failed", overall: "failed", error: "run process exited with code 4", totals: null,
        progress: { completed: 0, total: 0, current: null, tests: [] }, environment: null, console_tail: "error: cannot write run output", exit_code: 4 },
    });
    renderAt("/run");
    expect(await screen.findByText(/run process exited with code 4/)).toBeInTheDocument();
    expect(screen.getByLabelText("Run console output")).toHaveTextContent("cannot write run output");
  });
});

describe("Results page", () => {
  const base = { "GET /api/health": health, "GET /api/runs": { runs: [runA, runB], latest: runA.run_id, active_run: null },
    [`GET /api/runs/${runA.run_id}/results`]: resultsA };

  it("never presents an expected failure as a success, and flags unexpected ones", async () => {
    mockFetch(base);
    renderAt("/results");
    const table = await screen.findByRole("table", { name: /test results/i });
    const row = (name: string) => within(table).getByText(name).closest("tr")!;
    expect(within(row("counter_basic")).getByText("Passed")).toBeInTheDocument();
    expect(within(row("counter_fail_intentional")).getByText("Expected FAIL")).toBeInTheDocument();
    expect(within(row("hang_intentional")).getByText("Expected TIMEOUT")).toBeInTheDocument();
    expect(within(row("regressed")).getByText(/UNEXPECTED FAIL \(wanted PASS\)/)).toBeInTheDocument();
    expect(within(row("counter_fail_intentional")).queryByText("Passed")).toBeNull();
  });

  it("filters and searches, and shows detail with a link to the failing log line", async () => {
    mockFetch(base);
    renderAt("/results");
    await screen.findByRole("table", { name: /test results/i });
    await userEvent.selectOptions(screen.getByLabelText("Outcome"), "unexpected");
    expect(screen.queryByText("counter_basic")).toBeNull();
    expect(screen.getByText("regressed")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Outcome"), "all");
    await userEvent.type(screen.getByLabelText("Search"), "timeout");
    expect(screen.getByText("hang_intentional")).toBeInTheDocument();
    expect(screen.queryByText("counter_fail_intentional")).toBeNull();
    await userEvent.clear(screen.getByLabelText("Search"));
    await userEvent.click(screen.getByRole("button", { name: "counter_fail_intentional" }));
    expect(screen.getByText(/ML prediction \(experimental text guess\)/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /open log at line 3/i }))
      .toHaveAttribute("href", `/logs?run=${encodeURIComponent(runA.run_id)}&test=counter_fail_intentional&line=3`);
  });

  it("marks historical runs and shows the empty-filter state", async () => {
    mockFetch({ ...base, [`GET /api/runs/${runB.run_id}/results`]: { ...resultsA, run_id: runB.run_id } });
    renderAt(`/results?run=${runB.run_id}`);
    expect(await screen.findByText(/historical run/i)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Search"), "zzzz-no-such");
    expect(screen.getByText("No tests match the filters")).toBeInTheDocument();
  });
});

describe("Log explorer", () => {
  const chunk = { text: "INFO: start\nline2\nASSERT FAIL: expected 9\nFATAL: x\n", offset: 0, next_offset: 52, size: 52, has_more: false,
    start_line: 1, test: "counter_fail_intentional", run_id: runA.run_id, log_truncated: false, findings: resultsA.tests[1].findings };
  const logUrl = `GET /api/runs/${runA.run_id}/logs/counter_fail_intentional`;
  const base = { "GET /api/health": health, "GET /api/runs": { runs: [runA], latest: runA.run_id, active_run: null },
    [`GET /api/runs/${runA.run_id}/results`]: resultsA };

  it("loads a chunk, highlights the requested line, shows findings and searches", async () => {
    const { calls } = mockFetch({ ...base, [logUrl]: chunk,
      [`${logUrl}/search`]: { query: "fatal", matches: [{ line: 4, text: "FATAL: x" }], total_matches: 1, capped: false, test: "x" } });
    renderAt(`/logs?run=${runA.run_id}&test=counter_fail_intentional&line=3`);
    const pre = await screen.findByLabelText("Log content of counter_fail_intentional");
    expect(pre).toHaveTextContent("ASSERT FAIL: expected 9");
    expect(calls.find((c) => c.path.includes("/logs/counter_fail_intentional"))!.path).toContain("around_line=3");
    expect(screen.getByText(/Parsed findings \(1\)/)).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("Search log text"), "fatal");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(await screen.findByText("1 match(es)")).toBeInTheDocument();
  });

  it("warns when a log was truncated by the engine", async () => {
    mockFetch({ ...base, [logUrl]: { ...chunk, log_truncated: true, log_bytes_total: 30_000_000 } });
    renderAt(`/logs?run=${runA.run_id}&test=counter_fail_intentional`);
    expect(await screen.findByRole("note")).toHaveTextContent(/truncated by the engine/i);
  });

  it("offers Load more for large logs and appends the next chunk", async () => {
    let n = 0;
    mockFetch({ ...base, [logUrl]: () => ({ body: n++ === 0 ? { ...chunk, text: "first\n", has_more: true, next_offset: 6, size: 12 } : { ...chunk, text: "second\n", offset: 6, next_offset: 13, has_more: false, start_line: 2 } }) });
    renderAt(`/logs?run=${runA.run_id}&test=counter_fail_intentional`);
    await userEvent.click(await screen.findByRole("button", { name: "Load more" }));
    await waitFor(() => expect(screen.getByLabelText(/Log content of/)).toHaveTextContent(/first[\s\S]*second/));
  });

  it("shows a clear message when the log file is missing", async () => {
    mockFetch({ ...base, [logUrl]: { status: 404, body: { detail: { error: "log_missing", message: "no log file for test" } } } });
    renderAt(`/logs?run=${runA.run_id}&test=counter_fail_intentional`);
    expect(await screen.findByRole("alert")).toHaveTextContent(/log file is missing/i);
  });

  it("asks to choose a test when none is selected", async () => {
    mockFetch(base);
    renderAt("/logs");
    expect(await screen.findByText("Choose a test to view its log")).toBeInTheDocument();
  });
});

describe("ML analysis", () => {
  const ev = { evaluation: { n_samples: 151, n_families: 40, class_counts: { timeout: 32 }, source_types: ["synthetic"], protocol: "grouped CV",
    labels: ["timeout", "unknown"], rule_baseline: { accuracy: 0.735, macro_f1: 0.752, per_class: { timeout: { precision: 1, recall: 0.625, f1: 0.77, support: 32 }, unknown: { precision: 0.45, recall: 1, f1: 0.62, support: 29 } }, confusion_matrix: [[20, 12], [0, 29]] },
    ml_model: { accuracy: 0.603, macro_f1: 0.6, per_class: { timeout: { precision: 0.5, recall: 0.53, f1: 0.5, support: 32 }, unknown: { precision: 0.62, recall: 0.28, f1: 0.38, support: 29 } }, confusion_matrix: [[17, 15], [21, 8]] },
    ml_misclassified_examples: [{ text: "elaboration aborted", true: "compile_error", predicted: "runtime_error" }], rule_misclassified_examples: [],
    inference_ms_per_sample: 0.15, inference_sample_size: 50, sklearn_version: "1.2.2", evaluated_at: "2026-10-09" },
    labels: ["timeout", "unknown"], statement: "The ML model classifies the TEXT of a failure log. It does not diagnose hardware defects and does not establish a verified root cause.",
    limitations: ["Synthetic data.", "Scores depend on the split seed."], baseline_higher: true, model_file_present: true };
  const base = { "GET /api/health": health, "GET /api/runs": { runs: [runA], latest: runA.run_id, active_run: null }, [`GET /api/runs/${runA.run_id}/results`]: resultsA };

  it("shows saved metrics, the honest baseline comparison and the disclaimer", async () => {
    mockFetch({ ...base, "GET /api/ml/evaluation": ev });
    renderAt("/ml");
    expect(await screen.findByText(/does not diagnose hardware defects/)).toBeInTheDocument();
    expect(await screen.findByText("0.752")).toBeInTheDocument();
    expect(screen.getByText("0.600")).toBeInTheDocument();
    expect(screen.getByText(/keyword-rule baseline scored higher than the ML model/)).toBeInTheDocument();
    expect(screen.getByText(/151/)).toBeInTheDocument();
    expect(screen.getByText("Synthetic data.")).toBeInTheDocument();
    const cm = screen.getByRole("table", { name: /confusion matrix/i });
    expect(within(cm).getByText("21")).toBeInTheDocument();                     // ML matrix shown by default
    await userEvent.click(screen.getByRole("button", { name: "Rule baseline" }));
    expect(within(screen.getByRole("table", { name: /confusion matrix/i })).getByText("12")).toBeInTheDocument();
    // run table: rule vs ML for non-passing tests only
    const t = screen.getByRole("table", { name: /rule-based category versus ML prediction/i });
    expect(within(t).getByText("counter_fail_intentional")).toBeInTheDocument();
    expect(within(t).queryByText("counter_basic")).toBeNull();
    expect(within(t).getByText("0.91")).toBeInTheDocument();
  });

  it("explains how to create the evaluation when none is saved", async () => {
    mockFetch({ ...base, "GET /api/ml/evaluation": { status: 404, body: { detail: { error: "no_evaluation", message: "none" } } } });
    renderAt("/ml");
    expect(await screen.findByText("No saved evaluation")).toBeInTheDocument();
    expect(screen.getByText(/does not diagnose hardware defects or establish verified root causes/)).toBeInTheDocument();
  });
});

describe("Compare page", () => {
  const base = { "GET /api/health": health, "GET /api/runs": { runs: [runA, runB], latest: runA.run_id, active_run: null } };
  const cmp = { before: runB.run_id, after: runA.run_id, compatible: true, warnings: [], regressions: [{ name: "counter_basic", before: "PASS", after: "FAIL", expected: "PASS" }],
    fixes: [{ name: "regressed", before: "FAIL", after: "PASS", expected: "PASS" }], other_changes: [], config_changed: ["x"], only_before: ["gone"], only_after: ["new_test"], text: "" };

  it("lists regressions, fixes and membership changes from the API", async () => {
    const { calls } = mockFetch({ ...base, "GET /api/runs/compare": cmp });
    renderAt("/compare");
    expect(await screen.findByText(/Regressions \(matched expectation before, not now\) \(1\)/)).toBeInTheDocument();
    expect(screen.getByText("counter_basic")).toBeInTheDocument();
    expect(screen.getByText(/Fixed \(did not match before, matches now\) \(1\)/)).toBeInTheDocument();
    expect(screen.getByText(/new_test/)).toBeInTheDocument();
    expect(calls.find((c) => c.path.startsWith("/api/runs/compare"))!.path).toContain(`before=${runB.run_id}`);
  });

  it("warns instead of inferring regressions for incompatible runs", async () => {
    mockFetch({ ...base, "GET /api/runs/compare": { ...cmp, compatible: false, warnings: ["project differs", "runs are not comparable; no regressions inferred"], regressions: [], fixes: [] } });
    renderAt("/compare");
    expect(await screen.findByRole("alert")).toHaveTextContent(/not comparable/i);
    expect(screen.queryByText(/Regressions \(/)).toBeNull();
  });

  it("asks for two completed runs when fewer exist", async () => {
    mockFetch({ ...base, "GET /api/runs": { runs: [runA], latest: runA.run_id, active_run: null } });
    renderAt("/compare");
    expect(await screen.findByText("Need at least two completed runs")).toBeInTheDocument();
  });
});

describe("API client", () => {
  it("maps structured and validation errors", async () => {
    mockFetch({ "GET /api/health": { status: 422, body: { detail: [{ msg: "field required" }] } }, "GET /api/configs": { status: 409, body: { detail: { error: "run_active", message: "busy", active_run: "r" } } } });
    await expect(api.health()).rejects.toMatchObject({ code: "validation", message: "field required" });
    const e = await api.configs().catch((x) => x) as ApiError;
    expect(e.code).toBe("run_active");
    expect(e.extra.active_run).toBe("r");
  });
});
