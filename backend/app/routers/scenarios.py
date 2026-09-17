"""Scenario management endpoints (R5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_edit, require_role
from app.core.errors import NotFoundError
from app.db.base import get_db
from app.models import ChangeStatus, PlanVersion, RoleName, Scenario, User, VersionKind
from app.schemas import ScenarioCreate, ScenarioOut
from app.services import planning

router = APIRouter(tags=["scenarios"])


@router.post("/scenarios", response_model=ScenarioOut, status_code=201)
def create_scenario(
    payload: ScenarioCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_edit),
):
    """Create a scenario (hypothesis) without copying the official dataset (R5.1)."""
    scenario = Scenario(
        name=payload.name,
        plant_id=payload.plant_id,
        description=payload.description,
        status=ChangeStatus.proposal,
        created_by=user.username,
    )
    db.add(scenario)
    db.flush()
    planning.snapshot_cells(db, scenario_id=scenario.id, plant_id=payload.plant_id)
    db.commit()
    db.refresh(scenario)
    return scenario


@router.get("/scenarios", response_model=list[ScenarioOut])
def list_scenarios(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return db.scalars(select(Scenario).order_by(Scenario.created_at.desc())).all()


@router.post("/scenarios/{scenario_id}/promote", response_model=ScenarioOut)
def promote_scenario(
    scenario_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(RoleName.central_admin)),
):
    """Promote a scenario toward an official version (R5.3).

    Only central planning may promote. Captures a new official version from the
    scenario's snapshot rather than requiring manual re-entry.
    """
    scenario = db.get(Scenario, scenario_id)
    if scenario is None:
        raise NotFoundError(f"Scenario {scenario_id} not found.")

    version = PlanVersion(
        name=f"Official from scenario: {scenario.name}",
        plant_id=scenario.plant_id,
        kind=VersionKind.official,
        explanation=f"Promoted from scenario {scenario.id}",
        created_by=user.username,
    )
    db.add(version)
    db.flush()
    planning.snapshot_cells(db, version_id=version.id, plant_id=scenario.plant_id)

    scenario.promoted = True
    scenario.status = ChangeStatus.applied_in_compass
    db.commit()
    db.refresh(scenario)
    return scenario
