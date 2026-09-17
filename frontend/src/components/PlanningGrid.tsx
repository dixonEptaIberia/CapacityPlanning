import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useCadenceOptions, useGrid, useUpdateCell } from "../api/queries";
import { api, errorMessage } from "../api/client";
import type { Cell, CurrentUser } from "../types";
import { CellEditor } from "./CellEditor";
import { NoteDialog } from "./NoteDialog";

interface Props {
  plantId: number;
  user: CurrentUser | undefined;
}

const canEdit = (role?: string) => role === "central-admin" || role === "planner";

/** Friday (MAD) date of an ISO year-week, formatted dd/mm/yyyy, matching the reference. */
function isoWeekFriday(year: number, week: number): string {
  const simple = new Date(Date.UTC(year, 0, 1 + (week - 1) * 7));
  const dow = simple.getUTCDay();
  const monday = new Date(simple);
  const diff = (dow <= 4 ? 1 : 8) - dow;
  monday.setUTCDate(simple.getUTCDate() + diff);
  const friday = new Date(monday);
  friday.setUTCDate(monday.getUTCDate() + 4);
  const dd = String(friday.getUTCDate()).padStart(2, "0");
  const mm = String(friday.getUTCMonth() + 1).padStart(2, "0");
  return `${dd}/${mm}/${friday.getUTCFullYear()}`;
}

/** Spreadsheet-like planning grid: lines as rows, weeks as columns (R1). */
export function PlanningGrid({ plantId, user }: Props) {
  const { t } = useTranslation();
  const grid = useGrid(plantId, 8);
  const cadence = useCadenceOptions();
  const updateCell = useUpdateCell(plantId);

  const [editing, setEditing] = useState<{ lineId: number; cell: Cell } | null>(null);
  const [noting, setNoting] = useState<{ lineId: number; week: string } | null>(null);
  const [banner, setBanner] = useState<string | null>(null);

  if (grid.isLoading || cadence.isLoading) return <p>{t("loading")}</p>;
  if (grid.isError) return <p className="error">{errorMessage(grid.error)}</p>;
  if (!grid.data) return null;

  const editable = canEdit(user?.role);
  const data = grid.data;
  const taktLabel = data.takt_label;
  const workforceByWeek = new Map(data.workforce.map((w) => [w.iso_year_week, w]));

  // CSV export of the current grid (R10), aligned with the reference layout.
  // The old Print function is replaced by this export.
  function exportCsv() {
    const header = [
      t("plant"),
      t("line"),
      t("year"),
      t("weekNo"),
      "MAD",
      t("workers"),
      t("workingDays"),
      t("adjQnty"),
      t("piecesWeek"),
      taktLabel,
    ];
    const rows: string[][] = [];
    for (const row of data.rows) {
      for (const cell of row.cells) {
        const [yearStr, weekStr] = cell.iso_year_week.split("-W");
        rows.push([
          data.plant.name,
          row.line.name,
          yearStr,
          weekStr,
          isoWeekFriday(Number(yearStr), Number(weekStr)),
          String(cell.workers_assigned),
          String(cell.working_days),
          String(cell.capacity_delta),
          String(cell.computed.actual_output),
          cell.cadence_label ?? "",
        ]);
      }
    }
    const escape = (v: string) => `"${v.replace(/"/g, '""')}"`;
    const csv = [header, ...rows].map((r) => r.map(escape).join(",")).join("\r\n");
    const blob = new Blob(["\ufeff" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `assembly_${data.plant.name}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function saveNote(text: string) {
    if (!noting) return;
    try {
      await api.post("/notes", {
        product_line_id: noting.lineId,
        iso_year_week: noting.week,
        text,
      });
      setBanner(t("savedNote"));
      await grid.refetch();
    } catch (err) {
      setBanner(errorMessage(err));
    } finally {
      setNoting(null);
    }
  }

  function saveCell(update: {
    cadence_option_id: number | null;
    workers_assigned: number;
    capacity_delta: number;
  }) {
    if (!editing) return;
    updateCell.mutate(
      { lineId: editing.lineId, week: editing.cell.iso_year_week, update },
      {
        onSuccess: () => setBanner(t("cellUpdated")),
        onError: (err) => setBanner(errorMessage(err)),
        onSettled: () => setEditing(null),
      },
    );
  }

  return (
    <div>
      {banner && <p className="error">{banner}</p>}
      <div className="toolbar" style={{ display: "flex", justifyContent: "flex-end", marginBottom: 8 }}>
        <button onClick={exportCsv}>{t("exportCsv")}</button>
      </div>
      <div className="grid-wrap">
        <table className="grid">
          <thead>
            <tr>
              <th className="line-col">{t("line")}</th>
              {grid.data.weeks.map((w) => (
                <th key={w}>{w}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {grid.data.rows.map((row) => (
              <tr key={row.line.id}>
                <td className="line-col">
                  <div className="metric">{row.line.name}</div>
                  <div className="sub">
                    {row.line.product_family ?? ""}
                    {row.line.platforms.length > 0 && ` · ${row.line.platforms.join(", ")}`}
                  </div>
                </td>
                {row.cells.map((cell) => {
                  const cls = [
                    "cell",
                    cell.computed.frozen ? "frozen" : "",
                    cell.computed.has_note ? "has-note" : "",
                  ]
                    .filter(Boolean)
                    .join(" ");
                  return (
                    <td
                      key={cell.iso_year_week}
                      className={cls}
                      title={cell.computed.frozen ? t("frozen") : undefined}
                    >
                      <div className="metric">{cell.computed.actual_output}</div>
                      <div className="sub">
                        {cell.cadence_label ?? t("none")} · {cell.workers_assigned}
                        {t("workers").charAt(0).toLowerCase()}
                      </div>
                      {cell.capacity_delta !== 0 && (
                        <div className="sub adj">
                          {t("adjQnty")}: {cell.capacity_delta > 0 ? "+" : ""}
                          {cell.capacity_delta}
                        </div>
                      )}
                      {cell.computed.has_note && <span className="note-dot">●</span>}
                      {editable && !cell.computed.frozen && (
                        <div style={{ marginTop: 4, display: "flex", gap: 4 }}>
                          <button onClick={() => setEditing({ lineId: row.line.id, cell })}>
                            ✎
                          </button>
                          <button
                            onClick={() =>
                              setNoting({ lineId: row.line.id, week: cell.iso_year_week })
                            }
                          >
                            {t("note").charAt(0)}
                          </button>
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr className="workforce-row">
              <td className="line-col">{t("workforce")}</td>
              {grid.data.weeks.map((w) => {
                const wf = workforceByWeek.get(w);
                if (!wf) return <td key={w}>—</td>;
                return (
                  <td key={w}>
                    <span className={`badge ${wf.status}`}>
                      {wf.assigned_workers}/{wf.target_workers} · {t(wf.status)}
                    </span>
                  </td>
                );
              })}
            </tr>
          </tbody>
        </table>
      </div>

      {editing && cadence.data && (
        <CellEditor
          cell={editing.cell}
          cadenceOptions={cadence.data}
          taktLabel={taktLabel}
          onSave={saveCell}
          onClose={() => setEditing(null)}
        />
      )}
      {noting && (
        <NoteDialog
          week={noting.week}
          onSave={saveNote}
          onClose={() => setNoting(null)}
        />
      )}
    </div>
  );
}
