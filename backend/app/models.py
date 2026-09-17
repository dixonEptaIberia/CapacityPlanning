"""SQLAlchemy ORM models for the capacity planning platform.

Implements the domain model from design.md: Company -> Plant -> ProductLine ->
WeekCell, plus CadenceOption master data, Platform overlap, LineLink (combined
process), PlanVersion/WeekCellSnapshot, Scenario, RBAC, and configuration.
"""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


# --- Enumerations ---------------------------------------------------------


class RoleName(str, enum.Enum):
    central_admin = "central-admin"
    planner = "planner"
    viewer = "viewer"
    plant_viewer = "plant-viewer"


class ChangeStatus(str, enum.Enum):
    """Distinguishes proposals (hypotheses) from changes applied in Compass (R7.3)."""

    proposal = "proposal"
    applied_in_compass = "applied-in-compass"


class VersionKind(str, enum.Enum):
    named = "named"
    official = "official"


# --- Association tables ---------------------------------------------------

product_line_platform = Table(
    "product_line_platform",
    Base.metadata,
    Column("product_line_id", ForeignKey("product_lines.id"), primary_key=True),
    Column("platform_id", ForeignKey("platforms.id"), primary_key=True),
)


# --- Core hierarchy -------------------------------------------------------


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)

    plants: Mapped[list["Plant"]] = relationship(back_populates="company")


class Plant(Base):
    __tablename__ = "plants"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int | None] = mapped_column(ForeignKey("companies.id"))
    name: Mapped[str] = mapped_column(String(120), unique=True)
    country: Mapped[str | None] = mapped_column(String(80))
    region: Mapped[str] = mapped_column(String(40), default="EMEA")
    # Length of the frozen period in weeks; varies by industrial cycle (R6.3).
    frozen_weeks: Mapped[int] = mapped_column(Integer, default=3)
    # Standard working days in a full week for this plant; drives output
    # pro-rating for short weeks (e.g. 5-day EMEA plants, 6-day Istanbul).
    standard_working_days: Mapped[int] = mapped_column(Integer, default=5)
    # Hypothetical/sandbox plant for testing; excluded from official data (R15.2).
    hypothetical: Mapped[bool] = mapped_column(Boolean, default=False)

    company: Mapped[Company | None] = relationship(back_populates="plants")
    product_lines: Mapped[list["ProductLine"]] = relationship(back_populates="plant")
    workforce_targets: Mapped[list["WorkforceTarget"]] = relationship(back_populates="plant")


class Platform(Base):
    """A product platform (e.g., A1, Alpha 1, NC5) that may be built at multiple plants."""

    __tablename__ = "platforms"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)

    product_lines: Mapped[list["ProductLine"]] = relationship(
        secondary=product_line_platform, back_populates="platforms"
    )


class ProductLine(Base):
    __tablename__ = "product_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id"))
    # Product/project name, product family (R1.2).
    name: Mapped[str] = mapped_column(String(160))
    product_family: Mapped[str | None] = mapped_column(String(120))
    # Production-scheduler info: routings and SAP work centers (display-only, R1.2).
    routing_info: Mapped[str | None] = mapped_column(String(200))
    sap_work_center: Mapped[str | None] = mapped_column(String(80))
    # Hypothetical/sandbox line for testing; excluded from official data (R15.2).
    hypothetical: Mapped[bool] = mapped_column(Boolean, default=False)

    plant: Mapped[Plant] = relationship(back_populates="product_lines")
    platforms: Mapped[list[Platform]] = relationship(
        secondary=product_line_platform, back_populates="product_lines"
    )
    week_cells: Mapped[list["WeekCell"]] = relationship(back_populates="product_line")


class LineLink(Base):
    """Declares two lines as one combined process (R4).

    A cadence change on the primary line adjusts the secondary line's output by
    ``ratio`` (e.g., 1.0 mirrors the change, 0.5 halves it).
    """

    __tablename__ = "line_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    primary_line_id: Mapped[int] = mapped_column(ForeignKey("product_lines.id"))
    secondary_line_id: Mapped[int] = mapped_column(ForeignKey("product_lines.id"))
    ratio: Mapped[float] = mapped_column(Float, default=1.0)


# --- Master data ----------------------------------------------------------


class CadenceOption(Base):
    """Approved rate/worker combination supplied by the technical department (R2).

    ``workers`` is the total headcount, ``shifts`` the number of shifts, and
    ``pieces_per_week`` the approved theoretical output for that combination.
    Imported from Excel master data (R11).
    """

    __tablename__ = "cadence_options"
    __table_args__ = (UniqueConstraint("label", name="uq_cadence_label"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Human label as used in the spreadsheet, e.g. "1" or "11 + 11".
    label: Mapped[str] = mapped_column(String(40))
    workers: Mapped[int] = mapped_column(Integer)
    shifts: Mapped[int] = mapped_column(Integer, default=1)
    pieces_per_week: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


# --- Weekly planning grid -------------------------------------------------


class WeekCell(Base):
    """A single (product line, ISO week) planning cell (R1.3)."""

    __tablename__ = "week_cells"
    __table_args__ = (
        UniqueConstraint("product_line_id", "iso_year_week", name="uq_cell_line_week"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_line_id: Mapped[int] = mapped_column(ForeignKey("product_lines.id"))
    # ISO year-week, e.g. "2026-W34".
    iso_year_week: Mapped[str] = mapped_column(String(10))

    working_days: Mapped[int] = mapped_column(Integer, default=5)
    cadence_option_id: Mapped[int | None] = mapped_column(ForeignKey("cadence_options.id"))
    workers_assigned: Mapped[int] = mapped_column(Integer, default=0)
    # Manual adjustment applied to theoretical output (delay/ahead/extra capacity, R2.3).
    capacity_delta: Mapped[int] = mapped_column(Integer, default=0)

    product_line: Mapped[ProductLine] = relationship(back_populates="week_cells")
    cadence_option: Mapped[CadenceOption | None] = relationship()
    notes: Mapped[list["Note"]] = relationship(back_populates="week_cell")


class WorkforceTarget(Base):
    """Target staffing per plant/period; drives above/below indicator (R3)."""

    __tablename__ = "workforce_targets"
    __table_args__ = (
        UniqueConstraint("plant_id", "iso_year_week", name="uq_target_plant_week"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id"))
    iso_year_week: Mapped[str] = mapped_column(String(10))
    target_workers: Mapped[int] = mapped_column(Integer)

    plant: Mapped[Plant] = relationship(back_populates="workforce_targets")


class Note(Base):
    """A note attached to a planning cell/area; drives highlighting (R9)."""

    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    week_cell_id: Mapped[int] = mapped_column(ForeignKey("week_cells.id"))
    author: Mapped[str] = mapped_column(String(120))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    week_cell: Mapped[WeekCell] = relationship(back_populates="notes")


# --- Scenarios and versions -----------------------------------------------


class Scenario(Base):
    """A hypothesis branch that does not touch the official dataset (R5)."""

    __tablename__ = "scenarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    plant_id: Mapped[int | None] = mapped_column(ForeignKey("plants.id"))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[ChangeStatus] = mapped_column(Enum(ChangeStatus), default=ChangeStatus.proposal)
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    promoted: Mapped[bool] = mapped_column(Boolean, default=False)

    snapshots: Mapped[list["WeekCellSnapshot"]] = relationship(back_populates="scenario")


class PlanVersion(Base):
    """A saved version; official releases are the shared agreement (R6, R7)."""

    __tablename__ = "plan_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    plant_id: Mapped[int | None] = mapped_column(ForeignKey("plants.id"))
    kind: Mapped[VersionKind] = mapped_column(Enum(VersionKind), default=VersionKind.named)
    explanation: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    snapshots: Mapped[list["WeekCellSnapshot"]] = relationship(back_populates="version")


class WeekCellSnapshot(Base):
    """Immutable copy of a cell's values captured in a version or scenario."""

    __tablename__ = "week_cell_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int | None] = mapped_column(ForeignKey("plan_versions.id"))
    scenario_id: Mapped[int | None] = mapped_column(ForeignKey("scenarios.id"))
    product_line_id: Mapped[int] = mapped_column(ForeignKey("product_lines.id"))
    iso_year_week: Mapped[str] = mapped_column(String(10))
    working_days: Mapped[int] = mapped_column(Integer)
    cadence_label: Mapped[str | None] = mapped_column(String(40))
    workers_assigned: Mapped[int] = mapped_column(Integer)
    capacity_delta: Mapped[int] = mapped_column(Integer)
    expected_pieces: Mapped[int] = mapped_column(Integer)
    actual_output: Mapped[int] = mapped_column(Integer)

    version: Mapped[PlanVersion | None] = relationship(back_populates="snapshots")
    scenario: Mapped[Scenario | None] = relationship(back_populates="snapshots")


# --- Governance (RBAC) ----------------------------------------------------


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(120), unique=True)
    display_name: Mapped[str | None] = mapped_column(String(160))
    role: Mapped[RoleName] = mapped_column(Enum(RoleName), default=RoleName.viewer)
    # Optional plant/region scope; null means all (R12 scoping).
    scope_plant_id: Mapped[int | None] = mapped_column(ForeignKey("plants.id"))
    scope_region: Mapped[str | None] = mapped_column(String(40))


# --- Configuration over code ----------------------------------------------


class ConfigEntry(Base):
    """Generic configuration key/value for the config-over-code layer (R13)."""

    __tablename__ = "config_entries"
    __table_args__ = (UniqueConstraint("key", name="uq_config_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(120))
    value: Mapped[str] = mapped_column(Text)


class ProductionTransfer(Base):
    """A recorded intent to move production between plants for a market/country (R8.3).

    The transfer is a proposal only: ``sales_agreed`` must be set before it is
    applied, so the platform makes the "consult sales first" requirement explicit.
    """

    __tablename__ = "production_transfers"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_line_id: Mapped[int] = mapped_column(ForeignKey("product_lines.id"))
    from_plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id"))
    to_plant_id: Mapped[int] = mapped_column(ForeignKey("plants.id"))
    market: Mapped[str | None] = mapped_column(String(120))
    note: Mapped[str | None] = mapped_column(Text)
    # Sales must be consulted and the change agreed before it is applied (R8.3).
    sales_agreed: Mapped[bool] = mapped_column(Boolean, default=False)
    applied: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class RuleDefinition(Base):
    """A configurable special rule evaluated by the rules engine (R4.2, R13.2)."""

    __tablename__ = "rule_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    rule_type: Mapped[str] = mapped_column(String(80))
    # JSON-encoded parameters; interpreted by the engine.
    params_json: Mapped[str] = mapped_column(Text, default="{}")
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class KpiDefinition(Base):
    """A dashboard field / KPI defined through configuration (R13.3).

    KPIs are added, changed, or removed via the config API rather than in code.
    ``source_field`` names the per-cell value to aggregate (e.g. ``actual_output``,
    ``expected_pieces``, ``workers_assigned``, ``capacity_delta``); ``aggregation``
    is one of ``sum``, ``avg``, ``min``, ``max``.
    """

    __tablename__ = "kpi_definitions"
    __table_args__ = (UniqueConstraint("name", name="uq_kpi_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    source_field: Mapped[str] = mapped_column(String(80))
    aggregation: Mapped[str] = mapped_column(String(20), default="sum")
    unit: Mapped[str | None] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
