import { Alert, Loading, Spinner } from "../../components/ui";
import { useAction, useApi } from "../../hooks/useApi";
import { useAuth } from "../../hooks/useAuth";
import { api } from "../../services/api";
import type { InstagramStatus } from "../../types";
import { formatDateTime, relative } from "../../utils/time";

export default function InstagramTab({ connected, oauthError }: { connected: string | null; oauthError: string | null }) {
  const { tz, can } = useAuth();
  const { data: s, setData, loading, error: loadError } = useApi(() => api.get<InstagramStatus>("/instagram/status", { include_limit: true }));
  const { busy, error, run } = useAction();
  if (loading && !s) return <Loading />;
  if (!s) return <Alert kind="error">{loadError}</Alert>;
  const admin = can("admin");

  const connect = async () => {
    const r = await run("connect", () => api.get<{ authorize_url: string }>("/instagram/oauth/start"));
    if (r) window.location.href = r.authorize_url;
  };
  const act = async (name: string, path: string) => {
    const r = await run(name, () => api.post<InstagramStatus>(path));
    if (r) setData(r);
  };

  const statusText: Record<string, string> = {
    connected: "Connected",
    not_connected: "Not connected",
    token_expired: "Token expired — reconnect required",
    error: "Error",
  };

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-2">
        {connected && <Alert kind="success">Instagram account @{connected} connected successfully.</Alert>}
        {oauthError && <Alert kind="error" title="Instagram connection failed">{oauthError}</Alert>}
        {error && <Alert kind="error">{error.message}</Alert>}
        {s.is_mock && (
          <Alert kind="warning" title="Mock mode (MOCK_INSTAGRAM=true)">
            A simulated account is connected so you can test the whole workflow. Nothing is posted to Instagram. To publish for real, set MOCK_INSTAGRAM=false and configure your Meta app (README → “Connecting Instagram”).
          </Alert>
        )}
        <div className="card p-5">
          <h2 className="h2 mb-4">Account connection</h2>
          <dl className="grid gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
            <Item label="Instagram account">{s.username ? `@${s.username}` : "—"}</Item>
            <Item label="Connection status">
              <span className={`inline-flex items-center gap-1.5 font-medium ${s.connected ? "text-emerald-700" : "text-rose-700"}`}>
                <span className={`h-2 w-2 rounded-full ${s.connected ? "bg-emerald-500" : "bg-rose-500"}`} />
                {statusText[s.status] ?? s.status}
              </span>
            </Item>
            <Item label="Account type">{s.account_type || "—"}</Item>
            <Item label="Instagram user ID">{s.ig_user_id || "—"}</Item>
            <Item label="API">{s.login_type === "facebook" ? "Instagram API with Facebook Login" : "Instagram API with Instagram Login"}</Item>
            <Item label="Token source">{s.token_source || "—"}</Item>
            <Item label="Token status">
              {s.is_mock ? "Simulated" : s.token_expires_at ? `Expires ${formatDateTime(s.token_expires_at, tz)} (${relative(s.token_expires_at)})` : s.connected ? "Valid (no expiry recorded)" : "—"}
            </Item>
            <Item label="Last token refresh">{formatDateTime(s.token_last_refreshed_at, tz)}</Item>
            <Item label="Permissions">{s.scopes.length ? s.scopes.join(", ") : "—"}</Item>
            <Item label="Last successful API request">{formatDateTime(s.last_success_at, tz)}</Item>
            <Item label="Publishing quota (24h)">
              {s.publishing_limit && "quota_usage" in s.publishing_limit
                ? `${String(s.publishing_limit.quota_usage)} / ${String((s.publishing_limit.config as { quota_total?: number })?.quota_total ?? 100)} posts`
                : s.publishing_limit && "error" in s.publishing_limit
                  ? String(s.publishing_limit.error)
                  : "—"}
            </Item>
          </dl>
          {s.last_error && (
            <div className="mt-4">
              <Alert kind="error" title={`Last API error (${formatDateTime(s.last_error_at, tz)})`}>
                {s.last_error}
              </Alert>
            </div>
          )}
          {admin && (
            <div className="mt-5 flex flex-wrap gap-2">
              {s.oauth_available && (
                <button className="btn-primary" onClick={connect} disabled={!!busy}>
                  {busy === "connect" && <Spinner />} {s.connected ? "Reconnect" : "Connect"} Instagram account
                </button>
              )}
              {s.connected && (
                <button className="btn-secondary" onClick={() => act("test", "/instagram/test")} disabled={!!busy}>
                  {busy === "test" && <Spinner />} Test connection
                </button>
              )}
              {s.connected && s.token_source === "oauth" && (
                <button className="btn-secondary" onClick={() => act("refresh", "/instagram/refresh-token")} disabled={!!busy}>
                  Refresh token now
                </button>
              )}
              {s.connected && !s.is_mock && (
                <button className="btn-ghost text-rose-600" onClick={() => confirm("Disconnect Instagram? Scheduled posts will fail until you reconnect.") && act("disconnect", "/instagram/disconnect")} disabled={!!busy}>
                  Disconnect
                </button>
              )}
            </div>
          )}
          {!s.oauth_available && !s.is_mock && !s.connected && (
            <p className="mt-4 text-sm text-slate-600">
              The “Connect” button appears when META_APP_ID, META_APP_SECRET and META_REDIRECT_URI are set (Instagram Login). Alternatively set META_ACCESS_TOKEN and INSTAGRAM_ACCOUNT_ID.
            </p>
          )}
        </div>
      </div>
      <div className="card space-y-3 p-5 text-sm text-slate-700">
        <h2 className="h2">Requirements (Meta)</h2>
        <ul className="list-disc space-y-1 pl-5">
          <li>The Instagram account must be a <strong>Professional</strong> account (Business or Creator).</li>
          <li>
            Permissions: <code>instagram_business_basic</code> and <code>instagram_business_content_publish</code>.
          </li>
          <li>Images must be JPEG, ≤ 8 MB, aspect ratio 4:5 to 1.91:1 (this app produces 1080×1350 JPEGs).</li>
          <li>Instagram downloads the image from a public URL — the server's PUBLIC_BASE_URL (or S3) must be reachable from the internet.</li>
          <li>Limit: 100 API-published posts per 24 hours.</li>
          <li>Scheduling is done by this application; the API publishes at the moment we call it.</li>
          <li>Long-lived tokens last 60 days; this app refreshes them automatically.</li>
        </ul>
      </div>
    </div>
  );
}

function Item({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-xs text-slate-500">{label}</dt>
      <dd className="text-slate-900">{children}</dd>
    </div>
  );
}
