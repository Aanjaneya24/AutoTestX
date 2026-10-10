import { useEffect, useRef, type ReactNode } from "react";
import type { ApiError } from "../api";
import type { Outcome, Overall } from "../types";

const base = "inline-flex items-center rounded px-2 py-0.5 text-xs font-medium whitespace-nowrap";

export function StatusBadge({ status }: { status: string | null | undefined }) {
  const map: Record<string, string> = {
    PASS: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
    FAIL: "bg-red-100 text-red-800 dark:bg-red-950 dark:text-red-300",
    ERROR: "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-300",
    TIMEOUT: "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-300",
  };
  return <span className={`${base} ${map[status ?? ""] ?? "bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300"}`}>{status ?? "-"}</span>;
}

/** Expected-vs-actual label. An expected negative test is never shown as a success. */
export function OutcomeBadge({ outcome, expected, actual }: { outcome: Outcome; expected: string; actual: string | null }) {
  switch (outcome) {
    case "passed":
      return <span className={`${base} bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300`}>Passed</span>;
    case "expected_failure":
      return <span className={`${base} bg-sky-100 text-sky-800 dark:bg-sky-950 dark:text-sky-300`} title="This negative test was supposed to end this way">Expected {actual}</span>;
    case "unexpected_failure":
      return <span className={`${base} bg-red-600 text-white`}>UNEXPECTED {actual} (wanted {expected})</span>;
    case "unexpected_pass":
      return <span className={`${base} bg-red-600 text-white`}>UNEXPECTED PASS (wanted {expected})</span>;
    default:
      return <span className={`${base} bg-slate-200 text-slate-700 dark:bg-slate-800 dark:text-slate-300`}>{outcome}</span>;
  }
}

export function OverallBadge({ overall }: { overall: Overall }) {
  const text: Record<string, [string, string]> = {
    as_expected: ["All results as expected", "bg-emerald-600 text-white"],
    unexpected_results: ["Unexpected results", "bg-red-600 text-white"],
    running: ["Running", "bg-blue-600 text-white"],
    starting: ["Starting", "bg-blue-600 text-white"],
    failed: ["Run failed", "bg-red-600 text-white"],
    interrupted: ["Interrupted", "bg-amber-600 text-white"],
    completed: ["Completed", "bg-slate-600 text-white"],
  };
  const [label, cls] = text[overall] ?? [overall, "bg-slate-600 text-white"];
  return <span className={`${base} ${cls}`}>{label}</span>;
}

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      {(title || actions) && (
        <div className="mb-3 flex items-center justify-between gap-2">
          {title && <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: string; tone?: "good" | "bad" | "warn" }) {
  const color = tone === "good" ? "text-emerald-600 dark:text-emerald-400" : tone === "bad" ? "text-red-600 dark:text-red-400" : tone === "warn" ? "text-amber-600 dark:text-amber-400" : "";
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</div>
      <div className={`mt-1 text-3xl font-semibold tabular-nums ${color}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</div>}
    </div>
  );
}

export function Button({ variant = "primary", className = "", ...props }: React.ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const v = variant === "primary" ? "bg-blue-600 text-white hover:bg-blue-700 disabled:bg-blue-300"
    : variant === "danger" ? "bg-red-600 text-white hover:bg-red-700 disabled:bg-red-300"
    : "border border-slate-300 bg-white text-slate-800 hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100 dark:hover:bg-slate-800";
  return <button type="button" {...props} className={`rounded-md px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed ${v} ${className}`} />;
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 py-6 text-sm text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-blue-600" aria-hidden />
      {label}…
    </div>
  );
}

export function ErrorBox({ error, onRetry, title = "Something went wrong" }: { error: ApiError | Error | string; onRetry?: () => void; title?: string }) {
  const message = typeof error === "string" ? error : error.message;
  const problems = typeof error === "object" && "problems" in error ? (error as ApiError).problems : [];
  return (
    <div role="alert" className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
      <div className="font-semibold">{title}</div>
      <div className="mt-1">{message}</div>
      {problems.length > 0 && <ul className="mt-2 list-disc pl-5">{problems.map((p, i) => <li key={i}>{p}</li>)}</ul>}
      {onRetry && <Button variant="secondary" className="mt-3" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 p-8 text-center dark:border-slate-700">
      <div className="font-medium">{title}</div>
      {children && <div className="mt-1 text-sm text-slate-500 dark:text-slate-400">{children}</div>}
    </div>
  );
}

export function ConfirmDialog({ title, children, confirmLabel, onConfirm, onCancel }: {
  title: string; children: ReactNode; confirmLabel: string; onConfirm: () => void; onCancel: () => void;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div role="dialog" aria-modal="true" aria-labelledby="confirm-title" className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl dark:bg-slate-900">
        <h2 id="confirm-title" className="text-lg font-semibold">{title}</h2>
        <div className="mt-2 text-sm text-slate-600 dark:text-slate-300">{children}</div>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="secondary" onClick={onCancel}>Cancel</Button>
          <button ref={ref} type="button" onClick={onConfirm} className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700">{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <header className="mb-5 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-slate-500 dark:text-slate-400">{subtitle}</p>}
      </div>
      {actions}
    </header>
  );
}

export const th = "px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400";
export const td = "px-3 py-2 align-top text-sm";
