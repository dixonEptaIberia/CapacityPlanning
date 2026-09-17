import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  downloadVersionExcel,
  useOfficialVersions,
  useVersionSnapshot,
} from "../api/queries";
import { errorMessage } from "../api/client";

/**
 * Official Version page (R7.5): a read-only, compact view of released official
 * versions. Selecting a version shows its captured cells in a tabular layout
 * (with the takt label and Adj. Qnty) and offers an Excel export.
 */
export function OfficialVersions() {
  const { t } = useTranslation();
  const versions = useOfficialVersions();
  const [selected, setSelected] = useState<{ id: number; name: string } | null>(null);
  const snapshot = useVersionSnapshot(selected?.id ?? null);
  const [banner, setBanner] = useState<string | null>(null);

  if (versions.isLoading) return <p>{t("loading")}</p>;
  if (versions.isError) return <p className="error">{errorMessage(versions.error)}</p>;

  const list = versions.data ?? [];

  async function exportExcel() {
    if (!selected) return;
    try {
      await downloadVersionExcel(selected.id, selected.name);
    } catch (err) {
      setBanner(errorMessage(err));
    }
  }

  return (
    <div className="official">
      {banner && <p className="error">{banner}</p>}
      {list.length === 0 ? (
        <p>{t("noOfficialVersions")}</p>
      ) : (
        <div style={{ display: "flex", gap: "1.5rem", alignItems: "flex-start" }}>
          <div className="version-list">
            <h3>{t("officialVersion")}</h3>
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {list.map((v) => (
                <li key={v.id} style={{ marginBottom: 6 }}>
                  <button
                    className={selected?.id === v.id ? "primary" : ""}
                    onClick={() => setSelected({ id: v.id, name: v.name })}
                  >
                    {v.name}
                  </button>
                  <div className="sub">
                    {t("createdBy")}: {v.created_by}
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <div style={{ flex: 1 }}>
            {selected && (
              <>
                <div
                  className="toolbar"
                  style={{
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    marginBottom: 8,
                  }}
                >
                  <strong>
                    {t("version")}: {selected.name}
                  </strong>
                  <button onClick={exportExcel}>{t("exportExcel")}</button>
                </div>

                {snapshot.isLoading && <p>{t("loading")}</p>}
                {snapshot.isError && (
                  <p className="error">{errorMessage(snapshot.error)}</p>
                )}
                {snapshot.data && (
                  <div className="grid-wrap">
                    <table className="grid compact">
                      <thead>
                        <tr>
                          <th>{t("line")}</th>
                          <th>{t("week")}</th>
                          <th>{snapshot.data.takt_label}</th>
                          <th>{t("workingDays")}</th>
                          <th>{t("workers")}</th>
                          <th>{t("expected")}</th>
                          <th>{t("adjQnty")}</th>
                          <th>{t("actual")}</th>
                        </tr>
                      </thead>
                      <tbody>
                        {snapshot.data.rows.map((r, i) => (
                          <tr key={`${r.product_line_id}-${r.iso_year_week}-${i}`}>
                            <td>{r.line_name ?? `#${r.product_line_id}`}</td>
                            <td>{r.iso_year_week}</td>
                            <td>{r.cadence_label ?? t("none")}</td>
                            <td>{r.working_days}</td>
                            <td>{r.workers_assigned}</td>
                            <td>{r.expected_pieces}</td>
                            <td>
                              {r.capacity_delta > 0 ? "+" : ""}
                              {r.capacity_delta}
                            </td>
                            <td>{r.actual_output}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
