"""Production-transfer-between-plants endpoints (R8.3).

Recording an intended transfer is a proposal only. The platform makes the
"sales must be consulted and the change agreed" requirement explicit: a transfer
cannot be applied until ``sales_agreed`` is set.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_edit, require_role
from app.core.errors import AppError, NotFoundError
from app.db.base import get_db
from app.models import Plant, ProductionTransfer, ProductLine, RoleName, User
from app.schemas import TransferCreate, TransferOut

router = APIRouter(tags=["transfers"])


def _to_out(t: ProductionTransfer) -> TransferOut:
    return TransferOut(
        id=t.id,
        product_line_id=t.product_line_id,
        from_plant_id=t.from_plant_id,
        to_plant_id=t.to_plant_id,
        market=t.market,
        note=t.note,
        sales_agreed=t.sales_agreed,
        applied=t.applied,
        created_by=t.created_by,
        created_at=t.created_at,
        requires_sales_agreement=not t.sales_agreed,
    )


@router.post("/transfers", response_model=TransferOut, status_code=201)
def record_transfer(
    payload: TransferCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_edit),
):
    """Record an intended production transfer between plants (R8.3).

    Recorded as a proposal that indicates sales must be consulted before it is applied.
    """
    if db.get(ProductLine, payload.product_line_id) is None:
        raise NotFoundError(f"Line {payload.product_line_id} not found.")
    for plant_id in (payload.from_plant_id, payload.to_plant_id):
        if db.get(Plant, plant_id) is None:
            raise NotFoundError(f"Plant {plant_id} not found.")

    transfer = ProductionTransfer(
        product_line_id=payload.product_line_id,
        from_plant_id=payload.from_plant_id,
        to_plant_id=payload.to_plant_id,
        market=payload.market,
        note=payload.note,
        created_by=user.username,
    )
    db.add(transfer)
    db.commit()
    db.refresh(transfer)
    return _to_out(transfer)


@router.get("/transfers", response_model=list[TransferOut])
def list_transfers(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    transfers = db.scalars(
        select(ProductionTransfer).order_by(ProductionTransfer.created_at.desc())
    ).all()
    return [_to_out(t) for t in transfers]


@router.post("/transfers/{transfer_id}/agree", response_model=TransferOut)
def mark_sales_agreed(
    transfer_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """Record that sales has been consulted and agreed the transfer (R8.3)."""
    transfer = db.get(ProductionTransfer, transfer_id)
    if transfer is None:
        raise NotFoundError(f"Transfer {transfer_id} not found.")
    transfer.sales_agreed = True
    db.commit()
    db.refresh(transfer)
    return _to_out(transfer)


@router.post("/transfers/{transfer_id}/apply", response_model=TransferOut)
def apply_transfer(
    transfer_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require_role(RoleName.central_admin)),
):
    """Apply a transfer by moving the line to the destination plant (R8.3).

    Blocked until sales has agreed, so the change cannot be applied without
    consulting sales first.
    """
    transfer = db.get(ProductionTransfer, transfer_id)
    if transfer is None:
        raise NotFoundError(f"Transfer {transfer_id} not found.")
    if not transfer.sales_agreed:
        raise AppError(
            "Sales must be consulted and agree the transfer before it is applied.",
            code="sales_agreement_required",
            status_code=409,
        )
    line = db.get(ProductLine, transfer.product_line_id)
    if line is None:
        raise NotFoundError(f"Line {transfer.product_line_id} not found.")
    line.plant_id = transfer.to_plant_id
    transfer.applied = True
    db.commit()
    db.refresh(transfer)
    return _to_out(transfer)
