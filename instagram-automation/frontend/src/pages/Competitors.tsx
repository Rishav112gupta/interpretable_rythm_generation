import { useState } from "react";
import { Alert, Empty, Field, Loading, Modal, PageHeader, Spinner } from "../components/ui";
import { useAction, useApi } from "../hooks/useApi";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import type { Competitor, Insight, Observation } from "../types";
import { formatDateTime } from "../utils/time";

const emptyObs = { content_topic: "", content_type: "image", caption_summary: "", visual_style: "", posting_frequency: "", observed_strategy: "", cta_used: "", engagement_notes: "", source_url: "", notes: "" };
const INSIGHT_LABELS: Record<string, string> = {
  common_topics: "Common topics",
  content_gaps: "Content gaps / opportunities",
  recurring_themes: "Recurring themes & formats",
  audience_targeting: "Audience targeting",
  cta_patterns: "CTA patterns",
  visual_trends: "Visual trends",
  recommendations: "Recommendations for ORIGINAL content",
};

export default function CompetitorsPage() {
  const { tz, can } = useAuth();
  const { data, reload, loading } = useApi(() => Promise.all([api.get<Competitor[]>("/competitors"), api.get<Insight[]>("/insights")]));
  const { busy, error, setError, run } = useAction();
  const [selected, setSelected] = useState<Competitor | null>(null);
  const { data: observations, reload: reloadObs } = useApi(() => (selected ? api.get<Observation[]>(`/competitors/${selected.id}/observations`) : Promise.resolve([])), [selected?.id]);
  const [compForm, setCompForm] = useState<{ name: string; instagram_handle: string; website: string; notes: string } | null>(null);
  const [obsForm, setObsForm] = useState<typeof emptyObs | null>(null);
  const [importMsg, setImportMsg] = useState<string | null>(null);

  if (loading && !data) return <Loading />;
  const [competitors, insights] = data ?? [[], []];
  const latest = insights[0];

  const saveCompetitor = async () => {
    if (!compForm) return;
    const r = await run("comp", () => api.post<Competitor>("/competitors", compForm));
    if (r) {
      setCompForm(null);
      reload();
    }
  };
  const saveObs = async () => {
    if (!obsForm || !selected) return;
    const r = await run("obs", () => api.post(`/competitors/${selected.id}/observations`, obsForm));
    if (r) {
      setObsForm(null);
      reloadObs();
      reload();
    }
  };
  const analyze = async () => {
    const r = await run("analyze", () => api.post<Insight>("/competitors/analyze", {}));
    if (r) reload();
  };
  const importCsv = async (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    const r = await run("import", () => api.post<{ imported: number }>("/competitors/import", fd));
    if (r) {
      setImportMsg(`Imported ${r.imported} observation(s).`);
      reload();
    }
  };

  return (
    <div>
      <PageHeader
        title="Competitor research"
        subtitle="Record what competitors do (in your own words), then let the AI extract high-level patterns to inspire ORIGINAL content."
        actions={
          can("editor") && (
            <>
              <label className="btn-secondary cursor-pointer">
                {busy === "import" && <Spinner />} Import CSV
                <input type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => e.target.files?.[0] && importCsv(e.target.files[0])} />
              </label>
              <button className="btn-secondary" onClick={() => setCompForm({ name: "", instagram_handle: "", website: "", notes: "" })}>
                ✚ Add competitor
              </button>
              <button className="btn-primary" onClick={analyze} disabled={!!busy}>
                {busy === "analyze" && <Spinner />} Analyse patterns
              </button>
            </>
          )
        }
      />
      <div className="mb-4 space-y-3">
        <Alert kind="info" title="Compliance">
          This module never scrapes Instagram or websites and never copies competitor captions or images. Add observations from content you are allowed to view, summarised in your own words. CSV columns: competitor, content_topic, content_type, caption_summary, visual_style, posting_frequency, observed_strategy, cta_used, engagement_notes, source_url, observed_on, notes.
        </Alert>
        {importMsg && (
          <Alert kind="success" onClose={() => setImportMsg(null)}>
            {importMsg}
          </Alert>
        )}
        {error && (
          <Alert kind="error" onClose={() => setError(null)}>
            {error.message}
          </Alert>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="card p-4">
          <h2 className="h2 mb-3">Competitors</h2>
          {competitors.length === 0 ? (
            <p className="muted">None yet.</p>
          ) : (
            <ul className="space-y-1">
              {competitors.map((c) => (
                <li key={c.id}>
                  <button onClick={() => setSelected(c)} className={`w-full rounded-lg px-3 py-2 text-left text-sm ${selected?.id === c.id ? "bg-indigo-50 text-indigo-800" : "hover:bg-slate-50"}`}>
                    <div className="font-medium">{c.name}</div>
                    <div className="text-xs text-slate-500">
                      {c.instagram_handle && `@${c.instagram_handle.replace(/^@/, "")} · `}
                      {c.observation_count} observation(s)
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card p-4 lg:col-span-2">
          {!selected ? (
            <Empty title="Select a competitor">to view or add observations.</Empty>
          ) : (
            <>
              <div className="mb-3 flex items-center justify-between">
                <h2 className="h2">{selected.name} — observations</h2>
                {can("editor") && (
                  <button className="btn-secondary" onClick={() => setObsForm({ ...emptyObs })}>
                    ✚ Add observation
                  </button>
                )}
              </div>
              {!observations?.length ? (
                <p className="muted">No observations yet.</p>
              ) : (
                <div className="space-y-2">
                  {observations.map((o) => (
                    <div key={o.id} className="rounded-lg border border-slate-200 p-3 text-sm">
                      <div className="flex justify-between">
                        <span className="font-medium">{o.content_topic || "(no topic)"}</span>
                        <span className="text-xs text-slate-500">{o.content_type}</span>
                      </div>
                      {o.caption_summary && <p className="mt-1 text-slate-700">{o.caption_summary}</p>}
                      <div className="mt-1 text-xs text-slate-500">
                        {[o.visual_style && `Visual: ${o.visual_style}`, o.cta_used && `CTA: ${o.cta_used}`, o.observed_strategy && `Strategy: ${o.observed_strategy}`].filter(Boolean).join(" · ")}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </div>

      <div className="card mt-6 p-5">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="h2">Content strategy insights</h2>
          {latest && (
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={latest.use_in_generation} onChange={() => run("toggle", () => api.post(`/insights/${latest.id}/toggle`)).then(reload)} disabled={!can("editor")} />
              Use in AI generation
            </label>
          )}
        </div>
        {!latest ? (
          <Empty title="No insights yet">Add observations and click “Analyse patterns”.</Empty>
        ) : (
          <>
            <p className="muted mb-3">
              From {latest.observation_count} observations · {latest.llm_provider}/{latest.llm_model} · {formatDateTime(latest.created_at, tz)}
            </p>
            {typeof latest.insights.summary === "string" && latest.insights.summary && <p className="mb-4 text-sm text-slate-800">{latest.insights.summary}</p>}
            <div className="grid gap-4 md:grid-cols-2">
              {Object.entries(INSIGHT_LABELS).map(([k, label]) => {
                const items = latest.insights[k];
                if (!Array.isArray(items) || !items.length) return null;
                return (
                  <div key={k}>
                    <div className="text-sm font-semibold text-slate-800">{label}</div>
                    <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-slate-700">
                      {items.map((i) => (
                        <li key={i}>{i}</li>
                      ))}
                    </ul>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </div>

      <Modal open={!!compForm} title="Add competitor" onClose={() => setCompForm(null)} footer={<button className="btn-primary" onClick={saveCompetitor} disabled={!compForm?.name || !!busy}>Save</button>}>
        {compForm && (
          <>
            <Field label="Name" required>
              <input className="input" value={compForm.name} onChange={(e) => setCompForm({ ...compForm, name: e.target.value })} />
            </Field>
            <Field label="Instagram handle">
              <input className="input" value={compForm.instagram_handle} onChange={(e) => setCompForm({ ...compForm, instagram_handle: e.target.value })} />
            </Field>
            <Field label="Website">
              <input className="input" value={compForm.website} onChange={(e) => setCompForm({ ...compForm, website: e.target.value })} />
            </Field>
            <Field label="Notes">
              <textarea className="input" rows={2} value={compForm.notes} onChange={(e) => setCompForm({ ...compForm, notes: e.target.value })} />
            </Field>
          </>
        )}
      </Modal>

      <Modal wide open={!!obsForm} title={`New observation — ${selected?.name ?? ""}`} onClose={() => setObsForm(null)} footer={<button className="btn-primary" onClick={saveObs} disabled={!!busy}>Save observation</button>}>
        {obsForm && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Content topic">
              <input className="input" value={obsForm.content_topic} onChange={(e) => setObsForm({ ...obsForm, content_topic: e.target.value })} />
            </Field>
            <Field label="Content type">
              <select className="input" value={obsForm.content_type} onChange={(e) => setObsForm({ ...obsForm, content_type: e.target.value })}>
                {["image", "carousel", "reel", "story", "video", "other"].map((t) => (
                  <option key={t}>{t}</option>
                ))}
              </select>
            </Field>
            <div className="sm:col-span-2">
              <Field label="Caption summary (your own words, max 500 chars)" hint="Do not paste the competitor's caption.">
                <textarea className="input" rows={2} maxLength={500} value={obsForm.caption_summary} onChange={(e) => setObsForm({ ...obsForm, caption_summary: e.target.value })} />
              </Field>
            </div>
            <Field label="Visual style">
              <input className="input" value={obsForm.visual_style} onChange={(e) => setObsForm({ ...obsForm, visual_style: e.target.value })} />
            </Field>
            <Field label="Posting frequency">
              <input className="input" value={obsForm.posting_frequency} onChange={(e) => setObsForm({ ...obsForm, posting_frequency: e.target.value })} placeholder="e.g. 3x per week" />
            </Field>
            <Field label="CTA used">
              <input className="input" value={obsForm.cta_used} onChange={(e) => setObsForm({ ...obsForm, cta_used: e.target.value })} />
            </Field>
            <Field label="Observed strategy">
              <input className="input" value={obsForm.observed_strategy} onChange={(e) => setObsForm({ ...obsForm, observed_strategy: e.target.value })} />
            </Field>
            <Field label="Engagement notes">
              <input className="input" value={obsForm.engagement_notes} onChange={(e) => setObsForm({ ...obsForm, engagement_notes: e.target.value })} />
            </Field>
            <Field label="Source URL (reference only)">
              <input className="input" value={obsForm.source_url} onChange={(e) => setObsForm({ ...obsForm, source_url: e.target.value })} />
            </Field>
          </div>
        )}
      </Modal>
    </div>
  );
}
