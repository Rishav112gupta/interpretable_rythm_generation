import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Field, Loading, PageHeader, Spinner } from "../components/ui";
import { useAction, useApi } from "../hooks/useApi";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import type { Brand, Category, PostDetail, Template } from "../types";
import { zonedLocalToIso } from "../utils/time";

const TONES = ["Helpful and motivating", "Friendly", "Professional", "Urgent", "Celebratory", "Informative", "Playful"];

export default function CreatePostPage() {
  const { tz } = useAuth();
  const navigate = useNavigate();
  const { data, loading } = useApi(() => Promise.all([api.get<Category[]>("/categories"), api.get<Template[]>("/templates"), api.get<Brand>("/brand")]));
  const { busy, error, run } = useAction();
  const [form, setForm] = useState({
    category_id: "",
    template_id: "",
    topic: "",
    target_audience: "",
    tone: "",
    objective: "",
    important_info: "",
    cta: "",
    language: "",
    brand_instructions: "",
    reference_material: "",
    image_instructions: "",
    desired_date: "",
    desired_time: "18:00",
  });
  const set = (k: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [k]: e.target.value });

  if (loading || !data) return <Loading />;
  const [categories, templates, brand] = data;

  const submit = (generate: boolean) => async (e?: FormEvent) => {
    e?.preventDefault();
    if (!form.topic.trim()) return;
    const body = {
      category_id: form.category_id ? Number(form.category_id) : null,
      template_id: form.template_id ? Number(form.template_id) : null,
      topic: form.topic,
      target_audience: form.target_audience,
      tone: form.tone,
      objective: form.objective,
      important_info: form.important_info,
      cta: form.cta,
      language: form.language || brand.default_language || "English",
      brand_instructions: form.brand_instructions,
      reference_material: form.reference_material,
      image_instructions: form.image_instructions,
      desired_publish_at: form.desired_date ? zonedLocalToIso(`${form.desired_date}T${form.desired_time || "18:00"}`, tz) : null,
      generate,
    };
    const post = await run(generate ? "generate" : "draft", () => api.post<PostDetail>("/posts", body));
    if (post) navigate(`/posts/${post.id}`, { state: { warnings: post.warnings } });
  };

  const selectedCat = categories.find((c) => String(c.id) === form.category_id);

  return (
    <div>
      <PageHeader title="Create post" subtitle="Describe the post. The AI drafts text and an image; a human reviews and approves before anything is published." />
      {!brand.company_name && (
        <div className="mb-4">
          <Alert kind="warning" title="Brand profile is empty">
            Fill in Settings → Brand profile (company name, voice, verified facts) so the AI writes on-brand content. The AI will not invent facts it has not been given.
          </Alert>
        </div>
      )}
      {error && (
        <div className="mb-4">
          <Alert kind="error" title="Could not create the post">
            {error.message}
          </Alert>
        </div>
      )}
      <form onSubmit={submit(true)} className="grid gap-6 lg:grid-cols-3">
        <div className="card space-y-4 p-6 lg:col-span-2">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Content category" hint={selectedCat?.description}>
              <select className="input" value={form.category_id} onChange={set("category_id")}>
                <option value="">— General —</option>
                {categories.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Design template" hint="Defaults to the category's template">
              <select className="input" value={form.template_id} onChange={set("template_id")}>
                <option value="">— Category default —</option>
                {templates
                  .filter((t) => t.is_active)
                  .map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
              </select>
            </Field>
          </div>
          <Field label="Topic" required>
            <input className="input" value={form.topic} onChange={set("topic")} placeholder="e.g. Last-minute exam preparation" maxLength={500} required />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Target audience">
              <input className="input" value={form.target_audience} onChange={set("target_audience")} placeholder={brand.target_audience || "e.g. Students"} />
            </Field>
            <Field label="Tone">
              <input className="input" list="tones" value={form.tone} onChange={set("tone")} placeholder={brand.tone || "e.g. Helpful and motivating"} />
              <datalist id="tones">
                {TONES.map((t) => (
                  <option key={t} value={t} />
                ))}
              </datalist>
            </Field>
          </div>
          <Field label="Objective" hint="What should this post achieve?">
            <input className="input" value={form.objective} onChange={set("objective")} placeholder="e.g. Reduce exam anxiety and promote the prep program" />
          </Field>
          <Field label="Important information" hint="Facts the post must include (dates, prices, details). The AI only states facts given here or in the brand profile.">
            <textarea className="input" rows={3} value={form.important_info} onChange={set("important_info")} />
          </Field>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Call to action">
              <input className="input" value={form.cta} onChange={set("cta")} placeholder="e.g. Join our preparation program" />
            </Field>
            <Field label="Language">
              <input className="input" value={form.language} onChange={set("language")} placeholder={brand.default_language || "English"} />
            </Field>
          </div>
          <details className="rounded-lg border border-slate-200 p-3">
            <summary className="cursor-pointer text-sm font-medium text-slate-700">More options (brand instructions, reference material, image instructions)</summary>
            <div className="mt-3 space-y-4">
              <Field label="Brand instructions for this post">
                <textarea className="input" rows={2} value={form.brand_instructions} onChange={set("brand_instructions")} />
              </Field>
              <Field label="Reference material (optional)" hint="Notes, syllabus extracts, announcement text… Used as a verified source.">
                <textarea className="input" rows={4} value={form.reference_material} onChange={set("reference_material")} />
              </Field>
              <Field label="Image instructions (optional)">
                <textarea className="input" rows={2} value={form.image_instructions} onChange={set("image_instructions")} placeholder="e.g. students studying at a desk, warm colours" />
              </Field>
            </div>
          </details>
        </div>

        <div className="space-y-6">
          <div className="card space-y-4 p-6">
            <h2 className="h2">Desired posting time</h2>
            <p className="muted">Optional. Approving the post schedules it for this time ({tz}).</p>
            <Field label="Date">
              <input className="input" type="date" value={form.desired_date} onChange={set("desired_date")} />
            </Field>
            <Field label="Time">
              <input className="input" type="time" value={form.desired_time} onChange={set("desired_time")} />
            </Field>
          </div>
          <div className="card space-y-3 p-6">
            <button type="submit" className="btn-primary w-full py-3 text-base" disabled={!!busy || !form.topic.trim()}>
              {busy === "generate" ? (
                <>
                  <Spinner /> Generating with AI…
                </>
              ) : (
                "✨ Generate with AI"
              )}
            </button>
            <button type="button" className="btn-secondary w-full" disabled={!!busy || !form.topic.trim()} onClick={() => submit(false)()}>
              {busy === "draft" && <Spinner />} Save as draft (write it myself)
            </button>
            <p className="text-xs text-slate-500">Generation can take up to a minute with real AI providers.</p>
          </div>
        </div>
      </form>
    </div>
  );
}
