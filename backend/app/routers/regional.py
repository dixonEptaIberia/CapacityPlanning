"""Regional / cross-plant aggregation endpoints (R8)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.errors import NotFoundError
from app.db.base import get_db
from app.models import Platform, User
from app.schemas import PlatformAggregateRow, RegionalResponse
from app.services import planning

router = APIRouter(tags=["regional"])


@router.get("/regional/grid", response_model=RegionalResponse)
def regional_grid(
    platform: str = Query(..., description="Platform name, e.g. A1"),
    start_week: str | None = Query(default=None),
    weeks_count: int = Query(default=8, ge=1, le=52),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Aggregate total potential output across plants sharing a platform (R8.2)."""
    plat = db.scalar(select(Platform).where(Platform.name == platform))
    if plat is None:
        raise NotFoundError(f"Platform '{platform}' not found.")

    week_labels = planning.resolve_week_labels(start_week, weeks_count)

    special_rules = planning.active_special_rules(db)
    rows: list[PlatformAggregateRow] = []
    for w in week_labels:
        per_plant: dict[str, int] = {}
        total_expected = 0
        total_actual = 0
        for line in plat.product_lines:
            # Exclude hypothetical/sandbox lines and plants from regional totals (R15.2).
            if line.hypothetical or line.plant.hypothetical:
                continue
            cell = planning.get_or_create_cell(db, line.id, w)
            result = planning.compute_for_cell(cell, special_rules)
            plant_name = line.plant.name
            per_plant[plant_name] = per_plant.get(plant_name, 0) + result.actual_output
            total_expected += result.expected_pieces
            total_actual += result.actual_output
        rows.append(
            PlatformAggregateRow(
                iso_year_week=w,
                total_expected_pieces=total_expected,
                total_actual_output=total_actual,
                per_plant=per_plant,
            )
        )
    db.commit()
    return RegionalResponse(platform=platform, weeks=week_labels, rows=rows)
