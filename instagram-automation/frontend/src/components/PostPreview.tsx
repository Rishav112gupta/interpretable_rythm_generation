import type { Post } from "../types";

/** Instagram-feed-like preview so reviewers see what followers will see. */
export default function PostPreview({ post, username }: { post: Pick<Post, "image_url" | "caption" | "hashtags" | "headline">; username?: string }) {
  const name = username || "your_company";
  return (
    <div className="card mx-auto w-full max-w-sm overflow-hidden">
      <div className="flex items-center gap-2 px-3 py-2">
        <div className="h-8 w-8 rounded-full bg-gradient-to-tr from-amber-400 via-rose-500 to-fuchsia-600 p-0.5">
          <div className="h-full w-full rounded-full bg-white" />
        </div>
        <div className="text-sm font-semibold">{name}</div>
      </div>
      <div className="aspect-[4/5] w-full bg-slate-100">
        {post.image_url ? (
          <img src={post.image_url} alt={post.headline || "Post image"} className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center text-sm text-slate-400">No image yet</div>
        )}
      </div>
      <div className="flex gap-4 px-3 pt-2 text-xl text-slate-700" aria-hidden>
        <span>♡</span>
        <span>💬</span>
        <span>➤</span>
      </div>
      <div className="max-h-72 overflow-y-auto px-3 pt-1 pb-3 text-sm whitespace-pre-wrap text-slate-800">
        <span className="font-semibold">{name}</span> {post.caption || <span className="text-slate-400">Caption will appear here…</span>}
        {post.hashtags.length > 0 && <div className="mt-2 text-indigo-700">{post.hashtags.map((h) => `#${h}`).join(" ")}</div>}
      </div>
    </div>
  );
}
