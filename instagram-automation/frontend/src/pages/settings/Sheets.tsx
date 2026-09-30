import { useState } from "react";
import { Alert, Loading, Spinner } from "../../components/ui";
import { useAction, useApi } from "../../hooks/useApi";
import { useAuth } from "../../hooks/useAuth";
import { api } from "../../services/api";
import { formatDateTime } from "../../utils/time";

interface SheetsStatus {
  enabled: boolean;
  mock: boolean;
  sheet_id_configured: boolean;
  worksheet: string;
  auto_sync: boolean;
  last_synced_at: string | null;
  columns: string[];
}

export default function SheetsTab() {
  const { tz, can, refreshSettings } = useAuth();
  const { data: s, loading, reload } = useApi(() => api.get<SheetsStatus>("/sheets/status"));
  const { busy, error, run } = useAction();
  const [result, setResult] = useState<string | null>(null);
  const [rows, setRows] = useState<string[][] | null>(null);
  if (loading || !s) return <Loading />;

  const sync = async () => {
    const r = await run("sync", () => api.post<{ imported: number; updated: number; appended: number; mock: boolean }>("/sheets/sync"));
    if (r) {
      setResult(`Imported ${r.imported} new topic row(s) as drafts, updated ${r.updated} row(s), added ${r.appended} row(s)${r.mock ? " (mock sheet)" : ""}.`);
      reload();
      if (r.mock) setRows((await api.get<{ rows: string[][] }>("/sheets/preview")).rows);
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        {s.mock && <Alert kind="warning" title="Mock mode (MOCK_GOOGLE_SHEETS=true)">Sync runs against an in-memory sheet so you can see exactly what would be written. Configure a service account to use a real Google Sheet (README → Google Sheets).</Alert>}
        {!s.enabled && <Alert kind="info">Google Sheets is disabled. Set GOOGLE_SHEETS_ENABLED=true and the Google variables in .env.</Alert>}
        {error && <Alert kind="error">{error.message}</Alert>}
        {result && <Alert kind="success">{result}</Alert>}
        <div className="card space-y-3 p-5">
          <h2 className="h2">Synchronisation</h2>
          <p className="text-sm text-slate-700">
            PostgreSQL is the source of truth. Each sync (1) turns new sheet rows that have a <em>Topic</em> but no <em>Post ID</em> into draft posts, then (2) writes every post's current status, caption, schedule and Instagram URL back to the sheet.
          </p>
          <div className="text-sm">
            Worksheet: <strong>{s.worksheet}</strong> · Last sync: {formatDateTime(s.last_synced_at, tz)}
          </div>
          <div className="flex flex-wrap gap-2">
            {can("approver") && (
              <button className="btn-primary" onClick={sync} disabled={!s.enabled || !!busy}>
                {busy === "sync" && <Spinner />} Sync now
              </button>
            )}
            {can("admin") && (
              <button
                className="btn-secondary"
                disabled={!!busy}
                onClick={async () => {
                  await run("auto", () => api.patch("/settings", { sheets_auto_sync: !s.auto_sync }));
                  await refreshSettings();
                  reload();
                }}
              >
                Auto-sync every 30 min: {s.auto_sync ? "ON" : "OFF"}
              </button>
            )}
          </div>
        </div>
        {rows && (
          <div className="card overflow-x-auto p-3">
            <table className="min-w-full text-xs">
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className={i === 0 ? "bg-slate-100 font-semibold" : "border-t border-slate-100"}>
                    {r.map((c, j) => (
                      <td key={j} className="max-w-48 truncate px-2 py-1">
                        {c}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <div className="card p-5 text-sm">
        <h2 className="h2 mb-2">Sheet columns</h2>
        <ol className="list-decimal space-y-0.5 pl-5 text-slate-700">
          {s.columns.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ol>
        <p className="mt-3 text-xs text-slate-500">To request content from the sheet, add a row with Category (e.g. EXAM), Topic, Target Audience and Status “NEW”, leaving Post ID empty.</p>
      </div>
    </div>
  );
}
