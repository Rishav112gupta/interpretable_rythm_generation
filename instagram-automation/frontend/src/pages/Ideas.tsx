import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Empty, Field, Loading, PageHeader, Spinner } from "../components/ui";
import { useAction, useApi } from "../hooks/useApi";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import type { Idea, PostDetail } from "../types";

export default function IdeasPage() {
  const { can } = useAuth();
  const navigate = useNavigate();
  const { data: ideas, setData, loading, error: loadError } = useApi(() => api.get<Idea[]>("/ideas"));
  const { busy, error, run } = useAction();
  const [theme, setTheme] = useState("");
  const [audience, setAudience] = useState("");
  const [count, setCount] = useState(7);

  const generate = async () => {
    const res = await run("gen", () => api.post<Idea[]>("/ideas/generate", { count, theme, target_audience: audience }));
    if (res) setData([...res, ...(ideas ?? [])]);
  };
  const convert = async (idea: Idea) => {
    const post = await run(`c${idea.id}`, () => api.post<PostDetail>(`/ideas/${idea.id}/convert`));
    if (post) navigate(`/posts/${post.id}`);
  };
  const dismiss = async (idea: Idea) => {
    await run(`d${idea.id}`, () => api.post(`/ideas/${idea.id}/dismiss`));
    setData((ideas ?? []).filter((i) => i.id !== idea.id));
  };

  return (
    <div>
      <PageHeader title="Content ideas" subtitle="Let the AI suggest post ideas, then turn the best ones into full posts." />
      {can("editor") && (
        <div className="card mb-6 grid gap-4 p-5 sm:grid-cols-4 sm:items-end">
          <Field label="Theme / focus (optional)">
            <input className="input" value={theme} onChange={(e) => setTheme(e.target.value)} placeholder="e.g. board exams in March" />
          </Field>
          <Field label="Audience (optional)">
            <input className="input" value={audience} onChange={(e) => setAudience(e.target.value)} placeholder="e.g. Class 12 students" />
          </Field>
          <Field label="How many">
            <input className="input" type="number" min={1} max={20} value={count} onChange={(e) => setCount(Number(e.target.value))} />
          </Field>
          <button className="btn-primary" onClick={generate} disabled={!!busy}>
            {busy === "gen" ? <Spinner /> : "✦"} Generate content ideas
          </button>
        </div>
      )}
      {(error || loadError) && (
        <div className="mb-4">
          <Alert kind="error">{error?.message || loadError}</Alert>
        </div>
      )}
      {loading && !ideas ? (
        <Loading />
      ) : !ideas?.length ? (
        <Empty title="No open ideas">Generate a batch of ideas to get started.</Empty>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {ideas.map((idea) => (
            <div key={idea.id} className="card flex flex-col p-4">
              <div className="mb-2 flex gap-2 text-xs">
                <span className="rounded bg-indigo-50 px-2 py-0.5 font-medium text-indigo-700">{idea.category_key}</span>
                {idea.suggested_format && <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">{idea.suggested_format}</span>}
              </div>
              <div className="font-semibold text-slate-900">{idea.title}</div>
              <p className="mt-1 flex-1 text-sm text-slate-600">{idea.description}</p>
              {can("editor") && (
                <div className="mt-4 flex gap-2">
                  <button className="btn-primary flex-1" onClick={() => convert(idea)} disabled={!!busy}>
                    {busy === `c${idea.id}` && <Spinner />} Use this idea →
                  </button>
                  <button className="btn-ghost" onClick={() => dismiss(idea)} disabled={!!busy}>
                    Dismiss
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
