/** Timezone helpers. All API datetimes are ISO strings (UTC); the UI shows them
 * in the company timezone from Settings (default Asia/Kolkata). */

export function formatDateTime(iso: string | null | undefined, tz: string, opts: Intl.DateTimeFormatOptions = {}): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("en-GB", {
    timeZone: tz,
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    ...opts,
  }).format(new Date(iso));
}

export function formatDate(iso: string | null | undefined, tz: string): string {
  return formatDateTime(iso, tz, { hour: undefined, minute: undefined });
}

function parts(date: Date, tz: string) {
  const p = new Intl.DateTimeFormat("en-US", {
    timeZone: tz,
    hourCycle: "h23",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(date);
  const get = (t: string) => Number(p.find((x) => x.type === t)?.value);
  return { y: get("year"), m: get("month"), d: get("day"), h: get("hour"), mi: get("minute"), s: get("second") };
}

/** Offset (minutes) of `tz` from UTC at the given instant. */
function offsetMinutes(date: Date, tz: string): number {
  const x = parts(date, tz);
  const asUtc = Date.UTC(x.y, x.m - 1, x.d, x.h, x.mi, x.s);
  return Math.round((asUtc - date.getTime()) / 60000);
}

/** "2026-10-01T18:00" wall-clock in `tz` -> ISO string in UTC. */
export function zonedLocalToIso(local: string, tz: string): string {
  const [datePart, timePart = "00:00"] = local.split("T");
  const [y, m, d] = datePart.split("-").map(Number);
  const [h, mi] = timePart.split(":").map(Number);
  const guess = Date.UTC(y, m - 1, d, h, mi);
  let off = offsetMinutes(new Date(guess), tz);
  let ts = guess - off * 60000;
  const off2 = offsetMinutes(new Date(ts), tz);
  if (off2 !== off) {
    off = off2;
    ts = guess - off * 60000;
  }
  return new Date(ts).toISOString();
}

/** ISO (UTC) -> "YYYY-MM-DDTHH:mm" wall-clock in `tz` for <input type="datetime-local">. */
export function isoToZonedLocal(iso: string | null | undefined, tz: string): string {
  if (!iso) return "";
  const x = parts(new Date(iso), tz);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${x.y}-${pad(x.m)}-${pad(x.d)}T${pad(x.h)}:${pad(x.mi)}`;
}

/** Calendar day key (YYYY-MM-DD) of an instant in `tz`. */
export function dayKey(iso: string, tz: string): string {
  return isoToZonedLocal(iso, tz).slice(0, 10);
}

export function relative(iso: string | null | undefined): string {
  if (!iso) return "";
  const diff = new Date(iso).getTime() - Date.now();
  const abs = Math.abs(diff);
  const mins = Math.round(abs / 60000);
  const text = mins < 60 ? `${mins} min` : mins < 60 * 48 ? `${Math.round(mins / 60)} h` : `${Math.round(mins / 1440)} days`;
  return diff >= 0 ? `in ${text}` : `${text} ago`;
}
