import { Link } from "react-router-dom";
import { api } from "../api";
import { useAsync, usePolling } from "../hooks";
import { fmtDuration, fmtTime } from "../format";
import { Button, Card, Empty, ErrorBox, OverallBadge, PageHeader, Spinner, Stat, td, th } from "../components/ui";

export default function Overview() {
  const runs = useAsync(() => api.runs(20), []);
  const latestId = runs.data?.latest ?? null;
  const active = runs.data?.active_run ?? null;
  usePolling(runs.reload, 1500, !!active);
  const results = useAsync(latestId ? () => api.results(latestId) : null, [latestId, active]);

  const launch = (
    <Link to="/run"><Button>Launch a new run</Button></Link>
  );

  if (runs.loading && !runs.data) return <><PageHeader title="Overview" /><Spinner label="Loading runs" /></>;
  if (runs.error) return <><PageHeader title="Overview" /><ErrorBox error={runs.error} onRetry={runs.reload} /></>;
  const list = runs.data!.runs;
  if (list.length === 0) {
    return (
      <>
        <PageHeader title="Overview" actions={launch} />
        <Empty title="No runs yet">Launch the demonstration suite to see results here.</Empty>
      </>
    );
  }
  const latest = list[0];
  const t = latest.totals;
  const expected = results.data ? results.data.tests.filter((x) => x.outcome === "expected_failure").length : null;
  return (
    <>
      <PageHeader title="Overview"
        subtitle="Latest run first. Figures come straight from the saved run on disk; nothing here is hard-coded."
        actions={launch} />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium">Latest run</span>
        <code className="rounded bg-slate-200 px-2 py-0.5 text-sm dark:bg-slate-800">{latest.run_id}</code>
        <OverallBadge overall={latest.overall} />
        <span className="text-sm text-slate-500">started {fmtTime(latest.started)} · duration {fmtDuration(latest.duration_seconds)}</span>
      </div>
      {latest.error && <div className="mb-4"><ErrorBox title={`Run ${latest.state}`} error={latest.error} /></div>}
      {t ? (
        <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <Stat label="Total tests" value={t.total} />
          <Stat label="Passed" value={t.passed} tone="good" />
          <Stat label="Failed" value={t.failed} hint={expected !== null ? `${expected} expected negative test(s) overall` : undefined} />
          <Stat label="Errored" value={t.errored} tone={t.errored ? "bad" : undefined} />
          <Stat label="Timed out" value={t.timed_out} />
          <Stat label="Unexpected" value={t.unexpected} tone={t.unexpected ? "bad" : "good"} hint="results that differ from `expect`" />
        </div>
      ) : <Empty title="No totals yet">The run has not reported any results.</Empty>}
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card title="Recent runs">
            <div className="overflow-x-auto">
              <table className="w-full">
                <caption className="sr-only">Recent runs, newest first</caption>
                <thead><tr><th className={th}>Run</th><th className={th}>Status</th><th className={th}>Tests</th><th className={th}>Unexpected</th><th className={th}>Duration</th></tr></thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                  {list.map((r, i) => (
                    <tr key={r.run_id}>
                      <td className={td}>
                        <Link className="text-blue-600 hover:underline dark:text-blue-400" to={`/results?run=${encodeURIComponent(r.run_id)}`}>{r.run_id}</Link>
                        {i === 0 ? <span className="ml-2 rounded bg-blue-100 px-1.5 text-xs text-blue-800 dark:bg-blue-950 dark:text-blue-300">latest</span> : null}
                      </td>
                      <td className={td}><OverallBadge overall={r.overall} /></td>
                      <td className={td}>{r.totals?.total ?? "-"}</td>
                      <td className={td}>{r.totals?.unexpected ?? "-"}</td>
                      <td className={td}>{fmtDuration(r.duration_seconds)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
        <Card title="Latest ML classification">
          {latest.ml && latest.ml.classified > 0 ? (
            <div className="space-y-2 text-sm">
              <div><span className="text-2xl font-semibold tabular-nums">{latest.ml.classified}</span> failing test log(s) classified</div>
              <ul className="space-y-1">
                {Object.entries(latest.ml.labels).map(([label, n]) => <li key={label} className="flex justify-between"><code>{label}</code><span className="tabular-nums">{n}</span></li>)}
              </ul>
              <div className="text-slate-500">Agrees with the rule-based category on {latest.ml.agree_with_rules} of {latest.ml.classified}; {latest.ml.needs_review} flagged needs_review.</div>
              <p className="text-xs text-slate-500">Text-pattern guesses about log wording, not verified root causes.</p>
              <Link to="/ml" className="text-blue-600 hover:underline dark:text-blue-400">ML analysis →</Link>
            </div>
          ) : <p className="text-sm text-slate-500">No ML predictions in the latest run (no failing tests, ML disabled, or no trained model).</p>}
        </Card>
      </div>
    </>
  );
}
