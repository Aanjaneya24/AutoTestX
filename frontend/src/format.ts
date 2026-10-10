export function fmtDuration(s: number | null | undefined): string {
  if (s === null || s === undefined) return "n/a";
  if (s < 60) return `${s.toFixed(s < 10 ? 2 : 1)} s`;
  return `${Math.floor(s / 60)} m ${Math.round(s % 60)} s`;
}
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "n/a";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}
export function fmtBytes(n: number | null | undefined): string {
  if (n === null || n === undefined) return "n/a";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KiB`;
  return `${(n / 1024 / 1024).toFixed(1)} MiB`;
}
export const pct = (x: number) => `${(x * 100).toFixed(0)}%`;
