import { useEffect, useState } from "react";
import { Alert, Field, Loading, Modal, Spinner } from "../../components/ui";
import { useAction, useApi } from "../../hooks/useApi";
import { useAuth } from "../../hooks/useAuth";
import { api } from "../../services/api";
import type { Template } from "../../types";

function Preview({ id, version }: { id: number; version: number }) {
  const [src, setSrc] = useState<string | null>(null);
  useEffect(() => {
    let url: string | null = null;
    api
      .blobUrl(`/templates/${id}/preview`)
      .then((u) => {
        url = u;
        setSrc(u);
      })
      .catch(() => setSrc(null));
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [id, version]);
  return <div className="aspect-[4/5] w-full overflow-hidden rounded-lg bg-slate-100">{src ? <img src={src} alt="Template preview" className="h-full w-full object-cover" /> : <div className="flex h-full items-center justify-center"><Spinner /></div>}</div>;
}

export default function TemplatesTab() {
  const { can } = useAuth();
  const { data, loading, reload } = useApi(() => api.get<Template[]>("/templates"));
  const { busy, error, run } = useAction();
  const [edit, setEdit] = useState<{ t: Partial<Template>; json: string } | null>(null);
  const [version, setVersion] = useState(0);
  if (loading || !data) return <Loading />;
  const admin = can("admin");

  const save = async () => {
    if (!edit) return;
    let layout: Record<string, unknown>;
    try {
      layout = JSON.parse(edit.json);
    } catch {
      alert("Layout is not valid JSON");
      return;
    }
    const body = { name: edit.t.name, description: edit.t.description, layout, is_active: edit.t.is_active ?? true };
    const r = await run("save", () => (edit.t.id ? api.patch(`/templates/${edit.t.id}`, body) : api.post("/templates", { ...body, key: edit.t.key })));
    if (r) {
      setEdit(null);
      setVersion(version + 1);
      reload();
    }
  };

  return (
    <div>
      <div className="mb-4 flex items-start justify-between gap-4">
        <p className="muted max-w-3xl">
          Templates are JSON layouts rendered to 1080×1350 JPEG (Instagram 4:5). Elements: <code>image</code>, <code>logo</code>, <code>rect</code>, <code>text</code> with a <code>box</code> [x, y, width, height]. Text slots: headline, subtitle, cta, footer, category, company. Colours can use {"{primary}"} / {"{secondary}"} from the brand profile.
        </p>
        {admin && (
          <button className="btn-primary shrink-0" onClick={() => setEdit({ t: { key: "", name: "", description: "", is_active: true }, json: JSON.stringify(data[0]?.layout ?? { elements: [] }, null, 2) })}>
            ✚ New template
          </button>
        )}
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {data.map((t) => (
          <div key={t.id} className={`card p-3 ${t.is_active ? "" : "opacity-50"}`}>
            <Preview id={t.id} version={version} />
            <div className="mt-2 font-medium">{t.name}</div>
            <div className="text-xs text-slate-500">{t.description}</div>
            {admin && (
              <button className="btn-ghost mt-2 text-xs" onClick={() => setEdit({ t, json: JSON.stringify(t.layout, null, 2) })}>
                Edit layout
              </button>
            )}
          </div>
        ))}
      </div>
      <Modal wide open={!!edit} title={edit?.t.id ? `Edit template — ${edit.t.name}` : "New template"} onClose={() => setEdit(null)} footer={<button className="btn-primary" onClick={save} disabled={!!busy}>{busy && <Spinner />} Save</button>}>
        {edit && (
          <>
            {error && <Alert kind="error">{error.message}</Alert>}
            <div className="grid gap-4 sm:grid-cols-3">
              {!edit.t.id && (
                <Field label="Key" hint="lowercase">
                  <input className="input" value={edit.t.key ?? ""} onChange={(e) => setEdit({ ...edit, t: { ...edit.t, key: e.target.value.toLowerCase() } })} />
                </Field>
              )}
              <Field label="Name">
                <input className="input" value={edit.t.name ?? ""} onChange={(e) => setEdit({ ...edit, t: { ...edit.t, name: e.target.value } })} />
              </Field>
              <Field label="Description">
                <input className="input" value={edit.t.description ?? ""} onChange={(e) => setEdit({ ...edit, t: { ...edit.t, description: e.target.value } })} />
              </Field>
            </div>
            <Field label="Layout (JSON)">
              <textarea className="input font-mono text-xs" rows={18} value={edit.json} onChange={(e) => setEdit({ ...edit, json: e.target.value })} />
            </Field>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={edit.t.is_active ?? true} onChange={(e) => setEdit({ ...edit, t: { ...edit.t, is_active: e.target.checked } })} /> Active
            </label>
          </>
        )}
      </Modal>
    </div>
  );
}
