import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks";
import { useRuns } from "../components/useRuns";
import { RunPicker } from "../components/RunPicker";
import { fmtBytes, fmtDuration } from "../format";
import type { TestRecord } from "../types";
import { Card, Empty, ErrorBox, OutcomeBadge, PageHeader, Spinner, StatusBadge, td, th } from "../components/ui";

export default function Results() {
  const { list, latest, selected, select } = useRuns();
  const results = useAsync(selected ? () => api.results(selected) : null, [selected]);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");
  const [outcome, setOutcome] = useState("all");
  const [chosen, setChosen] = useState<string | null>(null);

  const tests = results.data?.tests ?? [];
  const visible = useMemo(() => tests.filter((t) => {
    if (search && !`${t.name} ${t.rule_category ?? ""}`.toLowerCase().includes(search.toLowerCase())) return false;
    if (status !== "all" && t.status !== status) return false;
    if (outcome === "unexpected" && !t.outcome.startsWith("unexpected")) return false;
    if (outcome === "expected_failure" && t.outcome !== "expected_failure") return false;
    if (outcome === "passed" && t.outcome !== "passed") return false;
    return true;
  }), [tests, search, status, outcome]);
  const detail = tests.find((t) => t.name === chosen) ?? null;

  if (list.loading && !list.data) return <><PageHeader title="Results" /><Spinner label="Loading runs" /></>;
  if (list.error) return <><PageHeader title="Results" /><ErrorBox error={list.error} onRetry={list.reload} /></>;
  if (!list.data!.runs.length) return <><PageHeader title="Results" /><Empty title="No runs yet">Start a run from the Run page.</Empty></>;

  const isLatest = selected === latest;
  return (
    <>
      <PageHeader title="Test results"
        subtitle="Expected negative tests are labelled “Expected FAIL/TIMEOUT”; they are not successes. Anything that differs from its expectation is marked UNEXPECTED." />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="min-w-72"><RunPicker label="Run" runs={list.data!.runs} latest={latest} value={selected} onChange={select} /></div>
        {!isLatest && <span className="rounded bg-amber-100 px-2 py-1 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">Historical run (not the latest)</span>}
      </div>
      {results.loading && <Spinner label="Loading results" />}
      {results.error && <ErrorBox error={results.error} onRetry={results.reload} />}
      {results.data && (
        <>
          <div className="mb-3 flex flex-wrap gap-3">
            <label className="flex flex-col text-sm"><span className="font-medium">Search</span>
              <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="name or category"
                className="rounded-md border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-900" /></label>
            <label className="flex flex-col text-sm"><span className="font-medium">Status</span>
              <select value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-md border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-900">
                <option value="all">All</option><option>PASS</option><option>FAIL</option><option>ERROR</option><option>TIMEOUT</option>
              </select></label>
            <label className="flex flex-col text-sm"><span className="font-medium">Outcome</span>
              <select value={outcome} onChange={(e) => setOutcome(e.target.value)} className="rounded-md border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-900">
                <option value="all">All</option><option value="passed">Passed</option><option value="expected_failure">Expected failures</option><option value="unexpected">Unexpected</option>
              </select></label>
          </div>
          <div className="grid gap-4 xl:grid-cols-3">
            <div className="xl:col-span-2">
              <Card>
                {tests.length === 0 ? <Empty title="This run has no results yet" /> : visible.length === 0 ? <Empty title="No tests match the filters" /> : (
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <caption className="sr-only">Test results for run {selected}</caption>
                      <thead><tr><th className={th}>Test</th><th className={th}>Status</th><th className={th}>Outcome</th><th className={th}>Duration</th><th className={th}>Exit</th><th className={th}>Category</th></tr></thead>
                      <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                        {visible.map((t) => (
                          <tr key={t.name} className={t.name === chosen ? "bg-blue-50 dark:bg-slate-800" : ""}>
                            <td className={td}><button type="button" className="font-medium text-blue-600 hover:underline dark:text-blue-400" onClick={() => setChosen(t.name)} aria-pressed={t.name === chosen}>{t.name}</button></td>
                            <td className={td}><StatusBadge status={t.status} /></td>
                            <td className={td}><OutcomeBadge outcome={t.outcome} expected={t.expected_status} actual={t.status} /></td>
                            <td className={td}>{fmtDuration(t.duration_seconds)}</td>
                            <td className={td}>{t.exit_code ?? "-"}</td>
                            <td className={td}>{t.rule_category ? <code>{t.rule_category}</code> : "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
              <p className="mt-2 text-xs text-slate-500">Showing {visible.length} of {tests.length} tests.</p>
            </div>
            <div>{detail ? <Detail run={selected} t={detail} /> : <Card title="Test detail"><p className="text-sm text-slate-500">Select a test name to inspect it.</p></Card>}</div>
          </div>
        </>
      )}
    </>
  );
}

function Detail({ run, t }: { run: string; t: TestRecord }) {
  const first = t.findings[0];
  const logLink = `/logs?run=${encodeURIComponent(run)}&test=${encodeURIComponent(t.name)}${first ? `&line=${first.line}` : ""}`;
  return (
    <Card title={`Detail: ${t.name}`}>
      <dl className="space-y-2 text-sm">
        <div><dt className="text-xs text-slate-500">Expected vs actual</dt><dd>expected <b>{t.expected_status}</b>, actual <b>{t.status}</b> <OutcomeBadge outcome={t.outcome} expected={t.expected_status} actual={t.status} /></dd></div>
        <div><dt className="text-xs text-slate-500">Reason</dt><dd>{t.status_reason || "-"}</dd></div>
        <div><dt className="text-xs text-slate-500">Rule-based category (deterministic)</dt><dd>{t.rule_category ?? "-"}</dd></div>
        <div><dt className="text-xs text-slate-500">ML prediction (experimental text guess)</dt>
          <dd>{t.ml_prediction ? <>{t.ml_prediction.label} · confidence {t.ml_prediction.confidence.toFixed(2)}{t.ml_prediction.needs_review ? " · needs review" : ""}</> : "none"}</dd></div>
        <div><dt className="text-xs text-slate-500">Command</dt><dd><code className="break-all text-xs">{(t.command ?? []).join(" ")}</code></dd></div>
        <div><dt className="text-xs text-slate-500">Parsed findings</dt><dd>{t.findings.length} {t.findings.length ? "" : "(none)"}</dd></div>
        {t.log_truncated && <div className="rounded bg-amber-100 p-2 text-xs text-amber-900 dark:bg-amber-950 dark:text-amber-200">Log was truncated ({fmtBytes(t.log_bytes_total)} produced).</div>}
      </dl>
      <div className="mt-3">
        {t.log_available ? <Link className="text-blue-600 underline dark:text-blue-400" to={logLink}>Open log{first ? ` at line ${first.line}` : ""} →</Link> : <span className="text-sm text-slate-500">Log file not available.</span>}
      </div>
    </Card>
  );
}
