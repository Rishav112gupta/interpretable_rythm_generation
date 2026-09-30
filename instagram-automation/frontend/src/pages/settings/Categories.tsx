import { useState } from "react";
import { Alert, Field, Loading, Modal, Spinner } from "../../components/ui";
import { useAction, useApi } from "../../hooks/useApi";
import { useAuth } from "../../hooks/useAuth";
import { api } from "../../services/api";
import type { Category, Template } from "../../types";

type Form = Omit<Category, "id"> & { id?: number };
const blank: Form = { key: "", name: "", description: "", ai_guidance: "", color: "#6366f1", default_template_id: null, is_active: true, sort_order: 100 };

export default function CategoriesTab() {
  const { can } = useAuth();
  const { data, loading, reload } = useApi(() => Promise.all([api.get<Category[]>("/categories", { include_inactive: true }), api.get<Template[]>("/templates")]));
  const { busy, error, run } = useAction();
  const [form, setForm] = useState<Form | null>(null);
  if (loading || !data) return <Loading />;
  const [cats, templates] = data;
  const admin = can("admin");

  const save = async () => {
    if (!form) return;
    const { id, key, ...rest } = form;
    const r = await run("save", () => (id ? api.patch(`/categories/${id}`, rest) : api.post("/categories", { key, ...rest })));
    if (r) {
      setForm(null);
      reload();
    }
  };

  return (
    <div>
      <div className="mb-4 flex justify-between">
        <p className="muted">Categories drive AI guidance and the default design template. Deactivate instead of deleting so history stays intact.</p>
        {admin && (
          <button className="btn-primary" onClick={() => setForm({ ...blank })}>
            ✚ New category
          </button>
        )}
      </div>
      <div className="card overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200 text-sm">
          <thead className="bg-slate-50 text-left text-xs font-semibold text-slate-500 uppercase">
            <tr>
              <th className="px-4 py-2">Category</th>
              <th className="px-4 py-2">Key</th>
              <th className="px-4 py-2">Template</th>
              <th className="px-4 py-2">AI guidance</th>
              <th className="px-4 py-2">Status</th>
              <th />
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {cats.map((c) => (
              <tr key={c.id} className={c.is_active ? "" : "opacity-50"}>
                <td className="px-4 py-2 font-medium">
                  <span className="mr-2 inline-block h-3 w-3 rounded-sm align-middle" style={{ background: c.color }} />
                  {c.name}
                </td>
                <td className="px-4 py-2 font-mono text-xs">{c.key}</td>
                <td className="px-4 py-2">{templates.find((t) => t.id === c.default_template_id)?.name ?? "—"}</td>
                <td className="max-w-sm truncate px-4 py-2 text-slate-600">{c.ai_guidance}</td>
                <td className="px-4 py-2">{c.is_active ? "Active" : "Inactive"}</td>
                <td className="px-4 py-2 text-right">
                  {admin && (
                    <button className="btn-ghost text-xs" onClick={() => setForm({ ...c })}>
                      Edit
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Modal open={!!form} title={form?.id ? "Edit category" : "New category"} onClose={() => setForm(null)} footer={<button className="btn-primary" onClick={save} disabled={!!busy}>{busy && <Spinner />} Save</button>}>
        {form && (
          <>
            {error && <Alert kind="error">{error.message}</Alert>}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Key" hint="UPPER_CASE, cannot change later">
                <input className="input font-mono" value={form.key} disabled={!!form.id} onChange={(e) => setForm({ ...form, key: e.target.value.toUpperCase().replace(/[^A-Z0-9_]/g, "_") })} />
              </Field>
              <Field label="Name">
                <input className="input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              </Field>
            </div>
            <Field label="Description">
              <input className="input" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </Field>
            <Field label="AI guidance" hint="Extra instructions for the AI for this category">
              <textarea className="input" rows={3} value={form.ai_guidance} onChange={(e) => setForm({ ...form, ai_guidance: e.target.value })} />
            </Field>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="Colour">
                <input type="color" className="h-10 w-full rounded border border-slate-300" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} />
              </Field>
              <Field label="Default template">
                <select className="input" value={form.default_template_id ?? ""} onChange={(e) => setForm({ ...form, default_template_id: e.target.value ? Number(e.target.value) : null })}>
                  <option value="">—</option>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Sort order">
                <input type="number" className="input" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: Number(e.target.value) })} />
              </Field>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} /> Active
            </label>
          </>
        )}
      </Modal>
    </div>
  );
}
