import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import { Loading } from "./components/ui";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import CalendarPage from "./pages/Calendar";
import CompetitorsPage from "./pages/Competitors";
import CreatePostPage from "./pages/CreatePost";
import DashboardPage from "./pages/Dashboard";
import IdeasPage from "./pages/Ideas";
import LoginPage from "./pages/Login";
import PostDetailPage from "./pages/PostDetail";
import PostsPage from "./pages/Posts";
import SchedulesPage from "./pages/Schedules";
import SettingsPage from "./pages/Settings";

function Protected() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  if (!user) return <Navigate to="/login" replace />;
  return <Layout />;
}

function LoginRoute() {
  const { user, loading } = useAuth();
  if (loading) return <Loading />;
  return user ? <Navigate to="/" replace /> : <LoginPage />;
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginRoute />} />
          <Route element={<Protected />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/create" element={<CreatePostPage />} />
            <Route path="/posts" element={<PostsPage />} />
            <Route path="/posts/:id" element={<PostDetailPage />} />
            <Route path="/calendar" element={<CalendarPage />} />
            <Route path="/ideas" element={<IdeasPage />} />
            <Route path="/schedules" element={<SchedulesPage />} />
            <Route path="/competitors" element={<CompetitorsPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
