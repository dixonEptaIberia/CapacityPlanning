"""Shared ORM-to-schema serialization helpers.

Small, reusable converters used by multiple routers so response construction
stays consistent (and avoids the same boilerplate being copy-pasted around).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProductLine
from app.schemas import ProductLineOut


def product_line_out(line: ProductLine) -> ProductLineOut:
    """Serialize a ProductLine ORM object into its API representation."""
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


def line_name_map(db: Session) -> dict[int, str]:
    """Map every product line's id to its name (used to label snapshot rows)."""
    return {line.id: line.name for line in db.scalars(select(ProductLine)).all()}
