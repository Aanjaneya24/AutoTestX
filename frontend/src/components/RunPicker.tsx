import type { RunSummary } from "../types";
import { fmtTime } from "../format";

export function runLabel(r: RunSummary, latest: string | null): string {
  const tag = r.run_id === latest ? "LATEST · " : "";
  return `${tag}${r.run_id} · ${fmtTime(r.started)} · ${r.state}`;
}

export function RunPicker({ label, runs, latest, value, onChange, onlyCompleted = false }: {
  label: string; runs: RunSummary[]; latest: string | null; value: string; onChange: (id: string) => void; onlyCompleted?: boolean;
}) {
  const list = onlyCompleted ? runs.filter((r) => r.state === "completed") : runs;
  return (
    <label className="flex flex-col gap-1 text-sm">
      <span className="font-medium">{label}</span>
      <select value={value} onChange={(e) => onChange(e.target.value)}
        className="min-w-0 rounded-md border border-slate-300 bg-white px-2 py-1.5 dark:border-slate-700 dark:bg-slate-900">
        {list.map((r) => <option key={r.run_id} value={r.run_id}>{runLabel(r, latest)}</option>)}
      </select>
    </label>
  );
}
