import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, ApiError } from "../api";
import { useAsync, usePolling } from "../hooks";
import type { ConfigInfo, RunDetail } from "../types";
import { fmtDuration } from "../format";
import { Button, Card, ConfirmDialog, Empty, ErrorBox, OverallBadge, PageHeader, Spinner, StatusBadge, td, th } from "../components/ui";

export default function RunPage() {
  const configs = useAsync(() => api.configs(), []);
  const [configId, setConfigId] = useState("");
  const [validation, setValidation] = useState<ConfigInfo | null>(null);
  const [validating, setValidating] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [launchError, setLaunchError] = useState<ApiError | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [detail, setDetail] = useState<RunDetail | null>(null);
  const [pollError, setPollError] = useState<ApiError | null>(null);

  // pick a default config and re-attach to a run that is already in flight (e.g. after a page reload)
  useEffect(() => {
    if (configs.data && !configId && configs.data.configs.length) setConfigId(configs.data.configs[0].id);
  }, [configs.data, configId]);
  useEffect(() => {
    api.health().then((h) => { if (h.active_run) setRunId(h.active_run); }).catch(() => undefined);
  }, []);

  const poll = () => {
    if (!runId) return;
    api.run(runId).then((d) => { setDetail(d); setPollError(null); }, (e) => setPollError(e));
  };
  useEffect(poll, [runId]); // eslint-disable-line react-hooks/exhaustive-deps
  const inFlight = !!detail && (detail.state === "starting" || detail.state === "running");
  usePolling(poll, 1000, !!runId && (inFlight || !detail));

  const config = configs.data?.configs.find((c) => c.id === configId) ?? null;
  const shown = validation && validation.id === configId ? validation : config;

  const validate = async () => {
    setValidating(true);
    try { setValidation(await api.validate(configId)); setLaunchError(null); }
    catch (e) { setLaunchError(e as ApiError); }
    finally { setValidating(false); }
  };
  const start = async () => {
    setConfirm(false);
    setLaunchError(null);
    try {
      const r = await api.startRun(configId);
      setDetail(null);
      setRunId(r.run_id);
    } catch (e) {
      const err = e as ApiError;
      setLaunchError(err);
      if (err.code === "run_active" && typeof err.extra.active_run === "string") setRunId(err.extra.active_run);
    }
  };

  if (configs.loading && !configs.data) return <><PageHeader title="Run" /><Spinner label="Loading configurations" /></>;
  if (configs.error) return <><PageHeader title="Run" /><ErrorBox error={configs.error} onRetry={configs.reload} /></>;
  if (!configs.data!.configs.length) return <><PageHeader title="Run" /><Empty title="No trusted configurations">Add a project-relative path to AUTOTESTX_ALLOWED_CONFIGS.</Empty></>;

  return (
    <>
      <PageHeader title="Run configuration and execution"
        subtitle="Only server-side allowlisted configuration files can be run. The browser never sends commands; it picks a configuration by id." />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="1 · Configuration">
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">Trusted configuration</span>
            <select value={configId} onChange={(e) => { setConfigId(e.target.value); setValidation(null); }}
              className="rounded-md border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-900">
              {configs.data!.configs.map((c) => <option key={c.id} value={c.id}>{c.id} ({c.path})</option>)}
            </select>
          </label>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button variant="secondary" onClick={validate} disabled={validating || !configId}>{validating ? "Validating…" : "Validate configuration"}</Button>
            <Button onClick={() => setConfirm(true)} disabled={!configId || inFlight || (shown ? !shown.valid : false)}>Start regression run</Button>
          </div>
          {shown && !shown.valid && <div className="mt-3"><ErrorBox title="Configuration is not valid" error="Fix these problems before running:" /><ul className="mt-2 list-disc pl-5 text-sm text-red-700">{shown.problems.map((p, i) => <li key={i}>{p}</li>)}</ul></div>}
          {validation && validation.id === configId && validation.valid && (
            <div role="status" className="mt-3 rounded border border-emerald-300 bg-emerald-50 p-3 text-sm text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-200">
              Configuration is valid and all required tools were found.
              <ul className="mt-1 text-xs">{validation.tools?.map((t) => <li key={t.role}>{t.role}: {t.found ? t.version || t.path : "MISSING"}</li>)}</ul>
            </div>
          )}
          {launchError && <div className="mt-3"><ErrorBox title={launchError.code === "run_active" ? "A run is already in progress" : "Could not start the run"} error={launchError} /></div>}
        </Card>
        <Card title={`Tests that will run${shown ? ` (${shown.tests.length})` : ""}`}>
          {shown && (
            <div className="overflow-x-auto">
              <table className="w-full">
                <caption className="sr-only">Tests defined in the selected configuration</caption>
                <thead><tr><th className={th}>Test</th><th className={th}>Expected</th><th className={th}>Timeout</th></tr></thead>
                <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                  {shown.tests.map((t) => (
                    <tr key={t.name}>
                      <td className={td}><div className="font-medium">{t.name}</div><div className="text-xs text-slate-500">{t.description}</div></td>
                      <td className={td}><code>{t.expect}</code></td>
                      <td className={td}>{t.timeout_seconds}s</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      {runId && (
        <div className="mt-4">
          <Card title="2 · Execution" actions={detail ? <OverallBadge overall={detail.overall} /> : undefined}>
            <div className="mb-2 text-sm">Run <code>{runId}</code></div>
            {!detail && !pollError && <Spinner label="Waiting for the run to report" />}
            {pollError && <ErrorBox error={pollError} />}
            {detail && (
              <>
                <div className="mb-1 flex justify-between text-sm">
                  <span>{detail.progress.completed} of {detail.progress.total} tests finished{detail.progress.current ? ` · running ${detail.progress.current}` : ""}</span>
                  <span>{fmtDuration(detail.duration_seconds)}</span>
                </div>
                <div role="progressbar" aria-valuemin={0} aria-valuemax={detail.progress.total} aria-valuenow={detail.progress.completed}
                  aria-label="Run progress" className="h-2 overflow-hidden rounded bg-slate-200 dark:bg-slate-800">
                  <div className="h-full bg-blue-600 transition-all" style={{ width: `${detail.progress.total ? (100 * detail.progress.completed) / detail.progress.total : 0}%` }} />
                </div>
                <ul className="mt-3 divide-y divide-slate-200 text-sm dark:divide-slate-800">
                  {detail.progress.tests.map((t) => (
                    <li key={t.name} className="flex items-center justify-between gap-2 py-1.5">
                      <span>{t.name}</span>
                      <span className="flex items-center gap-2">
                        {t.state === "done" ? <><StatusBadge status={t.status} /><span className="text-xs text-slate-500">expected {t.expect}</span></> : <span className="text-xs text-slate-500">{t.state}</span>}
                      </span>
                    </li>
                  ))}
                </ul>
                {detail.state === "completed" && (
                  <div role="status" className="mt-3 text-sm">
                    Finished: {detail.totals?.passed} passed, {detail.totals?.failed} failed, {detail.totals?.timed_out} timed out, {detail.totals?.unexpected} unexpected.{" "}
                    <Link className="text-blue-600 underline dark:text-blue-400" to={`/results?run=${encodeURIComponent(detail.run_id)}`}>View results</Link>
                  </div>
                )}
                {(detail.state === "failed" || detail.state === "interrupted") && (
                  <div className="mt-3">
                    <ErrorBox title={`Run ${detail.state}`} error={detail.error ?? "No details were recorded."} />
                    {detail.console_tail && <pre className="mt-2 max-h-64 overflow-auto rounded bg-slate-100 p-2 text-xs dark:bg-slate-800" aria-label="Run console output">{detail.console_tail}</pre>}
                  </div>
                )}
              </>
            )}
          </Card>
        </div>
      )}

      {confirm && (
        <ConfirmDialog title="Start a regression run?" confirmLabel="Start run" onConfirm={start} onCancel={() => setConfirm(false)}>
          This executes the {shown?.tests.length ?? ""} tests in <code>{configId}</code> on this machine, including the
          simulator and any deliberately slow or hanging negative tests (up to their timeouts). Only one run can be active at a time.
        </ConfirmDialog>
      )}
    </>
  );
}
