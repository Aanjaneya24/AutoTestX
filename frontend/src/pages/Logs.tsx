import { useEffect, useState } from "react";
import { api, ApiError } from "../api";
import { useAsync } from "../hooks";
import { useRuns } from "../components/useRuns";
import { RunPicker } from "../components/RunPicker";
import { fmtBytes } from "../format";
import type { LogChunk, LogSearch } from "../types";
import { Button, Card, Empty, ErrorBox, PageHeader, Spinner } from "../components/ui";

const CHUNK = 65536;

export default function Logs() {
  const { list, latest, selected, select, params, setParams } = useRuns();
  const results = useAsync(selected ? () => api.results(selected) : null, [selected]);
  const test = params.get("test") ?? "";
  const targetLine = params.get("line") ? Number(params.get("line")) : null;

  const [chunk, setChunk] = useState<LogChunk | null>(null);
  const [text, setText] = useState("");
  const [startLine, setStartLine] = useState(1);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(false);
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState<LogSearch | null>(null);
  const [searchError, setSearchError] = useState<ApiError | null>(null);

  const load = async (opts: Parameters<typeof api.log>[2], append = false) => {
    setLoading(true);
    try {
      const c = await api.log(selected, test, { limit: CHUNK, ...opts });
      setChunk(c);
      setError(null);
      if (append) setText((t) => t + c.text); else { setText(c.text); setStartLine(c.start_line); }
    } catch (e) { setError(e as ApiError); setChunk(null); setText(""); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    setSearch(null); setSearchError(null);
    if (selected && test) void load(targetLine ? { around_line: targetLine } : { offset: 0 });
    else { setChunk(null); setText(""); setError(null); }
  }, [selected, test, targetLine]); // eslint-disable-line react-hooks/exhaustive-deps

  const setTest = (name: string) => {
    const next = new URLSearchParams(params);
    next.set("test", name); next.delete("line");
    setParams(next);
  };
  const goLine = (n: number) => {
    const next = new URLSearchParams(params);
    next.set("line", String(n));
    setParams(next);
  };
  const runSearch = async () => {
    if (!query.trim()) return;
    try { setSearch(await api.searchLog(selected, test, query.trim())); setSearchError(null); }
    catch (e) { setSearchError(e as ApiError); setSearch(null); }
  };

  if (list.loading && !list.data) return <><PageHeader title="Log explorer" /><Spinner label="Loading runs" /></>;
  if (list.error) return <><PageHeader title="Log explorer" /><ErrorBox error={list.error} onRetry={list.reload} /></>;
  if (!list.data!.runs.length) return <><PageHeader title="Log explorer" /><Empty title="No runs yet" /></>;

  const lines = text.split("\n");
  if (lines.length && lines[lines.length - 1] === "") lines.pop();
  const tests = results.data?.tests ?? [];
  const findings = chunk?.findings ?? tests.find((t) => t.name === test)?.findings ?? [];

  return (
    <>
      <PageHeader title="Log explorer" subtitle={`Logs are served in ${fmtBytes(CHUNK)} pieces from the server; the browser never loads a whole log at once.`} />
      <div className="mb-4 flex flex-wrap items-end gap-3">
        <div className="min-w-72"><RunPicker label="Run" runs={list.data!.runs} latest={latest} value={selected} onChange={select} /></div>
        <label className="flex flex-col gap-1 text-sm"><span className="font-medium">Test</span>
          <select value={test} onChange={(e) => setTest(e.target.value)} className="rounded-md border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-900">
            <option value="">Select a test…</option>
            {tests.map((t) => <option key={t.name} value={t.name}>{t.name}{t.log_available ? "" : " (no log)"}</option>)}
          </select></label>
      </div>
      {!test && <Empty title="Choose a test to view its log">Or open a failed test from the Results page.</Empty>}
      {test && error && <ErrorBox title={error.code === "log_missing" ? "Log file is missing" : "Could not load the log"} error={error} onRetry={() => load({ offset: 0 })} />}
      {test && loading && !chunk && <Spinner label="Loading log" />}
      {test && chunk && (
        <div className="grid gap-4 xl:grid-cols-3">
          <div className="xl:col-span-2">
            <Card title={`${test}.log · ${fmtBytes(chunk.size)}`} actions={
              <div className="flex gap-2">
                <Button variant="secondary" onClick={() => load({ offset: 0 })}>From start</Button>
                <Button variant="secondary" onClick={() => load({ tail: true })}>Jump to end</Button>
              </div>}>
              {chunk.log_truncated && (
                <div role="note" className="mb-2 rounded bg-amber-100 p-2 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
                  This log was truncated by the engine ({fmtBytes(chunk.log_bytes_total)} produced). The middle section was dropped; look for the “LOG TRUNCATED” marker line.
                </div>)}
              {text === "" ? <p className="text-sm text-slate-500">The log is empty at this position.</p> : (
                <pre aria-label={`Log content of ${test}`} className="max-h-[32rem] overflow-auto rounded bg-slate-100 p-2 font-mono text-xs leading-5 dark:bg-slate-950">
                  {lines.map((l, i) => {
                    const n = startLine + i;
                    const hit = findings.find((f) => f.line === n);
                    return (
                      <div key={n} className={n === targetLine ? "bg-yellow-200 dark:bg-yellow-900" : hit ? "bg-red-50 dark:bg-red-950" : ""}>
                        <span className="mr-3 inline-block w-12 select-none text-right text-slate-400">{n}</span>
                        <span>{l}</span>
                      </div>
                    );
                  })}
                </pre>)}
              <div className="mt-2 flex items-center justify-between text-xs text-slate-500">
                <span>bytes {chunk.offset}–{chunk.next_offset} of {chunk.size}</span>
                {chunk.has_more && <Button variant="secondary" disabled={loading} onClick={() => load({ offset: chunk.next_offset }, true)}>Load more</Button>}
              </div>
            </Card>
          </div>
          <div className="space-y-4">
            <Card title="Search this log">
              <form onSubmit={(e) => { e.preventDefault(); void runSearch(); }} className="flex gap-2">
                <input type="search" aria-label="Search log text" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="text to find"
                  className="min-w-0 flex-1 rounded-md border border-slate-300 bg-white px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-900" />
                <Button type="submit" variant="secondary">Search</Button>
              </form>
              {searchError && <div className="mt-2"><ErrorBox error={searchError} /></div>}
              {search && (
                <div className="mt-2 text-sm">
                  <div>{search.total_matches} match(es){search.capped ? ` (first ${search.matches.length} shown)` : ""}</div>
                  <ul className="mt-1 max-h-48 space-y-1 overflow-auto">
                    {search.matches.map((m) => (
                      <li key={m.line}><button type="button" className="text-left text-blue-600 hover:underline dark:text-blue-400" onClick={() => goLine(m.line)}>
                        <span className="tabular-nums">{m.line}:</span> <span className="font-mono text-xs">{m.text}</span></button></li>))}
                  </ul>
                </div>)}
            </Card>
            <Card title={`Parsed findings (${findings.length})`}>
              {findings.length === 0 ? <p className="text-sm text-slate-500">The Perl parser found no markers in this log.</p> : (
                <ul className="max-h-64 space-y-1 overflow-auto text-sm">
                  {findings.map((f, i) => (
                    <li key={i}><button type="button" className="text-left hover:underline" onClick={() => goLine(f.line)}>
                      <code className="mr-1 rounded bg-slate-200 px-1 text-xs dark:bg-slate-800">{f.category}</code>
                      <span className="tabular-nums text-slate-500">line {f.line}</span> <span className="font-mono text-xs">{f.snippet}</span></button></li>))}
                </ul>)}
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
