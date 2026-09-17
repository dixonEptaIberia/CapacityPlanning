"""Seed development data so the platform is usable out of the box.

Creates the EMEA plants from the meeting notes, a few product lines and
platforms, approved cadence options (incl. the 60 and 144 examples), a linked
line pair, workforce targets, and users for each role.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.db.base import SessionLocal
from app.domain import weeks
from app.models import (
    CadenceOption,
    Company,
    LineLink,
    Platform,
    Plant,
    ProductLine,
    RoleName,
    User,
    WeekCell,
    WorkforceTarget,
)

# Plant name -> (frozen weeks, standard working days) from the meeting notes.
# Istanbul runs a 6-day week; the others use the 5-day EMEA standard.
_PLANTS = {
    "Limana": (3, 5),
    "Solesino": (3, 5),
    "Casale": (6, 5),
    "Istanbul": (3, 6),
    "France": (3, 5),
    "Bradford": (4, 5),
}


def seed_if_empty() -> None:
    db = SessionLocal()
    try:
        if db.scalar(select(Plant).limit(1)) is not None:
            return  # already seeded

        company = Company(name="EMEA Manufacturing")
        db.add(company)
        db.flush()

        # Approved cadence options (technical department master data).
        one = CadenceOption(label="1", workers=1, shifts=1, pieces_per_week=60)
        eleven = CadenceOption(label="11 + 11", workers=22, shifts=2, pieces_per_week=144)
        five = CadenceOption(label="5", workers=5, shifts=1, pieces_per_week=100)
        db.add_all([one, eleven, five])
        db.flush()

        # Platforms shared across plants (regional overlap).
        a1 = Platform(name="A1")
        alpha1 = Platform(name="Alpha 1")
        nc5 = Platform(name="NC5")
        db.add_all([a1, alpha1, nc5])
        db.flush()

        plants: dict[str, Plant] = {}
        for name, (frozen, working_days) in _PLANTS.items():
            plant = Plant(
                company_id=company.id,
                name=name,
                country=name,
                frozen_weeks=frozen,
                standard_working_days=working_days,
            )
            db.add(plant)
            plants[name] = plant
        db.flush()

        # A few product lines; some share platforms for regional aggregation.
        limana = plants["Limana"]
        casale = plants["Casale"]
        line_a = ProductLine(
            plant_id=limana.id,
            name="Line A1-Front",
            product_family="Compressors",
            routing_info="RT-100",
            sap_work_center="WC-LIM-01",
            platforms=[a1],
        )
        line_b = ProductLine(
            plant_id=limana.id,
            name="Line A1-Back",
            product_family="Compressors",
            routing_info="RT-101",
            sap_work_center="WC-LIM-02",
            platforms=[a1],
        )
        line_c = ProductLine(
            plant_id=casale.id,
            name="Line A1-Casale",
            product_family="Compressors",
            routing_info="RT-200",
            sap_work_center="WC-CAS-01",
            platforms=[a1],
        )
        # A standalone (non-linked) Limana line. Sorts first by name so it is the
        # natural "plain line" for planning without linked-line deduction.
        line_solo = ProductLine(
            plant_id=limana.id,
            name="Line A0-Solo",
            product_family="Compressors",
            routing_info="RT-090",
            sap_work_center="WC-LIM-00",
        )
        db.add_all([line_a, line_b, line_c, line_solo])
        db.flush()

        # Line A1-Front (Master) and A1-Back (Slave) are one combined process
        # (Linee_Collegate): the Master's output is deducted from the Slave (R4.1).
        db.add(LineLink(primary_line_id=line_a.id, secondary_line_id=line_b.id, ratio=1.0))

        # Seed the first few open weeks with a starting cadence. The Master
        # (line_a) runs a smaller cadence than the Slave (line_b) so the Slave
        # nets a positive shared output (144 - 100 = 44) out of the box.
        start = weeks.iso_week_label(date.today())
        week_labels = weeks.week_range(start, 8)
        for line, combo in ((line_a, five), (line_b, eleven), (line_c, one)):
            for w in week_labels:
                db.add(
                    WeekCell(
                        product_line_id=line.id,
                        iso_year_week=w,
                        working_days=5,
                        cadence_option_id=combo.id,
                        workers_assigned=combo.workers,
                        capacity_delta=0,
                    )
                )

        # Workforce targets for Limana.
        for w in week_labels:
            db.add(WorkforceTarget(plant_id=limana.id, iso_year_week=w, target_workers=25))

        # Users for each role.
        db.add_all(
            [
                User(username="admin", display_name="Central Admin", role=RoleName.central_admin),
                User(
                    username="planner",
                    display_name="Planner",
                    role=RoleName.planner,
                    scope_region="EMEA",
                ),
                User(username="viewer", display_name="Viewer", role=RoleName.viewer),
                User(
                    username="limana_viewer",
                    display_name="Limana Plant Viewer",
                    role=RoleName.plant_viewer,
                    scope_plant_id=limana.id,
                ),
            ]
        )
        db.commit()
    finally:
        db.close()
