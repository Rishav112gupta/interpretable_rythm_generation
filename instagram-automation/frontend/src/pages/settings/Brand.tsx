import { useEffect, useState } from "react";
import { Alert, Field, ListInput, Loading, Spinner } from "../../components/ui";
import { useAction, useApi } from "../../hooks/useApi";
import { useAuth } from "../../hooks/useAuth";
import { api } from "../../services/api";
import type { Brand } from "../../types";

export default function BrandTab() {
  const { can } = useAuth();
  const { data, setData, loading } = useApi(() => api.get<Brand>("/brand"));
  const { busy, error, run } = useAction();
  const [b, setB] = useState<Brand | null>(null);
  const [saved, setSaved] = useState(false);
  useEffect(() => setB(data), [data]);
  if (loading || !b) return <Loading />;
  const admin = can("admin");
  const set = <K extends keyof Brand>(k: K, v: Brand[K]) => {
    setSaved(false);
    setB({ ...b, [k]: v });
  };

  const save = async () => {
    const r = await run("save", () => api.put<Brand>("/brand", b as unknown as Record<string, unknown>));
    if (r) {
      setData(r);
      setSaved(true);
    }
  };
  const uploadLogo = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await run("logo", () => api.post<Brand>("/brand/logo", fd));
    if (r) setData(r);
  };

  return (
    <div className="space-y-6">
      {error && <Alert kind="error">{error.message}</Alert>}
      {saved && <Alert kind="success">Brand profile saved. New generations will use it.</Alert>}
      <fieldset disabled={!admin} className="grid gap-6 lg:grid-cols-2">
        <div className="card space-y-4 p-5">
          <h2 className="h2">Company & voice</h2>
          <Field label="Company name">
            <input className="input" value={b.company_name} onChange={(e) => set("company_name", e.target.value)} />
          </Field>
          <Field label="Description">
            <textarea className="input" rows={3} value={b.description} onChange={(e) => set("description", e.target.value)} />
          </Field>
          <Field label="Target audience">
            <textarea className="input" rows={2} value={b.target_audience} onChange={(e) => set("target_audience", e.target.value)} />
          </Field>
          <Field label="Brand voice">
            <textarea className="input" rows={2} value={b.brand_voice} onChange={(e) => set("brand_voice", e.target.value)} placeholder="e.g. Warm, encouraging mentor; simple language" />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Default tone">
              <input className="input" value={b.tone} onChange={(e) => set("tone", e.target.value)} />
            </Field>
            <Field label="Default language">
              <input className="input" value={b.default_language} onChange={(e) => set("default_language", e.target.value)} />
            </Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Words to use">
              <ListInput value={b.words_to_use} onChange={(v) => set("words_to_use", v)} />
            </Field>
            <Field label="Words to avoid">
              <ListInput value={b.words_to_avoid} onChange={(v) => set("words_to_avoid", v)} />
            </Field>
          </div>
          <Field label="CTA style">
            <input className="input" value={b.cta_style} onChange={(e) => set("cta_style", e.target.value)} />
          </Field>
          <Field label="Hashtag strategy">
            <input className="input" value={b.hashtag_strategy} onChange={(e) => set("hashtag_strategy", e.target.value)} />
          </Field>
          <Field label="Default hashtags" hint="Without #, one per line">
            <ListInput value={b.default_hashtags} onChange={(v) => set("default_hashtags", v.map((x) => x.replace(/^#/, "")))} />
          </Field>
          <Field label="Content restrictions">
            <textarea className="input" rows={2} value={b.content_restrictions} onChange={(e) => set("content_restrictions", e.target.value)} placeholder="e.g. never mention competitors by name; no political content" />
          </Field>
        </div>

        <div className="space-y-6">
          <div className="card space-y-4 p-5">
            <h2 className="h2">Verified company facts</h2>
            <p className="muted">The AI may only state prices, dates, course details, statistics, contact details or claims that appear here or in a post's input. Anything else is flagged for review.</p>
            {b.knowledge.map((k, i) => (
              <div key={i} className="flex gap-2">
                <input className="input w-2/5" placeholder="Label (e.g. JEE 2027 course fee)" value={k.label} onChange={(e) => set("knowledge", b.knowledge.map((x, j) => (j === i ? { ...x, label: e.target.value } : x)))} />
                <input className="input" placeholder="Value (e.g. Rs 45,000)" value={k.value} onChange={(e) => set("knowledge", b.knowledge.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />
                <button type="button" className="btn-ghost" onClick={() => set("knowledge", b.knowledge.filter((_, j) => j !== i))} aria-label="Remove">
                  ×
                </button>
              </div>
            ))}
            <button type="button" className="btn-secondary" onClick={() => set("knowledge", [...b.knowledge, { label: "", value: "" }])}>
              ✚ Add fact
            </button>
            <Field label="Website">
              <input className="input" value={b.website} onChange={(e) => set("website", e.target.value)} />
            </Field>
            <Field label="Contact information">
              <textarea className="input" rows={2} value={b.contact_info} onChange={(e) => set("contact_info", e.target.value)} />
            </Field>
          </div>
          <div className="card space-y-4 p-5">
            <h2 className="h2">Visual identity</h2>
            <Field label="Visual style (used in image prompts)">
              <textarea className="input" rows={2} value={b.visual_style} onChange={(e) => set("visual_style", e.target.value)} placeholder="e.g. clean flat illustrations, navy and amber palette" />
            </Field>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Primary colour">
                <input className="h-10 w-full rounded border border-slate-300" type="color" value={b.primary_color} onChange={(e) => set("primary_color", e.target.value)} />
              </Field>
              <Field label="Secondary colour">
                <input className="h-10 w-full rounded border border-slate-300" type="color" value={b.secondary_color} onChange={(e) => set("secondary_color", e.target.value)} />
              </Field>
            </div>
            <Field label="Logo (PNG with transparency works best)">
              <div className="flex items-center gap-3">
                {b.logo_url && <img src={b.logo_url} alt="Logo" className="h-12 w-12 rounded bg-slate-100 object-contain" />}
                <input type="file" accept="image/png,image/jpeg,image/webp" onChange={(e) => e.target.files?.[0] && uploadLogo(e.target.files[0])} />
                {busy === "logo" && <Spinner />}
              </div>
            </Field>
          </div>
        </div>
      </fieldset>
      {admin && (
        <button className="btn-primary" onClick={save} disabled={!!busy}>
          {busy === "save" && <Spinner />} Save brand profile
        </button>
      )}
    </div>
  );
}
