import { useSearchParams } from "react-router-dom";
import { PageHeader, Tabs } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import BrandTab from "./settings/Brand";
import CategoriesTab from "./settings/Categories";
import GeneralTab from "./settings/General";
import InstagramTab from "./settings/Instagram";
import LogsTab from "./settings/Logs";
import SheetsTab from "./settings/Sheets";
import TemplatesTab from "./settings/Templates";
import UsersTab from "./settings/Users";

type Tab = "general" | "instagram" | "brand" | "categories" | "templates" | "sheets" | "users" | "logs";

export default function SettingsPage() {
  const { can } = useAuth();
  const [params, setParams] = useSearchParams();
  // After the Instagram OAuth redirect the backend sends ?ig_connected / ?ig_error.
  const initial = (params.get("tab") as Tab) || (params.has("ig_connected") || params.has("ig_error") ? "instagram" : "general");
  const tab = initial;
  const tabs: { key: Tab; label: string }[] = [
    { key: "general", label: "General" },
    { key: "instagram", label: "Instagram" },
    { key: "brand", label: "Brand profile" },
    { key: "categories", label: "Categories" },
    { key: "templates", label: "Templates" },
    { key: "sheets", label: "Google Sheets" },
    ...(can("admin") ? [{ key: "users" as Tab, label: "Users" }] : []),
    { key: "logs", label: "Logs" },
  ];
  return (
    <div>
      <PageHeader title="Settings" />
      <Tabs tabs={tabs} value={tab} onChange={(t) => setParams({ tab: t })} />
      {tab === "general" && <GeneralTab />}
      {tab === "instagram" && <InstagramTab connected={params.get("ig_connected")} oauthError={params.get("ig_error")} />}
      {tab === "brand" && <BrandTab />}
      {tab === "categories" && <CategoriesTab />}
      {tab === "templates" && <TemplatesTab />}
      {tab === "sheets" && <SheetsTab />}
      {tab === "users" && <UsersTab />}
      {tab === "logs" && <LogsTab />}
    </div>
  );
}
