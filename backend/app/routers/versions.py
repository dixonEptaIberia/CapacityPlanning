"""Version control, diffing, and history endpoints (R6, R7)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_edit, require_role
from app.core.errors import NotFoundError
from app.db.base import get_db
from app.models import (
    ChangeStatus,
    PlanVersion,
    RoleName,
    Scenario,
    User,
    VersionKind,
    WeekCell,
    WeekCellSnapshot,
)
from app.schemas import (
    DiffCell,
    DiffResponse,
    SnapshotRow,
    VersionCreate,
    VersionOut,
    VersionSnapshotResponse,
)
from app.services import planning, serializers

router = APIRouter(tags=["versions"])


@router.post("/versions", response_model=VersionOut, status_code=201)
def save_version(
    payload: VersionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_edit),
):
    """Save a named version with plant, time, and explanation (R7.1)."""
    version = PlanVersion(
        name=payload.name,
        plant_id=payload.plant_id,
        kind=VersionKind.named,
        explanation=payload.explanation,
        created_by=user.username,
    )
    db.add(version)
    db.flush()
    planning.snapshot_cells(db, version_id=version.id, plant_id=payload.plant_id)
    db.commit()
    db.refresh(version)
    return version


@router.post("/versions/{version_id}/release", response_model=VersionOut)
def release_official(
    version_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """Mark a version as the official released balance (R6.1). Central planning only."""
    version = db.get(PlanVersion, version_id)
    if version is None:
        raise NotFoundError(f"Version {version_id} not found.")
    version.kind = VersionKind.official
    db.commit()
    db.refresh(version)
    return version


@router.get("/versions", response_model=list[VersionOut])
def list_versions(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(PlanVersion).order_by(PlanVersion.created_at.desc())).all()


@router.get("/versions/official", response_model=list[VersionOut])
def official_summary(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Read-only summary of saved official versions (R7.5)."""
    return db.scalars(
        select(PlanVersion)
        .where(PlanVersion.kind == VersionKind.official)
        .order_by(PlanVersion.created_at.desc())
    ).all()


def _latest_official(db: Session) -> PlanVersion | None:
    # Tie-break on id so two officials saved in the same second order deterministically.
    return db.scalar(
        select(PlanVersion)
        .where(PlanVersion.kind == VersionKind.official)
        .order_by(PlanVersion.created_at.desc(), PlanVersion.id.desc())
    )


def _applied_keys(db: Session) -> set[tuple[int, str]]:
    """Cells that match a promoted scenario's snapshot are treated as applied (R7.3).

    Everything else that differs from the base is a proposal (a hypothesis).
    """
    promoted_ids = db.scalars(select(Scenario.id).where(Scenario.promoted.is_(True))).all()
    if not promoted_ids:
        return set()
    snaps = db.scalars(
        select(WeekCellSnapshot).where(WeekCellSnapshot.scenario_id.in_(promoted_ids))
    ).all()
    return {(s.product_line_id, s.iso_year_week) for s in snaps}


def _diff_against_version(db: Session, base_version: PlanVersion) -> list[DiffCell]:
    snapshots = db.scalars(
        select(WeekCellSnapshot).where(WeekCellSnapshot.version_id == base_version.id)
    ).all()
    snap_by_key = {(s.product_line_id, s.iso_year_week): s for s in snapshots}
    applied = _applied_keys(db)

    changes: list[DiffCell] = []
    for (line_id, week), snap in snap_by_key.items():
        cell = db.scalar(
            select(WeekCell).where(
                WeekCell.product_line_id == line_id, WeekCell.iso_year_week == week
            )
        )
        if cell is None:
            continue
        result = planning.compute_effective(
            cell=cell,
            db=db,
            special_rules=planning.active_special_rules(db),
            master_map=planning.linked_master_map(db),
        )
        comparisons = {
            "working_days": (snap.working_days, cell.working_days),
            "workers_assigned": (snap.workers_assigned, cell.workers_assigned),
            "capacity_delta": (snap.capacity_delta, cell.capacity_delta),
            "actual_output": (snap.actual_output, result.actual_output),
        }
        status = (
            ChangeStatus.applied_in_compass
            if (line_id, week) in applied
            else ChangeStatus.proposal
        )
        for field, (base_val, cur_val) in comparisons.items():
            if base_val != cur_val:
                changes.append(
                    DiffCell(
                        product_line_id=line_id,
                        iso_year_week=week,
                        field=field,
                        base_value=base_val,
                        current_value=cur_val,
                        status=status,
                    )
                )
    return changes


@router.get("/versions/diff", response_model=DiffResponse)
def diff_against_current(
    base: int = Query(..., description="Base version id to compare current data against"),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Diff current planning data against a base version, cell by cell (R7.2, R7.3)."""
    base_version = db.get(PlanVersion, base)
    if base_version is None:
        raise NotFoundError(f"Version {base} not found.")
    changes = _diff_against_version(db, base_version)
    return DiffResponse(base_version_id=base, changes=changes)


@router.get("/versions/diff/latest-official", response_model=DiffResponse)
def diff_against_latest_official(
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Diff current planning data against the most recent official version (R7.2)."""
    base_version = _latest_official(db)
    if base_version is None:
        raise NotFoundError("No official version has been released yet.")
    changes = _diff_against_version(db, base_version)
    return DiffResponse(base_version_id=base_version.id, changes=changes)


@router.get("/versions/{version_id}/snapshot", response_model=VersionSnapshotResponse)
def version_snapshot(
    version_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Read a saved version's stored cells back out for historical access (R7.4).

    Exposes previously closed or hidden weeks captured at save time without
    allowing edits to the live planning data (R7.5).
    """
    version = db.get(PlanVersion, version_id)
    if version is None:
        raise NotFoundError(f"Version {version_id} not found.")
    rows = db.scalars(
        select(WeekCellSnapshot)
        .where(WeekCellSnapshot.version_id == version_id)
        .order_by(WeekCellSnapshot.product_line_id, WeekCellSnapshot.iso_year_week)
    ).all()
    line_names = serializers.line_name_map(db)
    out_rows: list[SnapshotRow] = []
    for r in rows:
        row = SnapshotRow.model_validate(r)
        row.line_name = line_names.get(r.product_line_id)
        out_rows.append(row)
    return VersionSnapshotResponse(
        version_id=version_id, rows=out_rows, takt_label=planning.takt_label(db)
    )
