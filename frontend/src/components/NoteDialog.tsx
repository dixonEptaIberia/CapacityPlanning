import { useState } from "react";
import { useTranslation } from "react-i18next";

interface Props {
  week: string;
  onSave: (text: string) => void;
  onClose: () => void;
}

/** Dialog to add a planning note to a cell (R9). */
export function NoteDialog({ week, onSave, onClose }: Props) {
  const { t } = useTranslation();
  const [text, setText] = useState("");

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <strong>
          {t("addNote")} — {week}
        </strong>
        <textarea
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("note")}
        />
        <div style={{ display: "flex", gap: "0.5rem", justifyContent: "flex-end" }}>
          <button onClick={onClose}>{t("cancel")}</button>
          <button className="primary" disabled={!text.trim()} onClick={() => onSave(text)}>
            {t("save")}
          </button>
        </div>
      </div>
    </div>
  );
}
