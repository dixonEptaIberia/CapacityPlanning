"""Plants, product lines, and cadence master-data endpoints (R1, R2)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.base import get_db
from app.models import CadenceOption, Plant, ProductLine, User
from app.schemas import CadenceOptionOut, PlantOut, ProductLineOut

router = APIRouter(tags=["plants"])


@router.get("/plants", response_model=list[PlantOut])
def list_plants(
    include_hypothetical: bool = Query(
        default=False, description="Include hypothetical/sandbox plants (R15.2)"
    ),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """List plants. Hypothetical/sandbox plants are excluded from official data by default (R15.2)."""
    stmt = select(Plant).order_by(Plant.name)
    if not include_hypothetical:
        stmt = stmt.where(Plant.hypothetical.is_(False))
    return db.scalars(stmt).all()


@router.get("/plants/{plant_id}/lines", response_model=list[ProductLineOut])
def list_lines(
    plant_id: int,
    include_hypothetical: bool = Query(
        default=False, description="Include hypothetical/sandbox lines (R15.2)"
    ),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    stmt = select(ProductLine).where(ProductLine.plant_id == plant_id)
    if not include_hypothetical:
        stmt = stmt.where(ProductLine.hypothetical.is_(False))
    lines = db.scalars(stmt.order_by(ProductLine.name)).all()
    return [
        ProductLineOut(
            id=line.id,
            plant_id=line.plant_id,
            name=line.name,
            product_family=line.product_family,
            routing_info=line.routing_info,
            sap_work_center=line.sap_work_center,
            platforms=[p.name for p in line.platforms],
            hypothetical=line.hypothetical,
        )
        for line in lines
    ]


@router.get("/cadence-options", response_model=list[CadenceOptionOut])
def list_cadence_options(
    db: Session = Depends(get_db), _: User = Depends(get_current_user)
):
    return db.scalars(select(CadenceOption).order_by(CadenceOption.workers)).all()
