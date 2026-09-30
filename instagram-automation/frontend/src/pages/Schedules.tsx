import { useEffect, useState } from "react";
import { Alert, Empty, Field, ListInput, Loading, Modal, PageHeader, Spinner } from "../components/ui";
import { useAction, useApi } from "../hooks/useApi";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import type { Category, Schedule, Template } from "../types";
import { formatDateTime } from "../utils/time";

type Form = Omit<Schedule, "id" | "next_slots">;

const empty = (tz: string): Form => ({
  name: "Every 4th day",
  mode: "rolling",
  interval_days: 4,
  start_date: new Date().toISOString().slice(0, 10),
  end_date: null,
  post_time: "18:00",
  timezone: tz,
  generation_lead_hours: 72,
  auto_generate: true,
  auto_schedule_on_approval: true,
  category_id: null,
  category_rotation: [],
  template_id: null,
  topic_pool: [],
  target_audience: "",
  tone: "",
  objective: "",
  cta: "",
  language: "English",
  is_active: true,
});

export default function SchedulesPage() {
  const { tz, can } = useAuth();
  const { data, loading, error: loadError, reload } = useApi(() => Promise.all([api.get<Schedule[]>("/schedules"), api.get<Category[]>("/categories"), api.get<Template[]>("/templates")]));
  const { busy, error, setError, run } = useAction();
  const [editing, setEditing] = useState<{ id?: number; form: Form } | null>(null);
  const [preview, setPreview] = useState<string[]>([]);
  const [runResult, setRunResult] = useState<string | null>(null);

  const form = editing?.form;
  useEffect(() => {
    if (!form) return;
    const t = setTimeout(() => {
      api
        .post<string[]>("/schedules/preview", { mode: form.mode, interval_days: form.interval_days, start_date: form.start_date, end_date: form.end_date, post_time: form.post_time, timezone: form.timezone, count: 8 })
        .then(setPreview)
        .catch(() => setPreview([]));
    }, 300);
    return () => clearTimeout(t);
  }, [form?.mode, form?.interval_days, form?.start_date, form?.end_date, form?.post_time, form?.timezone]); // eslint-disable-line react-hooks/exhaustive-deps

  if (loading && !data) return <Loading />;
  if (!data) return <Alert kind="error">{loadError}</Alert>;
  const [schedules, categories, templates] = data;
  const set = <K extends keyof Form>(k: K, v: Form[K]) => editing && setEditing({ ...editing, form: { ...editing.form, [k]: v } });

  const save = async () => {
    if (!editing) return;
    const body = { ...editing.form, post_time: editing.form.post_time.slice(0, 5) };
    const res = await run("save", () => (editing.id ? api.put(`/schedules/${editing.id}`, body) : api.post("/schedules", body)));
    if (res) {
      setEditing(null);
      reload();
    }
  };
  const remove = async (s: Schedule) => {
    if (!confirm(`Delete schedule "${s.name}"? Already-created posts are kept.`)) return;
    await run("del", () => api.del(`/schedules/${s.id}`));
    reload();
  };
  const runNow = async () => {
    const r = await run("run", () => api.post<{ planned: number; generated: number; failed: number }>("/schedules/run"));
    if (r) setRunResult(`Planned ${r.planned} new slot(s); generated content for ${r.generated} post(s)${r.failed ? `; ${r.failed} failed (see logs)` : ""}.`);
    reload();
  };

  return (
    <div>
      <PageHeader
        title="Recurring schedules"
        subtitle="E.g. “post every 4th day at 18:00”. Content is generated ahead of time for review; only approved posts are published."
        actions={
          can("approver") && (
            <>
              {can("admin") && (
                <button className="btn-secondary" onClick={runNow} disabled={!!busy}>
                  {busy === "run" && <Spinner />} Run planner now
                </button>
              )}
              <button className="btn-primary" onClick={() => setEditing({ form: empty(tz) })}>
                ✚ New schedule
              </button>
            </>
          )
        }
      />
      {runResult && (
        <div className="mb-4">
          <Alert kind="success" onClose={() => setRunResult(null)}>
            {runResult}
          </Alert>
        </div>
      )}
      {error && !editing && (
        <div className="mb-4">
          <Alert kind="error" onClose={() => setError(null)}>
            {error.message}
          </Alert>
        </div>
      )}
      <div className="mb-6">
        <Alert kind="info" title="How recurring schedules work">
          <ol className="list-decimal space-y-0.5 pl-5">
            <li>The planner creates a draft post for each upcoming slot (next 14 days).</li>
            <li>“Generation lead time” before the slot, the AI writes the post and puts it in <em>Needs review</em>.</li>
            <li>A human approves it — it is then scheduled for the slot automatically.</li>
            <li>At the slot time, the scheduler publishes it. Unapproved posts are never published; you get a warning instead.</li>
          </ol>
        </Alert>
      </div>
      {schedules.length === 0 ? (
        <Empty title="No recurring schedules">Create one, e.g. every 4 days at 18:00 {tz}.</Empty>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {schedules.map((s) => (
            <div key={s.id} className="card p-5">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <div className="font-semibold text-slate-900">{s.name}</div>
                  <div className="text-sm text-slate-600">
                    {s.mode === "rolling" ? `Every ${s.interval_days} day(s) from ${s.start_date}` : `Days ${s.interval_days}, ${s.interval_days * 2}, ${s.interval_days * 3}… of each month`} at {s.post_time.slice(0, 5)} ({s.timezone})
                  </div>
                  <div className="mt-1 text-xs text-slate-500">
                    Content generated {s.generation_lead_hours}h before each slot · {s.topic_pool.length} topic(s) in pool
                    {s.category_rotation.length > 0 && ` · rotates ${s.category_rotation.join(" → ")}`}
                  </div>
                </div>
                <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${s.is_active ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-500"}`}>{s.is_active ? "Active" : "Paused"}</span>
              </div>
              <div className="mt-3 text-xs text-slate-500">Next slots:</div>
              <ul className="mt-1 flex flex-wrap gap-1.5 text-xs">
                {s.next_slots.map((d) => (
                  <li key={d} className="rounded bg-slate-100 px-2 py-0.5 text-slate-700">
                    {formatDateTime(d, s.timezone)}
                  </li>
                ))}
              </ul>
              {can("approver") && (
                <div className="mt-4 flex gap-2">
                  <button className="btn-secondary" onClick={() => setEditing({ id: s.id, form: { ...s } })}>
                    Edit
                  </button>
                  <button className="btn-ghost text-rose-600" onClick={() => remove(s)}>
                    Delete
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <Modal
        wide
        open={!!editing}
        title={editing?.id ? "Edit schedule" : "New recurring schedule"}
        onClose={() => setEditing(null)}
        footer={
          <>
            <button className="btn-secondary" onClick={() => setEditing(null)}>
              Cancel
            </button>
            <button className="btn-primary" onClick={save} disabled={!!busy}>
              {busy === "save" && <Spinner />} Save schedule
            </button>
          </>
        }
      >
        {form && (
          <>
            {error && <Alert kind="error">{error.message}</Alert>}
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Name">
                <input className="input" value={form.name} onChange={(e) => set("name", e.target.value)} />
              </Field>
              <Field label="What does “every N days” mean?" hint={form.mode === "rolling" ? "Counts N days continuously from the start date." : "Uses days N, 2N, 3N… of each month and restarts every month."}>
                <select className="input" value={form.mode} onChange={(e) => set("mode", e.target.value as Form["mode"])}>
                  <option value="rolling">Every N days from start date (rolling)</option>
                  <option value="monthly">Every Nth day of each month</option>
                </select>
              </Field>
              <Field label="N (days)">
                <input className="input" type="number" min={1} max={form.mode === "monthly" ? 28 : 365} value={form.interval_days} onChange={(e) => set("interval_days", Number(e.target.value))} />
              </Field>
              <Field label="Posting time">
                <input className="input" type="time" value={form.post_time.slice(0, 5)} onChange={(e) => set("post_time", e.target.value)} />
              </Field>
              <Field label="Start date">
                <input className="input" type="date" value={form.start_date} onChange={(e) => set("start_date", e.target.value)} />
              </Field>
              <Field label="End date (optional)">
                <input className="input" type="date" value={form.end_date ?? ""} onChange={(e) => set("end_date", e.target.value || null)} />
              </Field>
              <Field label="Timezone" hint="IANA name, e.g. Asia/Kolkata">
                <input className="input" value={form.timezone} onChange={(e) => set("timezone", e.target.value)} />
              </Field>
              <Field label="Generate content this many hours before each slot">
                <input className="input" type="number" min={0} value={form.generation_lead_hours} onChange={(e) => set("generation_lead_hours", Number(e.target.value))} />
              </Field>
            </div>
            <div className="rounded-lg bg-slate-50 p-3 text-xs">
              <div className="mb-1 font-semibold text-slate-700">Preview — next slots</div>
              <div className="flex flex-wrap gap-1.5">
                {preview.length ? (
                  preview.map((d) => (
                    <span key={d} className="rounded bg-white px-2 py-0.5 ring-1 ring-slate-200">
                      {formatDateTime(d, form.timezone || tz, { weekday: "short" })}
                    </span>
                  ))
                ) : (
                  <span className="text-slate-500">Enter valid values to preview.</span>
                )}
              </div>
            </div>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="Category">
                <select className="input" value={form.category_id ?? ""} onChange={(e) => set("category_id", e.target.value ? Number(e.target.value) : null)}>
                  <option value="">— General —</option>
                  {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Rotate categories (optional)" hint={`Keys, one per line: ${categories.map((c) => c.key).join(", ")}`}>
                <ListInput value={form.category_rotation} onChange={(v) => set("category_rotation", v.map((x) => x.toUpperCase()))} />
              </Field>
              <Field label="Template">
                <select className="input" value={form.template_id ?? ""} onChange={(e) => set("template_id", e.target.value ? Number(e.target.value) : null)}>
                  <option value="">— Category default —</option>
                  {templates.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.name}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Target audience">
                <input className="input" value={form.target_audience} onChange={(e) => set("target_audience", e.target.value)} />
              </Field>
              <Field label="Tone">
                <input className="input" value={form.tone} onChange={(e) => set("tone", e.target.value)} />
              </Field>
              <Field label="Call to action">
                <input className="input" value={form.cta} onChange={(e) => set("cta", e.target.value)} />
              </Field>
            </div>
            <Field label="Topic pool (one per line, used in rotation)" hint="Leave empty to let the AI pick a fresh idea for every slot.">
              <ListInput rows={4} value={form.topic_pool} onChange={(v) => set("topic_pool", v)} />
            </Field>
            <div className="flex flex-wrap gap-6 text-sm">
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.auto_generate} onChange={(e) => set("auto_generate", e.target.checked)} /> Auto-generate content with AI
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.auto_schedule_on_approval} onChange={(e) => set("auto_schedule_on_approval", e.target.checked)} /> Schedule for the slot when approved
              </label>
              <label className="flex items-center gap-2">
                <input type="checkbox" checked={form.is_active} onChange={(e) => set("is_active", e.target.checked)} /> Active
              </label>
            </div>
          </>
        )}
      </Modal>
    </div>
  );
}
