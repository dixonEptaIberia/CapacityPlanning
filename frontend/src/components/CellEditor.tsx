import { useState } from "react";
import { useTranslation } from "react-i18next";
import type { Cell, CadenceOption } from "../types";

interface Props {
  cell: Cell;
  cadenceOptions: CadenceOption[];
  taktLabel: string;
  onSave: (update: {
    cadence_option_id: number | null;
    workers_assigned: number;
    capacity_delta: number;
  }) => void;
  onClose: () => void;
}

/** Modal editor for a single planning cell (takt, workers, Adj. Qnty). */
export function CellEditor({ cell, cadenceOptions, taktLabel, onSave, onClose }: Props) {
  const { t } = useTranslation();
  const [cadenceId, setCadenceId] = useState<number | null>(cell.cadence_option_id);
  const [workers, setWorkers] = useState<number>(cell.workers_assigned);
  const [delta, setDelta] = useState<number>(cell.capacity_delta);

  // Keep the worker field aligned with the approved combination when cadence changes.
  function pickCadence(value: string) {
    if (value === "") {
      setCadenceId(null);
      return;
    }
    const id = Number(value);
    setCadenceId(id);
    const opt = cadenceOptions.find((o) => o.id === id);
    if (opt) setWorkers(opt.workers);
  }

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <strong>
          {t("week")} {cell.iso_year_week}
        </strong>

        <label>
          {taktLabel}
          <select value={cadenceId ?? ""} onChange={(e) => pickCadence(e.target.value)}>
            <option value="">{t("none")}</option>
            {cadenceOptions.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label} ({o.pieces_per_week})
              </option>
            ))}
          </select>
        </label>

        <label>
          {t("workers")}
          <input
            type="number"
            min={0}
            value={workers}
            onChange={(e) => setWorkers(Number(e.target.value))}
          />
        </label>

        <label>
          {t("adjQnty")}
          <input
            type="number"
            value={delta}
            onChange={(e) => setDelta(Number(e.target.value))}
          />
        </label>

        <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
          <button onClick={onClose}>{t("cancel")}</button>
          <button
            className="primary"
            onClick={() =>
              onSave({
                cadence_option_id: cadenceId,
                workers_assigned: workers,
                capacity_delta: delta,
              })
            }
          >
            {t("save")}
          </button>
        </div>
      </div>
    </div>
  );
}
