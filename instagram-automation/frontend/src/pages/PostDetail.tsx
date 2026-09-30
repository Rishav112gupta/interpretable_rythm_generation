import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import PostPreview from "../components/PostPreview";
import { Alert, CategoryPill, Field, Loading, Modal, Spinner, StatusBadge } from "../components/ui";
import { useAction, useApi } from "../hooks/useApi";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import type { Category, InstagramStatus, PostDetail, Template } from "../types";
import { formatDateTime, isoToZonedLocal, relative, zonedLocalToIso } from "../utils/time";

type Draft = { headline: string; subtitle: string; caption: string; hashtags: string; alternative_caption: string; image_prompt: string; category_id: string; template_id: string };

const toDraft = (p: PostDetail): Draft => ({
  headline: p.headline,
  subtitle: p.subtitle,
  caption: p.caption,
  hashtags: p.hashtags.map((h) => `#${h}`).join(" "),
  alternative_caption: p.alternative_caption,
  image_prompt: p.image_prompt,
  category_id: p.category_id ? String(p.category_id) : "",
  template_id: p.template_id ? String(p.template_id) : "",
});

const EDITABLE = ["DRAFT", "AI_GENERATED", "NEEDS_REVIEW", "APPROVED", "SCHEDULED", "FAILED", "REJECTED"];

export default function PostDetailPage() {
  const { id } = useParams();
  const location = useLocation();
  const navigate = useNavigate();
  const { tz, can } = useAuth();
  const { data: post, setData: setPost, loading, error: loadError } = useApi(() => api.get<PostDetail>(`/posts/${id}`), [id]);
  const { data: meta } = useApi(() => Promise.all([api.get<Category[]>("/categories"), api.get<Template[]>("/templates"), api.get<InstagramStatus>("/instagram/status")]));
  const { busy, error, setError, run } = useAction();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [warnings, setWarnings] = useState<string[]>((location.state as { warnings?: string[] })?.warnings ?? []);
  const [modal, setModal] = useState<null | "approve" | "reject" | "schedule" | "regen" | "upload" | "publish">(null);
  const [ack, setAck] = useState(false);
  const [reason, setReason] = useState("");
  const [feedback, setFeedback] = useState("");
  const [when, setWhen] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [applyTemplate, setApplyTemplate] = useState(true);

  useEffect(() => {
    if (post) setDraft(toDraft(post));
  }, [post]);

  if (loading && !post) return <Loading />;
  if (loadError || !post || !draft) return <Alert kind="error">{loadError || "Post not found"}</Alert>;

  const editable = EDITABLE.includes(post.status) && can("editor");
  const original = toDraft(post);
  const dirty = JSON.stringify(original) !== JSON.stringify(draft);
  const hasFlags = post.review_flags.length > 0 || post.missing_information.length > 0;

  const apply = (p: PostDetail | undefined) => {
    if (!p) return;
    setPost(p);
    setWarnings(p.warnings ?? []);
    setModal(null);
  };

  const save = () =>
    run("save", () =>
      api.patch<PostDetail>(`/posts/${post.id}`, {
        headline: draft.headline,
        subtitle: draft.subtitle,
        caption: draft.caption,
        alternative_caption: draft.alternative_caption,
        image_prompt: draft.image_prompt,
        hashtags: draft.hashtags.split(/[\s,]+/).filter(Boolean),
        category_id: draft.category_id ? Number(draft.category_id) : null,
        template_id: draft.template_id ? Number(draft.template_id) : null,
      }),
    ).then(apply);

  const action = (name: string, path: string, body?: Record<string, unknown>) => run(name, () => api.post<PostDetail>(`/posts/${post.id}/${path}`, body)).then(apply);

  const upload = async () => {
    if (!file) return;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("apply_template", String(applyTemplate));
    await run("upload", () => api.post<PostDetail>(`/posts/${post.id}/image`, fd)).then(apply);
    setFile(null);
  };

  const del = async () => {
    if (!confirm("Delete this post permanently?")) return;
    await run("delete", () => api.del(`/posts/${post.id}`));
    navigate("/posts");
  };

  const [categories, templates, ig] = meta ?? [[], [], null];

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <Link to="/posts" className="text-sm text-indigo-600 hover:underline">
            ← All posts
          </Link>
          <h1 className="h1 mt-1">{post.headline || post.topic || `Post #${post.id}`}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <StatusBadge status={post.status} mock={post.published_via_mock} />
            <CategoryPill name={post.category_name} color={post.category_color} />
            {post.schedule_id && <span className="text-xs text-slate-500">From recurring schedule #{post.schedule_id}</span>}
          </div>
        </div>
        <ActionBar
          post={post}
          busy={busy}
          can={can}
          onGenerate={() => action("generate", "generate")}
          onSubmit={() => action("submit", "submit")}
          open={(m) => {
            setAck(false);
            setWhen(isoToZonedLocal(post.scheduled_at || post.desired_publish_at, tz));
            setModal(m);
          }}
          onUnschedule={() => action("unschedule", "unschedule")}
          onDelete={del}
        />
      </div>

      <div className="space-y-3">
        {error && (
          <Alert kind="error" title="Action failed" onClose={() => setError(null)}>
            {error.message}
          </Alert>
        )}
        {warnings.map((w) => (
          <Alert key={w} kind={w.startsWith("MOCK") ? "warning" : "warning"} onClose={() => setWarnings(warnings.filter((x) => x !== w))}>
            {w}
          </Alert>
        ))}
        {post.status === "PUBLISHED" && (
          <Alert kind={post.published_via_mock ? "warning" : "success"} title={post.published_via_mock ? "Simulated publish (mock mode)" : "Published to Instagram"}>
            {post.published_via_mock ? (
              "This post was NOT posted to Instagram. Real publishing requires Meta configuration and credentials (see README)."
            ) : (
              <>
                Published {formatDateTime(post.published_at, tz)}.{" "}
                {post.instagram_permalink && (
                  <a href={post.instagram_permalink} target="_blank" rel="noreferrer" className="font-medium underline">
                    View on Instagram
                  </a>
                )}
                {post.like_count !== null && ` · ${post.like_count} likes · ${post.comments_count ?? 0} comments`}
              </>
            )}
          </Alert>
        )}
        {post.status === "SCHEDULED" && (
          <Alert kind="info">
            Scheduled for <strong>{formatDateTime(post.scheduled_at, tz)}</strong> ({relative(post.scheduled_at)}).
            {post.next_retry_at && (
              <>
                {" "}
                Retry {post.publish_attempts} pending — next attempt {relative(post.next_retry_at)}. Last error: {post.last_error}
              </>
            )}
          </Alert>
        )}
        {post.status === "FAILED" && (
          <Alert kind="error" title={`Publishing failed after ${post.publish_attempts} attempt(s)`}>
            {post.last_error} — fix the problem, then schedule again.
          </Alert>
        )}
        {post.status === "REJECTED" && post.rejected_reason && <Alert kind="error" title="Rejected">{post.rejected_reason}</Alert>}
        {hasFlags && !["PUBLISHED"].includes(post.status) && (
          <Alert kind="warning" title="Human review required — possible unverified facts or missing information">
            <ul className="mt-1 list-disc space-y-0.5 pl-5">
              {post.missing_information.map((m) => (
                <li key={m}>{m}</li>
              ))}
              {post.review_flags.map((f, i) => (
                <li key={i}>{f.message}</li>
              ))}
            </ul>
            {post.flags_acknowledged && <div className="mt-1 text-xs">Acknowledged by the approver.</div>}
          </Alert>
        )}
      </div>

      <div className="mt-5 grid gap-6 lg:grid-cols-5">
        <div className="space-y-5 lg:col-span-3">
          <div className="card space-y-4 p-5">
            <div className="flex items-center justify-between">
              <h2 className="h2">Content</h2>
              {editable && (
                <div className="flex gap-2">
                  {post.generated_at && (
                    <button className="btn-secondary" onClick={() => setModal("regen")} disabled={!!busy}>
                      ↻ Regenerate text
                    </button>
                  )}
                  <button className="btn-primary" onClick={save} disabled={!dirty || !!busy}>
                    {busy === "save" && <Spinner />} Save changes
                  </button>
                </div>
              )}
            </div>
            {dirty && ["APPROVED", "SCHEDULED"].includes(post.status) && <Alert kind="warning">Saving changes to an approved post sends it back for re-approval.</Alert>}
            <fieldset disabled={!editable} className="space-y-4">
              <Field label={`Headline (on image) — ${draft.headline.length}/120`}>
                <input className="input" maxLength={120} value={draft.headline} onChange={(e) => setDraft({ ...draft, headline: e.target.value })} />
              </Field>
              <Field label="Subtitle (on image)">
                <input className="input" maxLength={200} value={draft.subtitle} onChange={(e) => setDraft({ ...draft, subtitle: e.target.value })} />
              </Field>
              <Field label={`Caption — ${draft.caption.length}/2200`}>
                <textarea className="input font-[inherit]" rows={10} maxLength={2200} value={draft.caption} onChange={(e) => setDraft({ ...draft, caption: e.target.value })} />
              </Field>
              <Field label={`Hashtags — ${draft.hashtags.split(/[\s,]+/).filter(Boolean).length}/30`} hint="Separate with spaces. Instagram allows at most 30.">
                <textarea className="input" rows={2} value={draft.hashtags} onChange={(e) => setDraft({ ...draft, hashtags: e.target.value })} />
              </Field>
              {draft.alternative_caption && (
                <Field label="Alternative caption">
                  <div className="space-y-2">
                    <textarea className="input" rows={3} value={draft.alternative_caption} onChange={(e) => setDraft({ ...draft, alternative_caption: e.target.value })} />
                    {editable && (
                      <button type="button" className="btn-ghost text-xs" onClick={() => setDraft({ ...draft, caption: draft.alternative_caption, alternative_caption: draft.caption })}>
                        ⇅ Swap with main caption
                      </button>
                    )}
                  </div>
                </Field>
              )}
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Category">
                  <select className="input" value={draft.category_id} onChange={(e) => setDraft({ ...draft, category_id: e.target.value })}>
                    <option value="">— General —</option>
                    {categories.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label="Template">
                  <select className="input" value={draft.template_id} onChange={(e) => setDraft({ ...draft, template_id: e.target.value })}>
                    <option value="">— Category default —</option>
                    {templates.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.name}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>
              <Field label="Image prompt" hint="Used when regenerating the image.">
                <textarea className="input text-xs" rows={3} value={draft.image_prompt} onChange={(e) => setDraft({ ...draft, image_prompt: e.target.value })} />
              </Field>
            </fieldset>
          </div>

          <details className="card p-5">
            <summary className="cursor-pointer font-semibold text-slate-800">Post brief (inputs given to the AI)</summary>
            <dl className="mt-3 grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              {(
                [
                  ["Topic", post.topic],
                  ["Target audience", post.target_audience],
                  ["Tone", post.tone],
                  ["Objective", post.objective],
                  ["Important information", post.important_info],
                  ["Call to action", post.cta],
                  ["Language", post.language],
                  ["Desired publish time", post.desired_publish_at ? formatDateTime(post.desired_publish_at, tz) : ""],
                  ["Brand instructions", post.brand_instructions],
                  ["Image instructions", post.image_instructions],
                ] as [string, string][]
              ).map(([k, v]) => (
                <div key={k}>
                  <dt className="text-xs text-slate-500">{k}</dt>
                  <dd className="whitespace-pre-wrap text-slate-800">{v || "—"}</dd>
                </div>
              ))}
            </dl>
          </details>

          <details className="card p-5">
            <summary className="cursor-pointer font-semibold text-slate-800">History ({post.events.length})</summary>
            <ol className="mt-3 space-y-2 border-l border-slate-200 pl-4 text-sm">
              {[...post.events].reverse().map((e) => (
                <li key={e.id}>
                  <div className="text-xs text-slate-400">{formatDateTime(e.created_at, tz)}</div>
                  <div className="text-slate-800">
                    <span className="font-medium">{e.event_type.replace(/_/g, " ")}</span>
                    {e.to_status && (
                      <span className="text-slate-500">
                        {" "}
                        {e.from_status ? `${e.from_status} → ` : "→ "}
                        {e.to_status}
                      </span>
                    )}
                  </div>
                  {e.message && <div className="text-xs text-slate-600">{e.message}</div>}
                </li>
              ))}
            </ol>
          </details>
        </div>

        <div className="space-y-5 lg:col-span-2">
          <PostPreview post={{ ...post, caption: draft.caption, hashtags: draft.hashtags.split(/[\s,]+/).filter(Boolean).map((h) => h.replace(/^#/, "")) }} username={ig?.username} />
          {editable && (
            <div className="card flex flex-wrap gap-2 p-4">
              <button className="btn-secondary flex-1" onClick={() => action("regen-image", "regenerate-image")} disabled={!!busy || !post.image_prompt}>
                {busy === "regen-image" ? <Spinner /> : "🎨"} Regenerate image
              </button>
              <button className="btn-secondary flex-1" onClick={() => setModal("upload")} disabled={!!busy}>
                ⬆ Replace image
              </button>
              {post.image_url && (
                <a className="btn-ghost w-full text-xs" href={post.image_url} target="_blank" rel="noreferrer">
                  Open full-size image
                </a>
              )}
            </div>
          )}
          <div className="card p-4 text-xs text-slate-600">
            <div className="mb-1 font-semibold text-slate-800">AI generation details</div>
            <div>
              Text: {post.llm_provider || "—"} {post.llm_model && `/ ${post.llm_model}`} {post.generation_ms != null && `· ${(post.generation_ms / 1000).toFixed(1)}s`}
            </div>
            <div>
              Image: {post.image_provider || "—"} {post.image_model && `/ ${post.image_model}`} {post.image_generation_ms != null && `· ${(post.image_generation_ms / 1000).toFixed(1)}s`}
            </div>
            <div>
              Prompt version: {post.prompt_version || "—"} · text regenerations: {post.regeneration_count} · image regenerations: {post.image_regeneration_count}
            </div>
            <div>Created by {post.created_by_name || "system"} · {formatDateTime(post.created_at, tz)}</div>
          </div>
        </div>
      </div>

      {/* ------------------------------------------------------------ modals */}
      <Modal
        open={modal === "approve"}
        title="Approve post"
        onClose={() => setModal(null)}
        footer={
          <>
            <button className="btn-secondary" onClick={() => setModal(null)}>
              Cancel
            </button>
            <button
              className="btn-success"
              disabled={!!busy || (hasFlags && !ack)}
              onClick={() => action("approve", "approve", { acknowledge_flags: ack, schedule_at: when ? zonedLocalToIso(when, tz) : null, use_desired_time: false })}
            >
              {busy === "approve" && <Spinner />} Approve{when ? " & schedule" : ""}
            </button>
          </>
        }
      >
        {hasFlags && (
          <label className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
            <input type="checkbox" className="mt-1" checked={ack} onChange={(e) => setAck(e.target.checked)} />
            <span>I have checked the flagged items and confirm every price, date, claim and contact detail in this post is correct and approved by the company.</span>
          </label>
        )}
        <Field label={`Schedule for (${tz})`} hint="Leave empty to approve without scheduling.">
          <input className="input" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
        </Field>
      </Modal>

      <Modal
        open={modal === "schedule"}
        title="Schedule post"
        onClose={() => setModal(null)}
        footer={
          <button className="btn-primary" disabled={!when || !!busy} onClick={() => action("schedule", "schedule", { scheduled_at: zonedLocalToIso(when, tz) })}>
            {busy === "schedule" && <Spinner />} Schedule
          </button>
        }
      >
        <Field label={`Publish at (${tz})`}>
          <input className="input" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} />
        </Field>
        <p className="muted">The scheduler publishes within about a minute of this time through the official Instagram API.</p>
      </Modal>

      <Modal
        open={modal === "reject"}
        title="Reject post"
        onClose={() => setModal(null)}
        footer={
          <button className="btn-danger" disabled={!!busy} onClick={() => action("reject", "reject", { reason })}>
            Reject
          </button>
        }
      >
        <Field label="Reason (helps the next regeneration)">
          <textarea className="input" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
        </Field>
      </Modal>

      <Modal
        open={modal === "regen"}
        title="Regenerate text"
        onClose={() => setModal(null)}
        footer={
          <button className="btn-primary" disabled={!!busy} onClick={() => action("regen", "regenerate-text", { feedback })}>
            {busy === "regen" && <Spinner />} Regenerate
          </button>
        }
      >
        <Field label="What should change? (optional)" hint="e.g. shorter, more energetic, mention the weekend batch">
          <textarea className="input" rows={3} value={feedback} onChange={(e) => setFeedback(e.target.value)} />
        </Field>
        <p className="muted">Your current unsaved edits will be replaced.</p>
      </Modal>

      <Modal
        open={modal === "upload"}
        title="Replace image"
        onClose={() => setModal(null)}
        footer={
          <button className="btn-primary" disabled={!file || !!busy} onClick={upload}>
            {busy === "upload" && <Spinner />} Upload
          </button>
        }
      >
        <input type="file" accept="image/jpeg,image/png,image/webp" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={applyTemplate} onChange={(e) => setApplyTemplate(e.target.checked)} />
          Place the image inside the post template (with headline, logo…)
        </label>
        <p className="muted">Unchecked: the image is used as-is, converted to JPEG and cropped to Instagram's allowed 4:5–1.91:1 ratio.</p>
      </Modal>

      <Modal
        open={modal === "publish"}
        title="Publish now?"
        onClose={() => setModal(null)}
        footer={
          <button className="btn-success" disabled={!!busy} onClick={() => action("publish", "publish")}>
            {busy === "publish" && <Spinner />} Publish now
          </button>
        }
      >
        <p className="text-sm">
          This publishes the approved post to <strong>@{ig?.username || "your account"}</strong> immediately{ig?.is_mock ? " — in MOCK mode this is only a simulation" : " through the official Instagram API"}.
        </p>
      </Modal>
    </div>
  );
}

function ActionBar({
  post,
  busy,
  can,
  onGenerate,
  onSubmit,
  open,
  onUnschedule,
  onDelete,
}: {
  post: PostDetail;
  busy: string | null;
  can: (r: "editor" | "approver") => boolean;
  onGenerate: () => void;
  onSubmit: () => void;
  open: (m: "approve" | "reject" | "schedule" | "publish") => void;
  onUnschedule: () => void;
  onDelete: () => void;
}) {
  const s = post.status;
  return (
    <div className="flex flex-wrap gap-2">
      {can("editor") && ["DRAFT", "REJECTED"].includes(s) && (
        <button className="btn-primary" onClick={onGenerate} disabled={!!busy}>
          {busy === "generate" ? <Spinner /> : "✨"} {post.generated_at ? "Regenerate all" : "Generate with AI"}
        </button>
      )}
      {can("editor") && ["DRAFT", "AI_GENERATED", "REJECTED"].includes(s) && post.caption && (
        <button className="btn-secondary" onClick={onSubmit} disabled={!!busy}>
          Submit for review
        </button>
      )}
      {can("approver") && ["NEEDS_REVIEW", "AI_GENERATED"].includes(s) && (
        <button className="btn-success" onClick={() => open("approve")} disabled={!!busy}>
          ✓ Approve
        </button>
      )}
      {can("approver") && ["APPROVED", "FAILED", "SCHEDULED"].includes(s) && (
        <button className="btn-primary" onClick={() => open("schedule")} disabled={!!busy}>
          🗓 {s === "SCHEDULED" ? "Reschedule" : "Schedule"}
        </button>
      )}
      {can("approver") && s === "SCHEDULED" && (
        <button className="btn-secondary" onClick={onUnschedule} disabled={!!busy}>
          Unschedule
        </button>
      )}
      {can("approver") && ["APPROVED", "SCHEDULED"].includes(s) && (
        <button className="btn-success" onClick={() => open("publish")} disabled={!!busy}>
          ➤ Publish now
        </button>
      )}
      {can("approver") && !["PUBLISHED", "PUBLISHING", "REJECTED"].includes(s) && (
        <button className="btn-secondary text-rose-700" onClick={() => open("reject")} disabled={!!busy}>
          ✕ Reject
        </button>
      )}
      {can("approver") && !["PUBLISHED", "PUBLISHING"].includes(s) && (
        <button className="btn-ghost text-rose-600" onClick={onDelete} disabled={!!busy}>
          Delete
        </button>
      )}
    </div>
  );
}
