import { NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";

const NAV = [
  { to: "/", label: "Dashboard", icon: "▦" },
  { to: "/create", label: "Create post", icon: "✚", role: "editor" as const },
  { to: "/posts", label: "Posts", icon: "☰" },
  { to: "/calendar", label: "Calendar", icon: "▤" },
  { to: "/ideas", label: "Content ideas", icon: "✦" },
  { to: "/schedules", label: "Recurring schedules", icon: "↻" },
  { to: "/competitors", label: "Competitor research", icon: "◎" },
  { to: "/settings", label: "Settings", icon: "⚙" },
];

export default function Layout() {
  const { user, logout, settings, can } = useAuth();
  const mocks = settings ? Object.entries(settings.mock).filter(([, v]) => v).map(([k]) => k.replace("_", " ")) : [];

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-slate-200 bg-white md:flex">
        <div className="flex items-center gap-2 px-5 py-5">
          <img src="/favicon.svg" className="h-8 w-8" alt="" />
          <div>
            <div className="text-sm font-semibold text-slate-900">Instagram Automation</div>
            <div className="text-xs text-slate-500">Phase 1</div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 px-3">
          {NAV.filter((n) => !n.role || can(n.role)).map((n) => (
            <NavLink
              key={n.to}
              to={n.to}
              end={n.to === "/"}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium ${isActive ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"}`
              }
            >
              <span className="w-4 text-center opacity-70">{n.icon}</span>
              {n.label}
            </NavLink>
          ))}
        </nav>
        <div className="border-t border-slate-200 px-5 py-4 text-sm">
          <div className="truncate font-medium text-slate-800">{user?.full_name || user?.email}</div>
          <div className="text-xs text-slate-500 capitalize">{user?.role}</div>
          <button className="mt-2 text-xs text-indigo-600 hover:underline" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center gap-2 overflow-x-auto border-b border-slate-200 bg-white px-4 py-2 md:hidden">
          {NAV.filter((n) => !n.role || can(n.role)).map((n) => (
            <NavLink key={n.to} to={n.to} end={n.to === "/"} className={({ isActive }) => `shrink-0 rounded px-2 py-1 text-xs ${isActive ? "bg-indigo-50 text-indigo-700" : "text-slate-600"}`}>
              {n.label}
            </NavLink>
          ))}
        </header>
        {mocks.length > 0 && (
          <div className="border-b border-amber-200 bg-amber-50 px-6 py-2 text-xs text-amber-900">
            <strong>Development mode:</strong> simulated services active ({mocks.join(", ")}).
            {settings?.mock.instagram && " Nothing is posted to Instagram — real publishing still requires Meta configuration and credentials."}
          </div>
        )}
        {settings && !settings.publishing_enabled && (
          <div className="border-b border-rose-200 bg-rose-50 px-6 py-2 text-xs text-rose-900">
            <strong>Publishing is paused.</strong> Scheduled posts will not be published until it is re-enabled in Settings.
          </div>
        )}
        <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
