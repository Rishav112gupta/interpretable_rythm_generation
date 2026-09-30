import { useState, type FormEvent } from "react";
import { Alert, Spinner } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { ApiError } from "../services/api";

export default function LoginPage() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email, password);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Login failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-gradient-to-br from-indigo-50 via-white to-rose-50 p-4">
      <form onSubmit={submit} className="card w-full max-w-sm space-y-4 p-8">
        <div className="flex items-center gap-3">
          <img src="/favicon.svg" alt="" className="h-10 w-10" />
          <div>
            <h1 className="text-lg font-semibold">Instagram Automation</h1>
            <p className="muted">Sign in to the content dashboard</p>
          </div>
        </div>
        {error && <Alert kind="error">{error}</Alert>}
        <label className="block">
          <span className="label">Email</span>
          <input className="input" type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </label>
        <label className="block">
          <span className="label">Password</span>
          <input className="input" type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        </label>
        <button className="btn-primary w-full" disabled={busy}>
          {busy && <Spinner />} Sign in
        </button>
        <p className="text-xs text-slate-500">The first admin account is created from FIRST_ADMIN_EMAIL / FIRST_ADMIN_PASSWORD in your .env file.</p>
      </form>
    </div>
  );
}
