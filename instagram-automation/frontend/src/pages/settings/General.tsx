import { useState } from "react";
import { Alert, Field, Spinner } from "../../components/ui";
import { useAction } from "../../hooks/useApi";
import { useAuth } from "../../hooks/useAuth";
import { api } from "../../services/api";

const COMMON_TZ = ["Asia/Kolkata", "Asia/Dubai", "Asia/Singapore", "Europe/London", "Europe/Berlin", "America/New_York", "America/Los_Angeles", "Australia/Sydney", "UTC"];

export default function GeneralTab() {
  const { settings, refreshSettings, can } = useAuth();
  const { busy, error, run } = useAction();
  const [tz, setTz] = useState(settings?.timezone ?? "Asia/Kolkata");
  const [pw, setPw] = useState({ current_password: "", new_password: "" });
  const [pwOk, setPwOk] = useState(false);
  if (!settings) return null;
  const admin = can("admin");

  const save = async (body: Record<string, unknown>) => {
    await run("save", () => api.patch("/settings", body));
    await refreshSettings();
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="card space-y-4 p-5">
        <h2 className="h2">Scheduling</h2>
        {error && <Alert kind="error">{error.message}</Alert>}
        <Field label="Company timezone" hint="All dates in the dashboard and new schedules use this timezone.">
          <div className="flex gap-2">
            <input className="input" list="tzlist" value={tz} onChange={(e) => setTz(e.target.value)} disabled={!admin} />
            <datalist id="tzlist">
              {COMMON_TZ.map((t) => (
                <option key={t} value={t} />
              ))}
            </datalist>
            {admin && (
              <button className="btn-primary" onClick={() => save({ timezone: tz })} disabled={!!busy || tz === settings.timezone}>
                {busy === "save" && <Spinner />} Save
              </button>
            )}
          </div>
        </Field>
        <div className="flex items-center justify-between rounded-lg border border-slate-200 p-3">
          <div>
            <div className="font-medium">Publishing</div>
            <div className="text-sm text-slate-500">Emergency switch. When paused, nothing is published to Instagram (manual or scheduled).</div>
          </div>
          {admin && (
            <button className={settings.publishing_enabled ? "btn-danger" : "btn-success"} onClick={() => save({ publishing_enabled: !settings.publishing_enabled })} disabled={!!busy}>
              {settings.publishing_enabled ? "Pause publishing" : "Resume publishing"}
            </button>
          )}
        </div>
      </div>

      <div className="card space-y-3 p-5">
        <h2 className="h2">Connected services</h2>
        <p className="muted">Configured through environment variables on the server (see README). Secrets are never shown here.</p>
        <table className="w-full text-sm">
          <tbody className="divide-y divide-slate-100">
            {Object.entries(settings.providers).map(([k, v]) => (
              <tr key={k}>
                <td className="py-2 font-medium text-slate-600 capitalize">{k.replace("_", " ")}</td>
                <td className="py-2 text-right">
                  <span className={`rounded px-2 py-0.5 text-xs font-medium ${v === "mock" ? "bg-amber-100 text-amber-800" : "bg-slate-100 text-slate-700"}`}>{v || "—"}</span>
                </td>
              </tr>
            ))}
            <tr>
              <td className="py-2 font-medium text-slate-600">Public base URL</td>
              <td className="py-2 text-right text-xs">{settings.public_base_url}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="card space-y-3 p-5">
        <h2 className="h2">Change my password</h2>
        {pwOk && <Alert kind="success">Password changed.</Alert>}
        <Field label="Current password">
          <input className="input" type="password" value={pw.current_password} onChange={(e) => setPw({ ...pw, current_password: e.target.value })} />
        </Field>
        <Field label="New password" hint="At least 10 characters">
          <input className="input" type="password" value={pw.new_password} onChange={(e) => setPw({ ...pw, new_password: e.target.value })} />
        </Field>
        <button
          className="btn-primary"
          disabled={pw.new_password.length < 10 || !!busy}
          onClick={async () => {
            setPwOk(false);
            const ok = await run("pw", () => api.post("/auth/change-password", pw).then(() => true));
            if (ok) {
              setPwOk(true);
              setPw({ current_password: "", new_password: "" });
            }
          }}
        >
          Change password
        </button>
      </div>
    </div>
  );
}
