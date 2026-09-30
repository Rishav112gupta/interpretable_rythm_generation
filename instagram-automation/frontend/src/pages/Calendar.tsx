import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Alert, PageHeader, STATUS_STYLES } from "../components/ui";
import { useApi } from "../hooks/useApi";
import { useAuth } from "../hooks/useAuth";
import { api } from "../services/api";
import type { Post } from "../types";
import { dayKey, formatDateTime, zonedLocalToIso } from "../utils/time";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function CalendarPage() {
  const { tz } = useAuth();
  const today = new Date();
  const [month, setMonth] = useState({ y: today.getFullYear(), m: today.getMonth() }); // m: 0-11

  const grid = useMemo(() => {
    const first = new Date(Date.UTC(month.y, month.m, 1));
    const offset = (first.getUTCDay() + 6) % 7; // Monday first
    const start = new Date(Date.UTC(month.y, month.m, 1 - offset));
    return Array.from({ length: 42 }, (_, i) => new Date(start.getTime() + i * 86400000));
  }, [month]);

  const pad = (n: number) => String(n).padStart(2, "0");
  const key = (d: Date) => `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
  const rangeStart = zonedLocalToIso(`${key(grid[0])}T00:00`, tz);
  const rangeEnd = zonedLocalToIso(`${key(grid[41])}T23:59`, tz);
  const { data, error } = useApi(() => api.get<Post[]>("/posts/calendar", { start: rangeStart, end: rangeEnd }), [rangeStart, rangeEnd]);

  const byDay = useMemo(() => {
    const map: Record<string, Post[]> = {};
    for (const p of data ?? []) {
      const when = p.published_at || p.scheduled_at || p.desired_publish_at;
      if (!when) continue;
      (map[dayKey(when, tz)] ||= []).push(p);
    }
    return map;
  }, [data, tz]);

  const todayKey = dayKey(new Date().toISOString(), tz);
  const monthName = new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" }).format(new Date(Date.UTC(month.y, month.m, 1)));
  const shift = (delta: number) => setMonth(({ y, m }) => ({ y: y + Math.floor((m + delta) / 12), m: (((m + delta) % 12) + 12) % 12 }));

  return (
    <div>
      <PageHeader
        title="Content calendar"
        subtitle={`Posts by publish / scheduled / planned date (${tz})`}
        actions={
          <>
            <button className="btn-secondary" onClick={() => shift(-1)}>
              ←
            </button>
            <div className="flex min-w-40 items-center justify-center font-semibold">{monthName}</div>
            <button className="btn-secondary" onClick={() => shift(1)}>
              →
            </button>
            <button className="btn-ghost" onClick={() => setMonth({ y: today.getFullYear(), m: today.getMonth() })}>
              Today
            </button>
          </>
        }
      />
      {error && <Alert kind="error">{error}</Alert>}
      <div className="mb-3 flex flex-wrap gap-3 text-xs">
        {(["DRAFT", "NEEDS_REVIEW", "APPROVED", "SCHEDULED", "PUBLISHED", "FAILED"] as const).map((s) => (
          <span key={s} className="flex items-center gap-1">
            <span className={`h-2 w-2 rounded-full ${STATUS_STYLES[s].dot}`} />
            {STATUS_STYLES[s].label}
          </span>
        ))}
      </div>
      <div className="card overflow-hidden">
        <div className="grid grid-cols-7 border-b border-slate-200 bg-slate-50 text-center text-xs font-semibold text-slate-500">
          {WEEKDAYS.map((d) => (
            <div key={d} className="py-2">
              {d}
            </div>
          ))}
        </div>
        <div className="grid grid-cols-7">
          {grid.map((d) => {
            const k = key(d);
            const inMonth = d.getUTCMonth() === month.m;
            const posts = byDay[k] ?? [];
            return (
              <div key={k} className={`min-h-28 border-r border-b border-slate-100 p-1.5 ${inMonth ? "bg-white" : "bg-slate-50/60"}`}>
                <div className={`mb-1 text-xs ${k === todayKey ? "inline-flex h-5 w-5 items-center justify-center rounded-full bg-indigo-600 text-white" : inMonth ? "text-slate-700" : "text-slate-400"}`}>{d.getUTCDate()}</div>
                <div className="space-y-1">
                  {posts.map((p) => {
                    const st = STATUS_STYLES[p.status];
                    return (
                      <Link
                        key={p.id}
                        to={`/posts/${p.id}`}
                        title={`${st.label} · ${formatDateTime(p.published_at || p.scheduled_at || p.desired_publish_at, tz)}`}
                        className={`block truncate rounded px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset ${st.cls}`}
                        style={{ borderLeft: `3px solid ${p.category_color || "#94a3b8"}` }}
                      >
                        {p.category_name ? `[${p.category_name}] ` : ""}
                        {p.headline || p.topic || `#${p.id}`}
                      </Link>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
