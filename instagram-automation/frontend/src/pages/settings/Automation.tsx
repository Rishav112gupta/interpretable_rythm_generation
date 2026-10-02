import { useState } from "react";
import { Alert, Empty, Field, Loading, Modal, Spinner } from "../../components/ui";
import { useAction, useApi } from "../../hooks/useApi";
import { useAuth } from "../../hooks/useAuth";
import { api } from "../../services/api";
import { formatDateTime } from "../../utils/time";

interface ApiKey {
  id: number;
  name: string;
  prefix: string;
  role: string;
  created_at: string;
  last_used_at: string | null;
  revoked_at: string | null;
}
interface Webhook {
  id: number;
  name: string;
  url: string;
  events: string[];
  is_active: boolean;
  last_delivery_at: string | null;
  last_status_code: number | null;
  last_error: string;
}
interface Delivery {
  id: string;
  endpoint_id: number;
  event: string;
  status: string;
  attempts: number;
  last_status_code: number | null;
  last_error: string;
  created_at: string;
  next_attempt_at: string;
}
interface EventDef {
  event: string;
  description: string;
}

function Secret({ label, value, onClose }: { label: string; value: string; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  return (
    <Alert kind="success" title={`${label} — copy it now, it will not be shown again`} onClose={onClose}>
      <div className="mt-2 flex items-center gap-2">
        <code className="flex-1 rounded bg-white px-2 py-1.5 text-xs break-all ring-1 ring-emerald-200">{value}</code>
        <button
          className="btn-secondary text-xs"
          onClick={() => {
            navigator.clipboard?.writeText(value);
            setCopied(true);
          }}
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </Alert>
  );
}

export default function AutomationTab() {
  const { tz } = useAuth();
  const { data, loading, reload } = useApi(() =>
    Promise.all([api.get<ApiKey[]>("/api-keys"), api.get<Webhook[]>("/webhooks"), api.get<EventDef[]>("/webhooks/events"), api.get<Delivery[]>("/webhooks/deliveries", { limit: 30 })]),
  );
  const { busy, error, setError, run } = useAction();
  const [keyForm, setKeyForm] = useState<{ name: string; role: string } | null>(null);
  const [hookForm, setHookForm] = useState<{ id?: number; name: string; url: string; events: string[]; is_active: boolean } | null>(null);
  const [secret, setSecret] = useState<{ label: string; value: string } | null>(null);
  const [testResult, setTestResult] = useState<Delivery | null>(null);

  if (loading && !data) return <Loading />;
  if (!data) return null;
  const [keys, hooks, events, deliveries] = data;

  const createKey = async () => {
    if (!keyForm) return;
    const r = await run("key", () => api.post<ApiKey & { key: string }>("/api-keys", keyForm));
    if (r) {
      setSecret({ label: `API key "${r.name}"`, value: r.key });
      setKeyForm(null);
      reload();
    }
  };
  const revokeKey = async (k: ApiKey) => {
    if (!confirm(`Revoke API key "${k.name}"? Anything using it (e.g. n8n) will stop working immediately.`)) return;
    await run("revoke", () => api.del(`/api-keys/${k.id}`));
    reload();
  };
  const saveHook = async () => {
    if (!hookForm) return;
    const { id, ...body } = hookForm;
    const r = await run("hook", () => (id ? api.put<Webhook>(`/webhooks/${id}`, body) : api.post<Webhook & { secret: string }>("/webhooks", body)));
    if (r) {
      if ("secret" in r) setSecret({ label: `Signing secret for "${r.name}"`, value: (r as { secret: string }).secret });
      setHookForm(null);
      reload();
    }
  };
  const testHook = async (w: Webhook) => {
    setTestResult(null);
    const r = await run(`test${w.id}`, () => api.post<Delivery>(`/webhooks/${w.id}/test`));
    if (r) setTestResult(r);
    reload();
  };
  const rotate = async (w: Webhook) => {
    if (!confirm("Create a new signing secret? Update it in n8n afterwards.")) return;
    const r = await run("rotate", () => api.post<{ secret: string; name: string }>(`/webhooks/${w.id}/rotate-secret`));
    if (r) setSecret({ label: `New signing secret for "${r.name}"`, value: r.secret });
  };
  const removeHook = async (w: Webhook) => {
    if (!confirm(`Delete webhook "${w.name}"?`)) return;
    await run("del", () => api.del(`/webhooks/${w.id}`));
    reload();
  };
  const hookName = (id: number) => hooks.find((h) => h.id === id)?.name ?? `#${id}`;

  return (
    <div className="space-y-6">
      <Alert kind="info" title="Connect n8n (or any automation tool)">
        <strong>n8n → this app:</strong> create an API key and send it as the <code>X-API-Key</code> header from n8n's HTTP Request node (e.g. create draft posts from a form or email).{" "}
        <strong>This app → n8n:</strong> add a webhook with the URL of an n8n Webhook node to receive events such as “needs review”, “published” or “failed”. Publishing and approval always stay in this app. Guide: docs/N8N.md.
      </Alert>
      {secret && <Secret label={secret.label} value={secret.value} onClose={() => setSecret(null)} />}
      {error && (
        <Alert kind="error" onClose={() => setError(null)}>
          {error.message}
        </Alert>
      )}
      {testResult && (
        <Alert kind={testResult.status === "success" ? "success" : "error"} title={testResult.status === "success" ? "Test event delivered" : "Test event failed"} onClose={() => setTestResult(null)}>
          {testResult.status === "success" ? `The receiver answered HTTP ${testResult.last_status_code}.` : testResult.last_error || "No response."}
        </Alert>
      )}

      <div className="card p-5">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h2 className="h2">API keys</h2>
            <p className="muted">Recommended role for n8n: <strong>editor</strong> (can create and generate drafts, cannot approve or publish).</p>
          </div>
          <button className="btn-primary" onClick={() => setKeyForm({ name: "n8n", role: "editor" })}>
            ✚ New API key
          </button>
        </div>
        {keys.length === 0 ? (
          <Empty title="No API keys" />
        ) : (
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="text-left text-xs font-semibold text-slate-500 uppercase">
              <tr>
                <th className="py-2">Name</th>
                <th>Key</th>
                <th>Role</th>
                <th>Last used</th>
                <th>Status</th>
                <th />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {keys.map((k) => (
                <tr key={k.id} className={k.revoked_at ? "opacity-50" : ""}>
                  <td className="py-2 font-medium">{k.name}</td>
                  <td className="font-mono text-xs">{k.prefix}…</td>
                  <td>{k.role}</td>
                  <td className="text-slate-600">{formatDateTime(k.last_used_at, tz)}</td>
                  <td>{k.revoked_at ? "Revoked" : "Active"}</td>
                  <td className="text-right">
                    {!k.revoked_at && (
                      <button className="btn-ghost text-xs text-rose-600" onClick={() => revokeKey(k)}>
                        Revoke
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <div className="card p-5">
        <div className="mb-3 flex items-center justify-between">
          <div>
            <h2 className="h2">Outgoing webhooks</h2>
            <p className="muted">Each request is signed (X-IA-Signature, HMAC-SHA256). Failed deliveries are retried for about 1.5 hours.</p>
          </div>
          <button className="btn-primary" onClick={() => setHookForm({ name: "n8n", url: "http://n8n:5678/webhook/instagram-events", events: ["*"], is_active: true })}>
            ✚ New webhook
          </button>
        </div>
        {hooks.length === 0 ? (
          <Empty title="No webhooks" />
        ) : (
          <div className="space-y-3">
            {hooks.map((w) => (
              <div key={w.id} className="rounded-lg border border-slate-200 p-3 text-sm">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <div className="font-medium">
                      {w.name} {!w.is_active && <span className="text-xs text-slate-500">(disabled)</span>}
                    </div>
                    <div className="truncate font-mono text-xs text-slate-600">{w.url}</div>
                    <div className="mt-1 text-xs text-slate-500">Events: {w.events.includes("*") ? "all" : w.events.join(", ")}</div>
                    <div className="text-xs text-slate-500">
                      Last delivery: {formatDateTime(w.last_delivery_at, tz)}
                      {w.last_status_code != null && ` · HTTP ${w.last_status_code}`}
                      {w.last_error && <span className="text-rose-700"> · {w.last_error}</span>}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    <button className="btn-secondary text-xs" onClick={() => testHook(w)} disabled={!!busy || !w.is_active}>
                      {busy === `test${w.id}` && <Spinner />} Send test
                    </button>
                    <button className="btn-ghost text-xs" onClick={() => setHookForm({ id: w.id, name: w.name, url: w.url, events: w.events, is_active: w.is_active })}>
                      Edit
                    </button>
                    <button className="btn-ghost text-xs" onClick={() => rotate(w)}>
                      New secret
                    </button>
                    <button className="btn-ghost text-xs text-rose-600" onClick={() => removeHook(w)}>
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="card p-5">
        <h2 className="h2 mb-3">Recent deliveries</h2>
        {deliveries.length === 0 ? (
          <p className="muted">Nothing sent yet.</p>
        ) : (
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="text-left text-xs font-semibold text-slate-500 uppercase">
              <tr>
                <th className="py-2">Time</th>
                <th>Webhook</th>
                <th>Event</th>
                <th>Status</th>
                <th>Attempts</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {deliveries.map((d) => (
                <tr key={d.id}>
                  <td className="py-1.5 whitespace-nowrap text-slate-600">{formatDateTime(d.created_at, tz)}</td>
                  <td>{hookName(d.endpoint_id)}</td>
                  <td className="font-mono text-xs">{d.event}</td>
                  <td>
                    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${d.status === "success" ? "bg-emerald-100 text-emerald-800" : d.status === "failed" ? "bg-rose-100 text-rose-800" : "bg-amber-100 text-amber-800"}`}>{d.status}</span>
                  </td>
                  <td>{d.attempts}</td>
                  <td className="max-w-xs truncate text-xs text-slate-500">{d.status === "pending" && d.attempts > 0 ? `retry ${formatDateTime(d.next_attempt_at, tz)} · ` : ""}{d.last_error}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <Modal open={!!keyForm} title="New API key" onClose={() => setKeyForm(null)} footer={<button className="btn-primary" onClick={createKey} disabled={!keyForm?.name || !!busy}>{busy === "key" && <Spinner />} Create key</button>}>
        {keyForm && (
          <>
            <Field label="Name" hint="e.g. n8n production">
              <input className="input" value={keyForm.name} onChange={(e) => setKeyForm({ ...keyForm, name: e.target.value })} />
            </Field>
            <Field label="Role" hint="Admin keys are not allowed. Approver keys can approve and publish — only use them if you deliberately automate approval.">
              <select className="input" value={keyForm.role} onChange={(e) => setKeyForm({ ...keyForm, role: e.target.value })}>
                <option value="viewer">viewer — read only</option>
                <option value="editor">editor — create/generate drafts (recommended)</option>
                <option value="approver">approver — can also approve/publish</option>
              </select>
            </Field>
          </>
        )}
      </Modal>

      <Modal wide open={!!hookForm} title={hookForm?.id ? "Edit webhook" : "New webhook"} onClose={() => setHookForm(null)} footer={<button className="btn-primary" onClick={saveHook} disabled={!!busy}>{busy === "hook" && <Spinner />} Save</button>}>
        {hookForm && (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Name">
                <input className="input" value={hookForm.name} onChange={(e) => setHookForm({ ...hookForm, name: e.target.value })} />
              </Field>
              <Field label="URL" hint="n8n Webhook node “Production URL”. Inside docker compose: http://n8n:5678/webhook/…">
                <input className="input" value={hookForm.url} onChange={(e) => setHookForm({ ...hookForm, url: e.target.value })} />
              </Field>
            </div>
            <div>
              <div className="label">Events</div>
              <label className="mb-2 flex items-center gap-2 text-sm font-medium">
                <input type="checkbox" checked={hookForm.events.includes("*")} onChange={(e) => setHookForm({ ...hookForm, events: e.target.checked ? ["*"] : [] })} /> All events
              </label>
              {!hookForm.events.includes("*") && (
                <div className="grid gap-1 sm:grid-cols-2">
                  {events
                    .filter((ev) => ev.event !== "webhook.test")
                    .map((ev) => (
                      <label key={ev.event} className="flex items-start gap-2 text-sm" title={ev.description}>
                        <input
                          type="checkbox"
                          className="mt-1"
                          checked={hookForm.events.includes(ev.event)}
                          onChange={(e) => setHookForm({ ...hookForm, events: e.target.checked ? [...hookForm.events, ev.event] : hookForm.events.filter((x) => x !== ev.event) })}
                        />
                        <span>
                          <span className="font-mono text-xs">{ev.event}</span>
                          <span className="block text-xs text-slate-500">{ev.description}</span>
                        </span>
                      </label>
                    ))}
                </div>
              )}
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={hookForm.is_active} onChange={(e) => setHookForm({ ...hookForm, is_active: e.target.checked })} /> Active
            </label>
          </>
        )}
      </Modal>
    </div>
  );
}
