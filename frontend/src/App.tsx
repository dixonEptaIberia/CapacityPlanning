import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useQueryClient } from "@tanstack/react-query";
import { usePlants, useCurrentUser } from "./api/queries";
import { getDevUser, setDevUser } from "./api/client";
import { SUPPORTED_LANGUAGES, setLanguage, type SupportedLanguage } from "./i18n";
import { PlanningGrid } from "./components/PlanningGrid";
import { OfficialVersions } from "./components/OfficialVersions";

// Dev users seeded on the backend, for switching roles locally.
const DEV_USERS = ["admin", "planner", "viewer", "limana_viewer"];

type Page = "assembly" | "official";

export default function App() {
  const { t, i18n } = useTranslation();
  const qc = useQueryClient();
  const plants = usePlants();
  const me = useCurrentUser();

  const [plantId, setPlantId] = useState<number | null>(null);
  const [devUser, setDevUserState] = useState<string>(getDevUser());
  const [page, setPage] = useState<Page>("assembly");

  // Default to the first plant once loaded.
  useEffect(() => {
    if (plantId == null && plants.data && plants.data.length > 0) {
      setPlantId(plants.data[0].id);
    }
  }, [plants.data, plantId]);

  function switchUser(username: string) {
    setDevUser(username);
    setDevUserState(username);
    qc.invalidateQueries(); // refetch under the new identity
  }

  return (
    <>
      <header className="app-header">
        <h1>{t("appTitle")}</h1>
        <div className="controls">
          <label>
            {t("plant")}{" "}
            <select
              value={plantId ?? ""}
              onChange={(e) => setPlantId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">{t("selectPlant")}</option>
              {plants.data?.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>

          <label>
            {t("language")}{" "}
            <select
              value={i18n.language}
              onChange={(e) => setLanguage(e.target.value as SupportedLanguage)}
            >
              {SUPPORTED_LANGUAGES.map((l) => (
                <option key={l} value={l}>
                  {l.toUpperCase()}
                </option>
              ))}
            </select>
          </label>

          <label>
            {t("user")}{" "}
            <select value={devUser} onChange={(e) => switchUser(e.target.value)}>
              {DEV_USERS.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
          </label>

          {me.data && (
            <span className="badge at">
              {t("role")}: {me.data.role}
            </span>
          )}
        </div>
      </header>

      <nav className="app-nav" style={{ display: "flex", gap: 8, padding: "0.5rem 1rem" }}>
        <button
          className={page === "assembly" ? "primary" : ""}
          onClick={() => setPage("assembly")}
        >
          {t("assemblyLine")}
        </button>
        <button
          className={page === "official" ? "primary" : ""}
          onClick={() => setPage("official")}
        >
          {t("officialVersion")}
        </button>
      </nav>

      <main className="app-main">
        {page === "official" ? (
          <OfficialVersions />
        ) : plantId != null ? (
          <PlanningGrid plantId={plantId} user={me.data} />
        ) : (
          <p>{t("selectPlant")}</p>
        )}
      </main>
    </>
  );
}
