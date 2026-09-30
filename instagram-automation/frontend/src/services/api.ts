/**
 * Thin API client. Only the dashboard session token (JWT) lives in the browser;
 * Instagram / LLM / Google credentials never leave the backend.
 */

const TOKEN_KEY = "ia_token";
const BASE = import.meta.env.VITE_API_BASE_URL || "";

export class ApiError extends Error {
  status: number;
  code: string;
  details: Record<string, unknown>;
  constructor(status: number, message: string, code = "error", details: Record<string, unknown> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
};

let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(fn: () => void) {
  onUnauthorized = fn;
}

type Body = Record<string, unknown> | unknown[] | FormData | undefined;

async function request<T>(method: string, path: string, body?: Body, query?: Record<string, unknown>): Promise<T> {
  const url = new URL(BASE + "/api" + path, window.location.origin);
  if (query) {
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === "") continue;
      if (Array.isArray(v)) v.forEach((x) => url.searchParams.append(k, String(x)));
      else url.searchParams.set(k, String(v));
    }
  }
  const headers: Record<string, string> = {};
  const token = tokenStore.get();
  if (token) headers["Authorization"] = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  let res: Response;
  try {
    res = await fetch(url.toString(), { method, headers, body: payload });
  } catch {
    throw new ApiError(0, "Cannot reach the server. Is the backend running?");
  }
  if (res.status === 401 && token) {
    tokenStore.clear();
    onUnauthorized?.();
  }
  if (res.status === 204) return undefined as T;
  const ct = res.headers.get("content-type") || "";
  const data = ct.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    const message =
      typeof data === "object" && data
        ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail ?? data))
        : String(data || res.statusText);
    throw new ApiError(res.status, message, (data as { error?: string })?.error, (data as { details?: Record<string, unknown> })?.details ?? {});
  }
  return data as T;
}

export const api = {
  get: <T>(p: string, q?: Record<string, unknown>) => request<T>("GET", p, undefined, q),
  post: <T>(p: string, b?: Body, q?: Record<string, unknown>) => request<T>("POST", p, b ?? {}, q),
  put: <T>(p: string, b?: Body) => request<T>("PUT", p, b),
  patch: <T>(p: string, b?: Body) => request<T>("PATCH", p, b),
  del: <T>(p: string) => request<T>("DELETE", p),
  /** Authenticated binary GET returned as an object URL (for template previews). */
  blobUrl: async (p: string): Promise<string> => {
    const token = tokenStore.get();
    const res = await fetch(BASE + "/api" + p, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!res.ok) throw new ApiError(res.status, "Preview failed");
    return URL.createObjectURL(await res.blob());
  },
};
