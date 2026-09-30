import { useState } from "react";
import { Link } from "react-router-dom";
import { Empty, Loading } from "../../components/ui";
import { useApi } from "../../hooks/useApi";
import { useAuth } from "../../hooks/useAuth";
import { api } from "../../services/api";
import type { IntegrationLog } from "../../types";
import { formatDateTime } from "../../utils/time";

const SOURCES = ["", "instagram", "llm", "image_generation", "google_sheets", "scheduler"];

export default function LogsTab() {
  const { tz } = useAuth();
  const [source, setSource] = useState("");
  const { data, loading } = useApi(() => api.get<IntegrationLog[]>("/logs", { source, limit: 200 }), [source]);
  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <span className="muted">Integration errors and warnings (secrets are redacted).</span>
        <select className="input w-48" value={source} onChange={(e) => setSource(e.target.value)}>
          {SOURCES.map((s) => (
            <option key={s} value={s}>
              {s || "All sources"}
            </option>
          ))}
        </select>
      </div>
      {loading && !data ? (
        <Loading />
      ) : !data?.length ? (
        <Empty title="No log entries" />
      ) : (
        <div className="card divide-y divide-slate-100">
          {data.map((l) => (
            <div key={l.id} className="px-4 py-2 text-sm">
              <div className="flex flex-wrap items-center gap-2">
                <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${l.level === "error" ? "bg-rose-100 text-rose-800" : l.level === "warning" ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-700"}`}>{l.level}</span>
                <span className="text-xs font-medium text-slate-500">{l.source}</span>
                <span className="text-xs text-slate-400">{formatDateTime(l.created_at, tz)}</span>
                {l.post_id && (
                  <Link to={`/posts/${l.post_id}`} className="text-xs text-indigo-600">
                    Post #{l.post_id}
                  </Link>
                )}
              </div>
              <div className="mt-0.5 text-slate-800">{l.message}</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
