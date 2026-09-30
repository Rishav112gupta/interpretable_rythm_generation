import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Alert, CategoryPill, Empty, Loading, PageHeader, STATUS_STYLES, StatusBadge } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import type { Category, Post, PostStatus } from "../types";
import { formatDateTime } from "../utils/time";

export default function PostsPage() {
  const { tz, can } = useAuth();
  const [params, setParams] = useSearchParams();
  const statuses = params.getAll("status");
  const [q, setQ] = useState(params.get("q") ?? "");
  const categoryId = params.get("category_id") ?? "";
  const { data: categories } = useApi(() => api.get<Category[]>("/categories"));
  const { data, loading, error } = useApi(
    () => api.get<{ items: Post[]; total: number }>("/posts", { status: statuses, q: params.get("q"), category_id: categoryId, limit: 200 }),
    [params.toString()],
  );

  const toggleStatus = (s: string) => {
    const next = new URLSearchParams(params);
    const cur = next.getAll("status");
    next.delete("status");
    (cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]).forEach((x) => next.append("status", x));
    setParams(next);
  };

  return (
    <div>
      <PageHeader
        title="Posts"
        subtitle={data ? `${data.total} post(s)` : undefined}
        actions={
          can("editor") && (
            <Link to="/create" className="btn-primary">
              ✚ Create post
            </Link>
          )
        }
      />
      <div className="card mb-4 space-y-3 p-4">
        <div className="flex flex-wrap gap-2">
          {(Object.keys(STATUS_STYLES) as PostStatus[]).map((s) => (
            <button key={s} onClick={() => toggleStatus(s)} className={`rounded-full px-3 py-1 text-xs font-medium ring-1 ${statuses.includes(s) ? "bg-indigo-600 text-white ring-indigo-600" : "bg-white text-slate-600 ring-slate-300 hover:bg-slate-50"}`}>
              {STATUS_STYLES[s].label}
            </button>
          ))}
        </div>
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const next = new URLSearchParams(params);
            if (q) next.set("q", q);
            else next.delete("q");
            setParams(next);
          }}
        >
          <input className="input max-w-xs" placeholder="Search topic, headline, caption…" value={q} onChange={(e) => setQ(e.target.value)} />
          <select
            className="input max-w-xs"
            value={categoryId}
            onChange={(e) => {
              const next = new URLSearchParams(params);
              if (e.target.value) next.set("category_id", e.target.value);
              else next.delete("category_id");
              setParams(next);
            }}
          >
            <option value="">All categories</option>
            {categories?.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <button className="btn-secondary">Search</button>
        </form>
      </div>
      {error && <Alert kind="error">{error}</Alert>}
      {loading && !data ? (
        <Loading />
      ) : data && data.items.length === 0 ? (
        <Empty title="No posts match">Try other filters or create a post.</Empty>
      ) : (
        <div className="card overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm">
            <thead className="bg-slate-50 text-left text-xs font-semibold tracking-wide text-slate-500 uppercase">
              <tr>
                <th className="px-4 py-3">Post</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Category</th>
                <th className="px-4 py-3">Publish time</th>
                <th className="px-4 py-3">Updated</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data?.items.map((p) => (
                <tr key={p.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link to={`/posts/${p.id}`} className="flex items-center gap-3">
                      <div className="h-12 w-10 shrink-0 overflow-hidden rounded bg-slate-100">{p.image_url && <img src={p.image_url} alt="" className="h-full w-full object-cover" />}</div>
                      <div className="min-w-0">
                        <div className="max-w-md truncate font-medium text-slate-900">{p.headline || p.topic || `Post #${p.id}`}</div>
                        <div className="max-w-md truncate text-xs text-slate-500">{p.topic}</div>
                      </div>
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={p.status} mock={p.published_via_mock} />
                    {(p.review_flags.length > 0 || p.missing_information.length > 0) && ["NEEDS_REVIEW", "AI_GENERATED"].includes(p.status) && <div className="mt-1 text-xs text-amber-700">⚠ needs fact check</div>}
                  </td>
                  <td className="px-4 py-3">
                    <CategoryPill name={p.category_name} color={p.category_color} />
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-slate-600">{formatDateTime(p.published_at || p.scheduled_at || p.desired_publish_at, tz)}</td>
                  <td className="px-4 py-3 whitespace-nowrap text-slate-500">{formatDateTime(p.updated_at, tz)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
