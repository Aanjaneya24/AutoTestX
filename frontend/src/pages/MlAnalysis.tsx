import { useState } from "react";
import { api } from "../api";
import { useAsync } from "../hooks";
import { useRuns } from "../components/useRuns";
import { RunPicker } from "../components/RunPicker";
import type { ModelMetrics } from "../types";
import { Card, Empty, ErrorBox, PageHeader, Spinner, td, th } from "../components/ui";

function Matrix({ labels, m }: { labels: string[]; m: ModelMetrics }) {
  const max = Math.max(1, ...m.confusion_matrix.flat());
  return (
    <div className="overflow-x-auto">
      <table className="text-sm">
        <caption className="sr-only">Confusion matrix: rows are true labels, columns are predicted labels</caption>
        <thead><tr><th className={th}>true ↓ / predicted →</th>{labels.map((l) => <th key={l} className={th}>{l}</th>)}</tr></thead>
        <tbody>
          {m.confusion_matrix.map((row, i) => (
            <tr key={labels[i]}><th scope="row" className={`${th} normal-case`}>{labels[i]}</th>
              {row.map((v, j) => (
                <td key={j} className={`${td} text-center tabular-nums ${i === j ? "font-semibold" : ""}`}
                  style={{ backgroundColor: v ? `rgba(59,130,246,${0.12 + 0.55 * (v / max)})` : undefined }}>{v}</td>))}
            </tr>))}
        </tbody>
      </table>
    </div>
  );
}

function PerClass({ labels, m }: { labels: string[]; m: ModelMetrics }) {
  return (
    <table className="w-full">
      <thead><tr><th className={th}>Class</th><th className={th}>Precision</th><th className={th}>Recall</th><th className={th}>F1</th><th className={th}>Support</th></tr></thead>
      <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
        {labels.map((l) => { const c = m.per_class[l]; return (
          <tr key={l}><td className={td}><code>{l}</code></td><td className={td}>{c.precision.toFixed(2)}</td><td className={td}>{c.recall.toFixed(2)}</td><td className={td}>{c.f1.toFixed(2)}</td><td className={td}>{c.support}</td></tr>); })}
      </tbody>
    </table>
  );
}

export default function MlAnalysis() {
  const ev = useAsync(() => api.mlEvaluation(), []);
  const { list, latest, selected, select } = useRuns();
  const results = useAsync(selected ? () => api.results(selected) : null, [selected]);
  const [which, setWhich] = useState<"ml_model" | "rule_baseline">("ml_model");
  const classified = (results.data?.tests ?? []).filter((t) => t.rule_category || t.ml_prediction).filter((t) => t.status !== "PASS");

  return (
    <>
      <PageHeader title="ML analysis" />
      <div role="note" className="mb-4 rounded-lg border border-blue-300 bg-blue-50 p-3 text-sm text-blue-900 dark:border-blue-900 dark:bg-blue-950 dark:text-blue-200">
        {ev.data?.statement ?? "The ML model classifies the text of a failure log. It does not diagnose hardware defects or establish verified root causes. Test status is never decided by ML."}
      </div>

      <Card title="Failure classification in a run">
        {list.data && <div className="mb-3 max-w-md"><RunPicker label="Run" runs={list.data.runs} latest={latest} value={selected} onChange={select} /></div>}
        {results.loading && <Spinner />}
        {results.error && <ErrorBox error={results.error} onRetry={results.reload} />}
        {results.data && (classified.length === 0 ? <Empty title="No failing tests in this run">Only non-PASS tests are classified.</Empty> : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <caption className="sr-only">Rule-based category versus ML prediction for each non-passing test</caption>
              <thead><tr><th className={th}>Test</th><th className={th}>Rule-based (deterministic)</th><th className={th}>ML prediction (experimental)</th><th className={th}>Confidence</th><th className={th}>Agree?</th></tr></thead>
              <tbody className="divide-y divide-slate-200 dark:divide-slate-800">
                {classified.map((t) => (
                  <tr key={t.name}><td className={td}>{t.name}</td><td className={td}><code>{t.rule_category ?? "-"}</code></td>
                    <td className={td}>{t.ml_prediction ? <code>{t.ml_prediction.label}</code> : <span className="text-slate-500">no prediction</span>}</td>
                    <td className={td}>{t.ml_prediction ? t.ml_prediction.confidence.toFixed(2) : "-"}</td>
                    <td className={td}>{t.ml_prediction ? ((t.ml_prediction.top_label ?? t.ml_prediction.label) === t.rule_category ? "yes" : "no") : "-"}</td></tr>))}
              </tbody>
            </table>
          </div>))}
      </Card>

      <h2 className="mb-2 mt-6 text-lg font-semibold">Saved model evaluation</h2>
      {ev.loading && <Spinner label="Loading evaluation" />}
      {ev.error && (ev.error.status === 404
        ? <Empty title="No saved evaluation">Run <code>python -m autotestx evaluate-ml --out reports/ml_evaluation.json</code> and refresh.</Empty>
        : <ErrorBox error={ev.error} onRetry={ev.reload} />)}
      {ev.data && (() => {
        const e = ev.data.evaluation;
        const labels = ev.data.labels;
        const m = e[which];
        return (
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <Card title="Macro-F1 (same family-grouped folds)">
                <table className="w-full text-sm">
                  <thead><tr><th className={th}>Classifier</th><th className={th}>Macro-F1</th><th className={th}>Accuracy</th></tr></thead>
                  <tbody>
                    <tr><td className={td}>Keyword rules (baseline)</td><td className={`${td} tabular-nums`}>{e.rule_baseline.macro_f1.toFixed(3)}</td><td className={`${td} tabular-nums`}>{e.rule_baseline.accuracy.toFixed(3)}</td></tr>
                    <tr><td className={td}>TF-IDF + Logistic Regression</td><td className={`${td} tabular-nums`}>{e.ml_model.macro_f1.toFixed(3)}</td><td className={`${td} tabular-nums`}>{e.ml_model.accuracy.toFixed(3)}</td></tr>
                  </tbody>
                </table>
                <p className="mt-2 text-sm">{ev.data.baseline_higher ? "On this dataset the keyword-rule baseline scored higher than the ML model." : "The ML model scored at least as high as the baseline on this dataset; see limitations before drawing conclusions."}</p>
              </Card>
              <Card title="Dataset">
                <ul className="space-y-1 text-sm">
                  <li><b>{e.n_samples}</b> samples from <b>{e.n_families}</b> template families ({e.source_types.join(", ")})</li>
                  <li>Class counts: {Object.entries(e.class_counts).map(([k, v]) => `${k} ${v}`).join(", ")}</li>
                  <li className="text-xs text-slate-500">{e.protocol}</li>
                  <li className="text-xs text-slate-500">Single-sample inference ≈ {e.inference_ms_per_sample} ms (n={e.inference_sample_size}); scikit-learn {e.sklearn_version}; evaluated {e.evaluated_at}</li>
                </ul>
              </Card>
            </div>
            <div role="group" aria-label="Classifier shown below" className="flex gap-2">
              <button type="button" aria-pressed={which === "ml_model"} onClick={() => setWhich("ml_model")} className={`rounded-md px-3 py-1.5 text-sm ${which === "ml_model" ? "bg-blue-600 text-white" : "border border-slate-300 dark:border-slate-700"}`}>ML model</button>
              <button type="button" aria-pressed={which === "rule_baseline"} onClick={() => setWhich("rule_baseline")} className={`rounded-md px-3 py-1.5 text-sm ${which === "rule_baseline" ? "bg-blue-600 text-white" : "border border-slate-300 dark:border-slate-700"}`}>Rule baseline</button>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Card title={`Per-class precision and recall · ${which === "ml_model" ? "ML model" : "rule baseline"}`}><PerClass labels={labels} m={m} /></Card>
              <Card title="Confusion matrix"><Matrix labels={labels} m={m} /></Card>
            </div>
            <Card title="Limitations">
              <ul className="list-disc space-y-1 pl-5 text-sm">{ev.data.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
            </Card>
            <Card title="Example misclassifications (ML model)">
              <ul className="space-y-1 text-sm">{e.ml_misclassified_examples.map((x, i) => <li key={i}><code>{x.true}</code> → <code>{x.predicted}</code>: <span className="font-mono text-xs">{x.text.replace(/\n/g, " ⏎ ")}</span></li>)}</ul>
            </Card>
          </div>
        );
      })()}
    </>
  );
}
