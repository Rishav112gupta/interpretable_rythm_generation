import { Link } from "react-router-dom";
import { Alert, CategoryPill, Empty, Loading, PageHeader, Stat, StatusBadge } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import type { Dashboard, Post } from "../types";
import { formatDateTime, relative } from "../utils/time";

function PostRow({ post, tz, when }: { post: Post; tz: string; when?: string | null }) {
  return (
    <Link to={`/posts/${post.id}`} className="flex items-center gap-3 rounded-lg px-2 py-2 hover:bg-slate-50">
      <div className="h-12 w-10 shrink-0 overflow-hidden rounded bg-slate-100">{post.image_url && <img src={post.image_url} alt="" className="h-full w-full object-cover" />}</div>
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-slate-900">{post.headline || post.topic || `Post #${post.id}`}</div>
        <div className="mt-0.5 flex flex-wrap items-center gap-2">
          <StatusBadge status={post.status} mock={post.published_via_mock} />
          <CategoryPill name={post.category_name} color={post.category_color} />
        </div>
      </div>
      {when !== undefined && (
        <div className="text-right text-xs text-slate-500">
          <div>{formatDateTime(when, tz)}</div>
          <div>{relative(when)}</div>
        </div>
      )}
    </Link>
  );
}

export default function DashboardPage() {
  const { tz, can } = useAuth();
  const { data, loading, error } = useApi(() => api.get<Dashboard>("/dashboard"));

  if (loading && !data) return <Loading />;
  if (error) return <Alert kind="error">{error}</Alert>;
  if (!data) return null;
  const c = data.counts;
  const ig = data.instagram;

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle={`All times shown in ${tz}`}
        actions={
          can("editor") && (
            <Link to="/create" className="btn-primary">
              ✚ Create post
            </Link>
          )
        }
      />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <Stat label="Total posts" value={c.total} to="/posts" />
        <Stat label="Drafts" value={c.draft} to="/posts?status=DRAFT&status=AI_GENERATED" />
        <Stat label="Pending approval" value={c.pending_approval} tone="amber" to="/posts?status=NEEDS_REVIEW" />
        <Stat label="Scheduled" value={c.scheduled} tone="indigo" to="/posts?status=SCHEDULED" />
        <Stat label="Published" value={c.published} tone="emerald" to="/posts?status=PUBLISHED" />
        <Stat label="Failed" value={c.failed} tone="rose" to="/posts?status=FAILED" />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="card p-5 lg:col-span-2">
          <h2 className="h2 mb-3">Next scheduled post</h2>
          {data.next_scheduled ? <PostRow post={data.next_scheduled} tz={tz} when={data.next_scheduled.scheduled_at} /> : <Empty title="Nothing scheduled">Approve a post and schedule it, or set up a recurring schedule.</Empty>}
          <h3 className="mt-5 mb-2 text-sm font-semibold text-slate-700">Upcoming</h3>
          {data.upcoming.length > 1 ? data.upcoming.slice(1).map((p) => <PostRow key={p.id} post={p} tz={tz} when={p.scheduled_at} />) : <p className="muted">No other upcoming posts.</p>}
          {data.planned_needing_review.length > 0 && (
            <>
              <h3 className="mt-5 mb-2 text-sm font-semibold text-slate-700">Planned slots waiting for content / approval</h3>
              {data.planned_needing_review.map((p) => (
                <PostRow key={p.id} post={p} tz={tz} when={p.desired_publish_at} />
              ))}
            </>
          )}
        </div>

        <div className="space-y-6">
          <div className="card p-5">
            <div className="mb-2 flex items-center justify-between">
              <h2 className="h2">Instagram</h2>
              <Link to="/settings?tab=instagram" className="text-xs text-indigo-600 hover:underline">
                Manage
              </Link>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className={`h-2.5 w-2.5 rounded-full ${ig.connected ? "bg-emerald-500" : "bg-rose-500"}`} />
              {ig.connected ? (
                <span>
                  Connected as <strong>@{ig.username}</strong>
                  {ig.is_mock && <span className="ml-1 rounded bg-amber-100 px-1.5 py-0.5 text-xs text-amber-800">MOCK</span>}
                </span>
              ) : (
                <span>{ig.status === "token_expired" ? "Token expired — reconnect" : "Not connected"}</span>
              )}
            </div>
            {ig.last_error && (!ig.last_success_at || (ig.last_error_at ?? "") > ig.last_success_at) && <p className="mt-2 text-xs text-rose-700">Last error: {ig.last_error}</p>}
            {!data.publishing_enabled && <p className="mt-2 text-xs font-medium text-rose-700">Publishing is paused.</p>}
          </div>

          <div className="card p-5">
            <h2 className="h2 mb-2">Recent errors</h2>
            {data.recent_errors.length === 0 ? (
              <p className="muted">No recent errors. 🎉</p>
            ) : (
              <ul className="space-y-2">
                {data.recent_errors.map((e) => (
                  <li key={e.id} className="text-xs">
                    <span className={`mr-1 rounded px-1.5 py-0.5 font-medium ${e.level === "error" ? "bg-rose-100 text-rose-800" : "bg-amber-100 text-amber-800"}`}>{e.source}</span>
                    <span className="text-slate-700">{e.message}</span>
                    <div className="text-slate-400">
                      {formatDateTime(e.created_at, tz)}
                      {e.post_id && (
                        <Link className="ml-2 text-indigo-600" to={`/posts/${e.post_id}`}>
                          Post #{e.post_id}
                        </Link>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>

      <div className="card mt-6 p-5">
        <h2 className="h2 mb-2">Recently updated</h2>
        {data.recent.length ? data.recent.map((p) => <PostRow key={p.id} post={p} tz={tz} when={p.published_at || p.scheduled_at || p.desired_publish_at} />) : <Empty title="No posts yet">Create your first post to get started.</Empty>}
      </div>
    </div>
  );
}
