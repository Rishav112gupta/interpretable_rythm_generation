import { useState } from "react";
import { Alert, Field, Loading, Modal, Spinner } from "../../components/ui";
import { useAction, useApi } from "../../hooks/useApi";
import { useAuth } from "../../hooks/useAuth";
import { api } from "../../services/api";
import type { Role, User } from "../../types";
import { formatDateTime } from "../../utils/time";

const ROLES: { key: Role; help: string }[] = [
  { key: "admin", help: "Everything: users, settings, Instagram connection" },
  { key: "approver", help: "Approve, reject, schedule and publish posts" },
  { key: "editor", help: "Create, generate and edit content" },
  { key: "viewer", help: "Read-only" },
];

export default function UsersTab() {
  const { tz, user: me } = useAuth();
  const { data, loading, reload } = useApi(() => api.get<User[]>("/users"));
  const { busy, error, run } = useAction();
  const [form, setForm] = useState<{ email: string; full_name: string; password: string; role: Role } | null>(null);
  if (loading || !data) return <Loading />;

  const create = async () => {
    if (!form) return;
    const r = await run("create", () => api.post("/users", form));
    if (r) {
      setForm(null);
      reload();
    }
  };
  const update = async (u: User, body: Record<string, unknown>) => {
    await run(`u${u.id}`, () => api.patch(`/users/${u.id}`, body));
    reload();
  };

  return (
    <div>
      <div className="mb-4 flex justify-between">
        <p className="muted">Roles: {ROLES.map((r) => `${r.key} — ${r.help}`).join(" · ")}</p>
        <button className="btn-primary shrink-0" onClick={() => setForm({ email: "", full_name: "", password: "", role: "editor" })}>
          ✚ Add user
        </button>
      </div>
      {error && !form && <Alert kind="error">{error.message}</Alert>}
      <div className="card overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold text-slate-500 uppercase">
            <tr>
              <th className="px-4 py-2">User</th>
              <th className="px-4 py-2">Role</th>
              <th className="px-4 py-2">Last login</th>
              <th className="px-4 py-2">Active</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.map((u) => (
              <tr key={u.id}>
                <td className="px-4 py-2">
                  <div className="font-medium">{u.full_name || "—"}</div>
                  <div className="text-xs text-slate-500">{u.email}</div>
                </td>
                <td className="px-4 py-2">
                  <select className="input w-36" value={u.role} disabled={u.id === me?.id} onChange={(e) => update(u, { role: e.target.value })}>
                    {ROLES.map((r) => (
                      <option key={r.key}>{r.key}</option>
                    ))}
                  </select>
                </td>
                <td className="px-4 py-2 text-slate-600">{formatDateTime(u.last_login_at, tz)}</td>
                <td className="px-4 py-2">
                  <input type="checkbox" checked={u.is_active} disabled={u.id === me?.id} onChange={(e) => update(u, { is_active: e.target.checked })} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Modal open={!!form} title="Add user" onClose={() => setForm(null)} footer={<button className="btn-primary" onClick={create} disabled={!!busy}>{busy && <Spinner />} Create</button>}>
        {form && (
          <>
            {error && <Alert kind="error">{error.message}</Alert>}
            <Field label="Email">
              <input className="input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
            </Field>
            <Field label="Full name">
              <input className="input" value={form.full_name} onChange={(e) => setForm({ ...form, full_name: e.target.value })} />
            </Field>
            <Field label="Initial password" hint="At least 10 characters. Ask the user to change it after first login.">
              <input className="input" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            </Field>
            <Field label="Role">
              <select className="input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value as Role })}>
                {ROLES.map((r) => (
                  <option key={r.key} value={r.key}>
                    {r.key} — {r.help}
                  </option>
                ))}
              </select>
            </Field>
          </>
        )}
      </Modal>
    </div>
  );
}
