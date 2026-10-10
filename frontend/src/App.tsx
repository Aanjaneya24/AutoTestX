import { useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import Overview from "./pages/Overview";
import RunPage from "./pages/RunPage";
import Results from "./pages/Results";
import Logs from "./pages/Logs";
import MlAnalysis from "./pages/MlAnalysis";
import Compare from "./pages/Compare";
import { api } from "./api";
import { useAsync } from "./hooks";

const nav = [
  { to: "/", label: "Overview", end: true },
  { to: "/run", label: "Run" },
  { to: "/results", label: "Results" },
  { to: "/logs", label: "Logs" },
  { to: "/ml", label: "ML analysis" },
  { to: "/compare", label: "Compare" },
];

export default function App() {
  const [open, setOpen] = useState(false);
  const health = useAsync(() => api.health(), []);
  const link = ({ isActive }: { isActive: boolean }) =>
    `block rounded-md px-3 py-2 text-sm font-medium ${isActive ? "bg-blue-600 text-white" : "text-slate-700 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-800"}`;
  return (
    <div className="min-h-screen md:flex">
      <aside className="border-b border-slate-200 bg-white md:min-h-screen md:w-56 md:shrink-0 md:border-b-0 md:border-r dark:border-slate-800 dark:bg-slate-900">
        <div className="flex items-center justify-between px-4 py-3">
          <div>
            <div className="text-base font-bold">AutoTestX</div>
            <div className="text-xs text-slate-500">RTL regression dashboard</div>
          </div>
          <button type="button" className="rounded border border-slate-300 px-2 py-1 text-sm md:hidden dark:border-slate-700"
            aria-expanded={open} aria-controls="main-nav" onClick={() => setOpen(!open)}>Menu</button>
        </div>
        <nav id="main-nav" aria-label="Main" className={`${open ? "block" : "hidden"} space-y-1 px-3 pb-3 md:block`}>
          {nav.map((n) => (
            <NavLink key={n.to} to={n.to} end={n.end} className={link} onClick={() => setOpen(false)}>{n.label}</NavLink>
          ))}
        </nav>
        <div className="hidden px-4 py-3 text-xs text-slate-500 md:block">
          {health.error ? <span className="text-red-600">Backend unreachable</span>
            : health.data ? <span>Backend v{health.data.version} · local only</span> : "Checking backend…"}
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-4 md:p-6">
        <Routes>
          <Route path="/" element={<Overview />} />
          <Route path="/run" element={<RunPage />} />
          <Route path="/results" element={<Results />} />
          <Route path="/logs" element={<Logs />} />
          <Route path="/ml" element={<MlAnalysis />} />
          <Route path="/compare" element={<Compare />} />
          <Route path="*" element={<p>Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}
