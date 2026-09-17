"""Planning grid and cell-editing endpoints (R1, R2, R3, R9)."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import check_plant_scope, get_current_user, require_edit
from app.db.base import get_db
from app.domain import weeks
from app.models import User
from app.schemas import (
    CellComputed,
    CellOut,
    CellUpdate,
    GridResponse,
    GridRow,
    KpiDashboardResponse,
    KpiValue,
    PlantOut,
    ProductLineOut,
    WeekTotals,
    WorkforceStatus,
)
from app.services import planning

router = APIRouter(tags=["grid"])


def _line_out(line) -> ProductLineOut:
    return ProductLineOut(
        id=line.id,
        plant_id=line.plant_id,
        name=line.name,
        product_family=line.product_family,
        routing_info=line.routing_info,
        sap_work_center=line.sap_work_center,
        platforms=[p.name for p in line.platforms],
        hypothetical=line.hypothetical,
    )


def _cell_out(
    db: Session,
    line_id: int,
    week: str,
    plant_frozen_weeks: int,
    special_rules=None,
    full_week_days: int | None = None,
    master_map: dict[int, int] | None = None,
) -> CellOut:
    cell = planning.get_or_create_cell(db, line_id, week)
    result = planning.compute_effective(db, cell, special_rules, full_week_days, master_map)
    current = planning.current_week_label()
    frozen = weeks.is_frozen(current, week, plant_frozen_weeks)
    finalization_due = weeks.is_finalization_week(current, week, plant_frozen_weeks)
    overdue = finalization_due and weeks.finalization_overdue(date.today(), current)
    return CellOut(
        product_line_id=line_id,
        iso_year_week=week,
        working_days=cell.working_days,
        cadence_option_id=cell.cadence_option_id,
        cadence_label=cell.cadence_option.label if cell.cadence_option else None,
        workers_assigned=cell.workers_assigned,
        capacity_delta=cell.capacity_delta,
        computed=CellComputed(
            expected_pieces=result.expected_pieces,
            actual_output=result.actual_output,
            frozen=frozen,
            has_note=planning.cell_has_note(db, cell.id),
            finalization_due=finalization_due,
            finalization_overdue=overdue,
        ),
    )


@router.get("/plants/{plant_id}/grid", response_model=GridResponse)
def get_grid(
    plant_id: int,
    start_week: str | None = Query(default=None, description="ISO week, e.g. 2026-W34"),
    weeks_count: int = Query(default=8, ge=1, le=52),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return the spreadsheet-like grid: lines as rows, weeks as columns (R1.1)."""
    plant = planning.get_plant_or_404(db, plant_id)
    start = start_week or planning.current_week_label()
    week_labels = weeks.week_range(start, weeks_count)

    special_rules = planning.active_special_rules(db)
    full_week_days = plant.standard_working_days
    master_map = planning.linked_master_map(db)
    rows: list[GridRow] = []
    # Hypothetical/sandbox lines are excluded from the official grid (R15.2).
    official_lines = [line for line in plant.product_lines if not line.hypothetical]
    for line in sorted(official_lines, key=lambda x: x.name):
        cells = [
            _cell_out(db, line.id, w, plant.frozen_weeks, special_rules, full_week_days, master_map)
            for w in week_labels
        ]
        rows.append(GridRow(line=_line_out(line), cells=cells))

    # Per-week totals across the plant's official lines (the sheet's bottom row).
    totals: list[WeekTotals] = []
    for i, w in enumerate(week_labels):
        expected = sum(row.cells[i].computed.expected_pieces for row in rows)
        actual = sum(row.cells[i].computed.actual_output for row in rows)
        workers = sum(row.cells[i].workers_assigned for row in rows)
        totals.append(
            WeekTotals(
                iso_year_week=w,
                total_expected_pieces=expected,
                total_actual_output=actual,
                total_workers=workers,
            )
        )

    workforce: list[WorkforceStatus] = []
    for w in week_labels:
        ev = planning.workforce_for_week(db, plant, w)
        if ev is not None:
            workforce.append(
                WorkforceStatus(
                    iso_year_week=w,
                    target_workers=ev.target_workers,
                    assigned_workers=ev.assigned_workers,
                    status=ev.status,
                    delta=ev.delta,
                )
            )
    takt_label = planning.takt_label(db)
    db.commit()
    return GridResponse(
        plant=PlantOut.model_validate(plant),
        weeks=week_labels,
        rows=rows,
        workforce=workforce,
        totals=totals,
        takt_label=takt_label,
    )


@router.put("/plants/{plant_id}/cells/{line_id}/{week}", response_model=CellOut)
def update_cell(
    plant_id: int,
    line_id: int,
    week: str,
    payload: CellUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_edit),
):
    """Edit a planning cell; runs the rules engine (R2, R3, R4) and scope check (R12)."""
    plant = planning.get_plant_or_404(db, plant_id)
    check_plant_scope(user, plant)
    line = next((line for line in plant.product_lines if line.id == line_id), None)
    if line is None:
        from app.core.errors import NotFoundError

        raise NotFoundError(f"Line {line_id} not found in plant {plant_id}.")

    # Distinguish "clear cadence" (explicit null) from "not provided".
    fields_set = payload.model_fields_set
    unset_cadence = "cadence_option_id" in fields_set and payload.cadence_option_id is None

    planning.edit_cell(
        db,
        line,
        week,
        working_days=payload.working_days,
        cadence_option_id=payload.cadence_option_id,
        workers_assigned=payload.workers_assigned,
        capacity_delta=payload.capacity_delta,
        unset_cadence=unset_cadence,
    )
    out = _cell_out(
        db,
        line_id,
        week,
        plant.frozen_weeks,
        planning.active_special_rules(db),
        master_map=planning.linked_master_map(db),
    )
    db.commit()
    return out


@router.get("/plants/{plant_id}/kpis", response_model=KpiDashboardResponse)
def get_kpis(
    plant_id: int,
    start_week: str | None = Query(default=None, description="ISO week, e.g. 2026-W34"),
    weeks_count: int = Query(default=8, ge=1, le=52),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Compute the configured dashboard KPIs for a plant's grid (R13.3).

    KPIs are defined through configuration (`/config/kpis`), so new dashboard
    fields can be added without code changes.
    """
    plant = planning.get_plant_or_404(db, plant_id)
    start = start_week or planning.current_week_label()
    week_labels = weeks.week_range(start, weeks_count)
    values = planning.evaluate_kpis(db, plant, week_labels)
    db.commit()
    return KpiDashboardResponse(
        plant_id=plant_id,
        weeks=week_labels,
        kpis=[KpiValue(**v) for v in values],
    )
