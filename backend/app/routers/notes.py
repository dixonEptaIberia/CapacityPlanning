"""Planning notes endpoints (R9)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, require_edit
from app.db.base import get_db
from app.models import Note, User
from app.schemas import NoteCreate, NoteOut
from app.services import planning

router = APIRouter(tags=["notes"])


@router.post("/notes", response_model=NoteOut, status_code=201)
def create_note(
    payload: NoteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_edit),
):
    """Attach a note to a planning cell; presence drives grid highlighting (R9.1, R9.2)."""
    cell = planning.get_or_create_cell(db, payload.product_line_id, payload.iso_year_week)
    note = Note(week_cell_id=cell.id, author=user.username, text=payload.text)
    db.add(note)
    db.commit()
    db.refresh(note)
    return note


@router.get("/notes", response_model=list[NoteOut])
def list_notes(
    product_line_id: int,
    iso_year_week: str,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
):
    """Return notes for a cell so the UI can show context (R9.3)."""
    cell = planning.get_or_create_cell(db, product_line_id, iso_year_week)
    db.commit()
    return db.scalars(
        select(Note).where(Note.week_cell_id == cell.id).order_by(Note.created_at)
    ).all()
