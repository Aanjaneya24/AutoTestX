import { useEffect, useState } from "react";
import { api } from "../api";
import { useAsync } from "../hooks";
import { RunPicker } from "../components/RunPicker";
import type { ChangeEntry, Comparison } from "../types";
import { Card, Empty, ErrorBox, PageHeader, Spinner, StatusBadge, td, th } from "../components/ui";

function Changes({ title, entries, tone }: { title: string; entries: ChangeEntry[]; tone: string }) {
  return (
    <Card title={`${title} (${entries.length})`}>
      {entries.length === 0 ? <p className="text-sm text-slate-500">None.</p> : (
        <table className="w-full">
          <thead><tr><th className={th}>Test</th><th className={th}>Before</th><th className={th}>After</th><th className={th}>Expected</th></tr></thead>
          <tbody className={`divide-y divide-slate-200 dark:divide-slate-800 ${tone}`}>
            {entries.map((e) => <tr key={e.name}><td className={td}>{e.name}</td><td className={td}><StatusBadge status={e.before} /></td><td className={td}><StatusBadge status={e.after} /></td><td className={td}>{e.expected}</td></tr>)}
          </tbody>
        </table>)}
    </Card>
  );
}

export default function Compare() {
  const list = useAsync(() => api.runs(100), []);
  const runs = (list.data?.runs ?? []).filter((r) => r.state === "completed");
  const [before, setBefore] = useState("");
  const [after, setAfter] = useState("");
  useEffect(() => {
    if (runs.length >= 2 && !before && !after) { setAfter(runs[0].run_id); setBefore(runs[1].run_id); }
  }, [runs.length]); // eslint-disable-line react-hooks/exhaustive-deps
  const cmp = useAsync<Comparison>(before && after ? () => api.compare(before, after) : null, [before, after]);

  if (list.loading && !list.data) return <><PageHeader title="Compare runs" /><Spinner label="Loading runs" /></>;
  if (list.error) return <><PageHeader title="Compare runs" /><ErrorBox error={list.error} onRetry={list.reload} /></>;
  if (runs.length < 2) return <><PageHeader title="Compare runs" /><Empty title="Need at least two completed runs">Run the suite twice, then compare.</Empty></>;

  return (
    <>
      <PageHeader title="Compare runs"
        subtitle="Judged against each test's own expectation: an expected-failure test that starts passing is a regression. Uses the same comparison code as the CLI." />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="min-w-72"><RunPicker label="Before (older)" runs={runs} latest={list.data!.latest} value={before} onChange={setBefore} onlyCompleted /></div>
        <div className="min-w-72"><RunPicker label="After (newer)" runs={runs} latest={list.data!.latest} value={after} onChange={setAfter} onlyCompleted /></div>
      </div>
      {cmp.loading && <Spinner label="Comparing" />}
      {cmp.error && <ErrorBox error={cmp.error} onRetry={cmp.reload} />}
      {cmp.data && (
        <div className="space-y-4">
          {!cmp.data.compatible && (
            <div role="alert" className="rounded-lg border border-amber-400 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200">
              <b>These runs are not comparable.</b> No regressions are inferred.
              <ul className="mt-1 list-disc pl-5">{cmp.data.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
            </div>)}
          {cmp.data.compatible && cmp.data.regressions.length + cmp.data.fixes.length + cmp.data.other_changes.length + cmp.data.config_changed.length + cmp.data.only_before.length + cmp.data.only_after.length === 0 &&
            <div role="status" className="rounded-lg border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">No differences between these runs.</div>}
          {cmp.data.compatible && (
            <div className="grid gap-4 lg:grid-cols-2">
              <Changes title="Regressions (matched expectation before, not now)" entries={cmp.data.regressions} tone="" />
              <Changes title="Fixed (did not match before, matches now)" entries={cmp.data.fixes} tone="" />
              <Changes title="Other changes (still unexpected, differently)" entries={cmp.data.other_changes} tone="" />
              <Card title="Configuration and membership">
                <ul className="space-y-1 text-sm">
                  <li>Command or expectation changed (not judged): {cmp.data.config_changed.length ? cmp.data.config_changed.join(", ") : "none"}</li>
                  <li>Only in before (removed): {cmp.data.only_before.length ? cmp.data.only_before.join(", ") : "none"}</li>
                  <li>Only in after (new): {cmp.data.only_after.length ? cmp.data.only_after.join(", ") : "none"}</li>
                </ul>
              </Card>
            </div>)}
        </div>)}
    </>
  );
}
