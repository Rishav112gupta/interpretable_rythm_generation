import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { PostStatus } from "../types";

export const STATUS_STYLES: Record<PostStatus, { label: string; cls: string; dot: string }> = {
  DRAFT: { label: "Draft", cls: "bg-slate-100 text-slate-700 ring-slate-200", dot: "bg-slate-400" },
  AI_GENERATED: { label: "AI generated", cls: "bg-violet-50 text-violet-700 ring-violet-200", dot: "bg-violet-500" },
  NEEDS_REVIEW: { label: "Needs review", cls: "bg-amber-50 text-amber-800 ring-amber-200", dot: "bg-amber-500" },
  APPROVED: { label: "Approved", cls: "bg-sky-50 text-sky-700 ring-sky-200", dot: "bg-sky-500" },
  SCHEDULED: { label: "Scheduled", cls: "bg-indigo-50 text-indigo-700 ring-indigo-200", dot: "bg-indigo-500" },
  PUBLISHING: { label: "Publishing…", cls: "bg-indigo-50 text-indigo-700 ring-indigo-200", dot: "bg-indigo-500 animate-pulse" },
  PUBLISHED: { label: "Published", cls: "bg-emerald-50 text-emerald-700 ring-emerald-200", dot: "bg-emerald-500" },
  REJECTED: { label: "Rejected", cls: "bg-rose-50 text-rose-700 ring-rose-200", dot: "bg-rose-400" },
  FAILED: { label: "Failed", cls: "bg-rose-100 text-rose-800 ring-rose-300", dot: "bg-rose-600" },
};

export function StatusBadge({ status, mock }: { status: PostStatus; mock?: boolean }) {
  const s = STATUS_STYLES[status] ?? STATUS_STYLES.DRAFT;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${s.cls}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {s.label}
      {mock && status === "PUBLISHED" ? " (simulated)" : ""}
    </span>
  );
}

export function CategoryPill({ name, color }: { name: string | null; color: string | null }) {
  if (!name) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
      <span className="h-2 w-2 rounded-sm" style={{ background: color || "#94a3b8" }} />
      {name}
    </span>
  );
}

export function Alert({ kind = "info", title, children, onClose }: { kind?: "info" | "warning" | "error" | "success"; title?: string; children?: ReactNode; onClose?: () => void }) {
  const cls = {
    info: "border-sky-200 bg-sky-50 text-sky-900",
    warning: "border-amber-200 bg-amber-50 text-amber-900",
    error: "border-rose-200 bg-rose-50 text-rose-900",
    success: "border-emerald-200 bg-emerald-50 text-emerald-900",
  }[kind];
  return (
    <div className={`relative rounded-lg border px-4 py-3 text-sm ${cls}`} role={kind === "error" ? "alert" : "status"}>
      {title && <div className="font-semibold">{title}</div>}
      {children && <div className={title ? "mt-1" : ""}>{children}</div>}
      {onClose && (
        <button className="absolute top-2 right-2 rounded px-1.5 text-lg leading-none opacity-60 hover:opacity-100" onClick={onClose} aria-label="Dismiss">
          ×
        </button>
      )}
    </div>
  );
}

export function Spinner({ className = "h-4 w-4" }: { className?: string }) {
  return <span className={`inline-block animate-spin rounded-full border-2 border-current border-r-transparent ${className}`} aria-label="Loading" />;
}

export function Loading({ text = "Loading…" }: { text?: string }) {
  return (
    <div className="flex items-center gap-2 py-10 text-slate-500 justify-center">
      <Spinner /> {text}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-slate-300 bg-white px-6 py-10 text-center">
      <div className="font-medium text-slate-700">{title}</div>
      {children && <div className="mt-1 text-sm text-slate-500">{children}</div>}
    </div>
  );
}

export function Field({ label, hint, children, required }: { label: string; hint?: string; children: ReactNode; required?: boolean }) {
  return (
    <label className="block">
      <span className="label">
        {label}
        {required && <span className="text-rose-500"> *</span>}
      </span>
      {children}
      {hint && <span className="mt-1 block text-xs text-slate-500">{hint}</span>}
    </label>
  );
}

export function Modal({ open, title, onClose, children, footer, wide }: { open: boolean; title: string; onClose: () => void; children: ReactNode; footer?: ReactNode; wide?: boolean }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-slate-900/40 p-4 pt-16" onMouseDown={onClose}>
      <div className={`card w-full ${wide ? "max-w-3xl" : "max-w-lg"}`} onMouseDown={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={title}>
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
          <h3 className="h2">{title}</h3>
          <button className="btn-ghost px-2 py-1" onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
        <div className="space-y-4 px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-slate-200 px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}

export function Stat({ label, value, tone = "slate", to }: { label: string; value: number | string; tone?: string; to?: string }) {
  const color: Record<string, string> = {
    slate: "text-slate-900",
    amber: "text-amber-600",
    indigo: "text-indigo-600",
    emerald: "text-emerald-600",
    rose: "text-rose-600",
    sky: "text-sky-600",
  };
  const inner = (
    <div className="card px-4 py-3 transition hover:border-indigo-300">
      <div className="text-xs font-medium tracking-wide text-slate-500 uppercase">{label}</div>
      <div className={`mt-1 text-2xl font-semibold ${color[tone] ?? color.slate}`}>{value}</div>
    </div>
  );
  return to ? <Link to={to}>{inner}</Link> : inner;
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="h1">{title}</h1>
        {subtitle && <p className="muted mt-1">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { key: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div className="mb-5 flex flex-wrap gap-1 border-b border-slate-200">
      {tabs.map((t) => (
        <button
          key={t.key}
          onClick={() => onChange(t.key)}
          className={`-mb-px border-b-2 px-3 py-2 text-sm font-medium ${value === t.key ? "border-indigo-600 text-indigo-700" : "border-transparent text-slate-500 hover:text-slate-800"}`}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

/** Comma/newline separated list <-> string[] */
export function ListInput({ value, onChange, placeholder, rows = 2 }: { value: string[]; onChange: (v: string[]) => void; placeholder?: string; rows?: number }) {
  return (
    <textarea
      className="input"
      rows={rows}
      placeholder={placeholder}
      defaultValue={value.join("\n")}
      onBlur={(e) =>
        onChange(
          e.target.value
            .split(/[\n,]/)
            .map((s) => s.trim())
            .filter(Boolean),
        )
      }
    />
  );
}
