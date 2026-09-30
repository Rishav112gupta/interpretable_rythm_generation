import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api, setUnauthorizedHandler, tokenStore } from "../services/api";
import type { AppSettings, Role, User } from "../types";

interface AuthState {
  user: User | null;
  settings: AppSettings | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  refreshSettings: () => Promise<void>;
  can: (role: Role) => boolean;
  tz: string;
}

const RANK: Record<Role, number> = { viewer: 0, editor: 1, approver: 2, admin: 3 };
const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshSettings = useCallback(async () => {
    setSettings(await api.get<AppSettings>("/settings"));
  }, []);

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    setSettings(null);
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
    if (!tokenStore.get()) {
      setLoading(false);
      return;
    }
    Promise.all([api.get<User>("/auth/me"), api.get<AppSettings>("/settings")])
      .then(([u, s]) => {
        setUser(u);
        setSettings(s);
      })
      .catch(() => tokenStore.clear())
      .finally(() => setLoading(false));
  }, [logout]);

  const login = async (email: string, password: string) => {
    const res = await api.post<{ access_token: string; user: User }>("/auth/login", { email, password });
    tokenStore.set(res.access_token);
    setUser(res.user);
    await refreshSettings();
  };

  const can = (role: Role) => !!user && RANK[user.role] >= RANK[role];

  return (
    <AuthContext.Provider value={{ user, settings, loading, login, logout, refreshSettings, can, tz: settings?.timezone || "Asia/Kolkata" }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth outside AuthProvider");
  return ctx;
}
