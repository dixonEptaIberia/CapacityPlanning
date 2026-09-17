"""Reporting and export endpoints (R10).

- Compass export: an .xlsx of approved cadence updates for import into Compass,
  replacing manual week-by-week copying (R10.2, R10.3).
- Click Sense (Qlik Sense) tables: flat, analysis-friendly rows (R10.1).
"""
from __future__ import annotations

import io

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from openpyxl import Workbook

from sqlalchemy import select

from app.core.auth import get_current_user, require_edit
from app.core.errors import NotFoundError
from app.db.base import get_db
from app.domain import weeks
from app.models import PlanVersion, ProductLine, User, WeekCellSnapshot
from app.services import planning

router = APIRouter(tags=["exports"])

_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _grid_rows_for_export(db, plant, week_labels):
    """Yield flat rows (plant, line, week, cadence, workers, expected, actual)."""
    special_rules = planning.active_special_rules(db)
    full_week_days = plant.standard_working_days
    master_map = planning.linked_master_map(db)
    # Exclude hypothetical/sandbox lines from Compass exports and reports (R15.2).
    official_lines = [line for line in plant.product_lines if not line.hypothetical]
    for line in sorted(official_lines, key=lambda x: x.name):
        for w in week_labels:
            cell = planning.get_or_create_cell(db, line.id, w)
            result = planning.compute_effective(db, cell, special_rules, full_week_days, master_map)
            yield {
                "plant": plant.name,
                "line": line.name,
                "sap_work_center": line.sap_work_center or "",
                "week": w,
                "cadence": cell.cadence_option.label if cell.cadence_option else "",
                "workers": cell.workers_assigned,
                "expected_pieces": result.expected_pieces,
                "adj_qnty": cell.capacity_delta,
                "actual_output": result.actual_output,
            }


@router.get("/exports/compass")
def export_compass(
    plant_id: int,
    start_week: str | None = Query(default=None),
    weeks_count: int = Query(default=8, ge=1, le=52),
    db=Depends(get_db),
    _: User = Depends(require_edit),
):
    """Generate a Compass-import spreadsheet of approved cadence updates (R10.2)."""
    plant = planning.get_plant_or_404(db, plant_id)
    start = start_week or planning.current_week_label()
    week_labels = weeks.week_range(start, weeks_count)

    wb = Workbook()
    ws = wb.active
    ws.title = "Compass Cadence"
    headers = [
        "Plant",
        "Line",
        "SAP Work Center",
        "Week",
        "Cadence",
        "Workers",
        "Adj. Qnty",
        "Pieces",
    ]
    ws.append(headers)
    for row in _grid_rows_for_export(db, plant, week_labels):
        ws.append(
            [
                row["plant"],
                row["line"],
                row["sap_work_center"],
                row["week"],
                row["cadence"],
                row["workers"],
                row["adj_qnty"],
                row["actual_output"],
            ]
        )
    db.commit()

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    filename = f"compass_{plant.name}_{start}.xlsx"
    return StreamingResponse(
        buf,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/versions/{version_id}/export.xlsx")
def export_official_version(
    version_id: int,
    db=Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Export a saved (official) version as a tabular .xlsx (R7.5, R10).

    Replaces the previous print-oriented layout with a readable table that
    includes the customizable takt label and the Adj. Qnty (capacity adjustment)
    captured in each snapshot.
    """
    version = db.get(PlanVersion, version_id)
    if version is None:
        raise NotFoundError(f"Version {version_id} not found.")

    label = planning.takt_label(db)
    snapshots = db.scalars(
        select(WeekCellSnapshot)
        .where(WeekCellSnapshot.version_id == version_id)
        .order_by(WeekCellSnapshot.product_line_id, WeekCellSnapshot.iso_year_week)
    ).all()

    line_names = {
        line.id: line.name
        for line in db.scalars(select(ProductLine)).all()
    }

    wb = Workbook()
    ws = wb.active
    ws.title = "Official Version"
    headers = [
        "Line",
        "Week",
        label,
        "Working Days",
        "Workers",
        "Expected",
        "Adj. Qnty",
        "Actual",
    ]
    ws.append(headers)
    for s in snapshots:
        ws.append(
            [
                line_names.get(s.product_line_id, str(s.product_line_id)),
                s.iso_year_week,
                s.cadence_label or "",
                s.working_days,
                s.workers_assigned,
                s.expected_pieces,
                s.capacity_delta,
                s.actual_output,
            ]
        )

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    safe_name = version.name.replace(" ", "_")
    filename = f"official_{safe_name}_{version_id}.xlsx"
    return StreamingResponse(
        buf,
        media_type=_XLSX_MEDIA,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/clicksense")
def report_clicksense(
    plant_id: int,
    start_week: str | None = Query(default=None),
    weeks_count: int = Query(default=8, ge=1, le=52),
    db=Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return flat, structured rows for Click Sense / Qlik Sense analysis (R10.1)."""
    plant = planning.get_plant_or_404(db, plant_id)
    start = start_week or planning.current_week_label()
    week_labels = weeks.week_range(start, weeks_count)
    rows = list(_grid_rows_for_export(db, plant, week_labels))
    db.commit()
    return {"rows": rows}
