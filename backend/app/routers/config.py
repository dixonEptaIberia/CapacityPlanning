"""Configuration-over-code endpoints (R13, R15).

Authorized users manage configuration and add plants/lines through this layer
rather than editing the code base. Central-admin only.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_role
from app.core.errors import AppError, NotFoundError
from app.db.base import get_db
from app.domain import rules
from app.models import (
    Company,
    ConfigEntry,
    KpiDefinition,
    LineLink,
    Note,
    Plant,
    ProductLine,
    RoleName,
    RuleDefinition,
    User,
    WeekCell,
)
from app.schemas import (
    CompanyIn,
    CompanyOut,
    ConfigEntryIn,
    ConfigEntryOut,
    KpiDefinitionIn,
    KpiDefinitionOut,
    LineLinkIn,
    LineLinkOut,
    LineMoveIn,
    PlantOut,
    ProductLineOut,
    RuleDefinitionIn,
    RuleDefinitionOut,
    UserOut,
)
from app.services import serializers

router = APIRouter(tags=["config"])


@router.get("/me", response_model=UserOut)
def whoami(user: User = Depends(get_current_user)):
    """Return the current user's identity and role (drives UI permissions)."""
    return user


@router.get("/config", response_model=list[ConfigEntryOut])
def list_config(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    return db.scalars(select(ConfigEntry).order_by(ConfigEntry.key)).all()


@router.put("/config", response_model=ConfigEntryOut)
def upsert_config(
    payload: ConfigEntryIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """Add or update a configuration entry (R13)."""
    entry = db.scalar(select(ConfigEntry).where(ConfigEntry.key == payload.key))
    if entry:
        entry.value = payload.value
    else:
        entry = ConfigEntry(key=payload.key, value=payload.value)
        db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


@router.post("/config/plants", response_model=PlantOut, status_code=201)
def add_plant(
    payload: PlantOut,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """Add a plant through configuration, incl. hypothetical test plants (R15.1, R15.2)."""
    plant = Plant(
        name=payload.name,
        country=payload.country,
        region=payload.region,
        frozen_weeks=payload.frozen_weeks,
        standard_working_days=payload.standard_working_days,
        hypothetical=payload.hypothetical,
    )
    db.add(plant)
    db.commit()
    db.refresh(plant)
    return plant


@router.post("/config/lines", response_model=ProductLineOut, status_code=201)
def add_line(
    payload: ProductLineOut,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """Add a production line through configuration (R13.1, R15.1)."""
    line = ProductLine(
        plant_id=payload.plant_id,
        name=payload.name,
        product_family=payload.product_family,
        routing_info=payload.routing_info,
        sap_work_center=payload.sap_work_center,
        hypothetical=payload.hypothetical,
    )
    db.add(line)
    db.commit()
    db.refresh(line)
    return serializers.product_line_out(line)


@router.post("/config/companies", response_model=CompanyOut, status_code=201)
def add_company(
    payload: CompanyIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """Add a company through configuration (R15.1)."""
    company = Company(name=payload.name)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.put("/config/lines/{line_id}/plant", response_model=ProductLineOut)
def move_line(
    line_id: int,
    payload: LineMoveIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """Switch a production line to a different plant via configuration (R13.1)."""
    line = db.get(ProductLine, line_id)
    if line is None:
        raise NotFoundError(f"Line {line_id} not found.")
    if db.get(Plant, payload.plant_id) is None:
        raise NotFoundError(f"Plant {payload.plant_id} not found.")
    line.plant_id = payload.plant_id
    db.commit()
    db.refresh(line)
    return serializers.product_line_out(line)


@router.delete("/config/lines/{line_id}", status_code=204)
def remove_line(
    line_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """Remove a production line through configuration (R13.1).

    Deletes the line's week cells (and their notes) and any line links first so
    the single central dataset stays consistent.
    """
    line = db.get(ProductLine, line_id)
    if line is None:
        raise NotFoundError(f"Line {line_id} not found.")

    cell_ids = db.scalars(
        select(WeekCell.id).where(WeekCell.product_line_id == line_id)
    ).all()
    if cell_ids:
        db.query(Note).filter(Note.week_cell_id.in_(cell_ids)).delete(synchronize_session=False)
        db.query(WeekCell).filter(WeekCell.product_line_id == line_id).delete(
            synchronize_session=False
        )
    db.query(LineLink).filter(
        (LineLink.primary_line_id == line_id) | (LineLink.secondary_line_id == line_id)
    ).delete(synchronize_session=False)
    db.delete(line)
    db.commit()


@router.get("/config/rules", response_model=list[RuleDefinitionOut])
def list_rules(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """List configurable special rules (R4.2, R13.2)."""
    return db.scalars(select(RuleDefinition).order_by(RuleDefinition.id)).all()


@router.post("/config/rules", response_model=RuleDefinitionOut, status_code=201)
def add_rule(
    payload: RuleDefinitionIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """Define a special rule that the engine applies to output (R4.2, R13.2)."""
    rule = RuleDefinition(
        name=payload.name,
        rule_type=payload.rule_type,
        params_json=payload.params_json,
        active=payload.active,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.delete("/config/rules/{rule_id}", status_code=204)
def remove_rule(
    rule_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """Remove a special rule (R13.2)."""
    rule = db.get(RuleDefinition, rule_id)
    if rule is None:
        raise NotFoundError(f"Rule {rule_id} not found.")
    db.delete(rule)
    db.commit()


@router.get("/config/kpis", response_model=list[KpiDefinitionOut])
def list_kpis(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """List configurable dashboard KPIs (R13.3)."""
    return db.scalars(select(KpiDefinition).order_by(KpiDefinition.id)).all()


@router.post("/config/kpis", response_model=KpiDefinitionOut, status_code=201)
def add_kpi(
    payload: KpiDefinitionIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """Add a dashboard field / KPI through configuration (R13.3)."""
    if payload.source_field not in rules.KPI_SOURCE_FIELDS:
        raise AppError(
            f"Unknown KPI source field '{payload.source_field}'. "
            f"Allowed: {', '.join(rules.KPI_SOURCE_FIELDS)}.",
            code="invalid_kpi_field",
        )
    if payload.aggregation not in rules.KPI_AGGREGATIONS:
        raise AppError(
            f"Unknown KPI aggregation '{payload.aggregation}'. "
            f"Allowed: {', '.join(rules.KPI_AGGREGATIONS)}.",
            code="invalid_kpi_aggregation",
        )
    kpi = KpiDefinition(
        name=payload.name,
        source_field=payload.source_field,
        aggregation=payload.aggregation,
        unit=payload.unit,
        active=payload.active,
    )
    db.add(kpi)
    db.commit()
    db.refresh(kpi)
    return kpi


@router.delete("/config/kpis/{kpi_id}", status_code=204)
def remove_kpi(
    kpi_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """Remove a dashboard KPI (R13.3)."""
    kpi = db.get(KpiDefinition, kpi_id)
    if kpi is None:
        raise NotFoundError(f"KPI {kpi_id} not found.")
    db.delete(kpi)
    db.commit()


# --- Linked lines / Linee_Collegate (R4) ----------------------------------


def _line_link_out(db: Session, link: LineLink, plant_id: int) -> LineLinkOut:
    master = db.get(ProductLine, link.primary_line_id)
    slave = db.get(ProductLine, link.secondary_line_id)
    return LineLinkOut(
        id=link.id,
        plant_id=plant_id,
        master_line_id=link.primary_line_id,
        slave_line_id=link.secondary_line_id,
        master_line_name=master.name if master else None,
        slave_line_name=slave.name if slave else None,
        ratio=link.ratio,
    )


@router.get("/config/line-links", response_model=list[LineLinkOut])
def list_line_links(
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """List configured Master/Slave line links (R4, Linee_Collegate)."""
    links = db.scalars(select(LineLink).order_by(LineLink.id)).all()
    result: list[LineLinkOut] = []
    for link in links:
        master = db.get(ProductLine, link.primary_line_id)
        plant_id = master.plant_id if master else 0
        result.append(_line_link_out(db, link, plant_id))
    return result


@router.post("/config/line-links", response_model=LineLinkOut, status_code=201)
def add_line_link(
    payload: LineLinkIn,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """Link a Master line to a Slave line so they move as one process (R4.1).

    Requires the plant, master line, and slave line. Both lines must belong to
    the given plant and be distinct.
    """
    if payload.master_line_id == payload.slave_line_id:
        raise AppError(
            "Master and Slave lines must be different.", code="invalid_line_link"
        )
    if db.get(Plant, payload.plant_id) is None:
        raise NotFoundError(f"Plant {payload.plant_id} not found.")
    master = db.get(ProductLine, payload.master_line_id)
    if master is None:
        raise NotFoundError(f"Line {payload.master_line_id} not found.")
    slave = db.get(ProductLine, payload.slave_line_id)
    if slave is None:
        raise NotFoundError(f"Line {payload.slave_line_id} not found.")
    if master.plant_id != payload.plant_id or slave.plant_id != payload.plant_id:
        raise AppError(
            "Both Master and Slave lines must belong to the specified plant.",
            code="invalid_line_link",
        )

    link = LineLink(
        primary_line_id=payload.master_line_id,
        secondary_line_id=payload.slave_line_id,
        ratio=payload.ratio,
    )
    db.add(link)
    db.commit()
    db.refresh(link)
    return _line_link_out(db, link, payload.plant_id)


@router.delete("/config/line-links/{link_id}", status_code=204)
def remove_line_link(
    link_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """Remove a Master/Slave line link (R4)."""
    link = db.get(LineLink, link_id)
    if link is None:
        raise NotFoundError(f"Line link {link_id} not found.")
    db.delete(link)
    db.commit()
