import { useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useAsync } from "../hooks";

/** Run list plus the currently selected run (from ?run=, defaulting to the latest). */
export function useRuns() {
  const [params, setParams] = useSearchParams();
  const list = useAsync(() => api.runs(100), []);
  const latest = list.data?.latest ?? null;
  const selected = params.get("run") || latest || "";
  const select = (id: string) => {
    const next = new URLSearchParams(params);
    next.set("run", id);
    next.delete("test");
    next.delete("line");
    setParams(next);
  };
  return { list, latest, selected, select, params, setParams };
}
