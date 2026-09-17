"""Pydantic request/response schemas (API contract).

All endpoints validate payloads against these schemas (R5.1).
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import ChangeStatus, RoleName, VersionKind


# --- Master data ----------------------------------------------------------


class CadenceOptionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    workers: int
    shifts: int
    pieces_per_week: int
    active: bool


# --- Plants / lines -------------------------------------------------------


class PlantOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    country: str | None = None
    region: str
    frozen_weeks: int
    standard_working_days: int = 5
    hypothetical: bool = False


class ProductLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plant_id: int
    name: str
    product_family: str | None = None
    routing_info: str | None = None
    sap_work_center: str | None = None
    platforms: list[str] = Field(default_factory=list)
    hypothetical: bool = False


# --- Grid cells -----------------------------------------------------------


class CellComputed(BaseModel):
    """Derived values returned alongside a cell (from the rules engine)."""

    expected_pieces: int
    actual_output: int
    frozen: bool
    has_note: bool
    # R6.4: the first week outside the frozen period awaiting finalization.
    finalization_due: bool = False
    # R6.4: the Friday deadline for the current cycle has already passed.
    finalization_overdue: bool = False


class CellOut(BaseModel):
    product_line_id: int
    iso_year_week: str
    working_days: int
    cadence_option_id: int | None
    cadence_label: str | None
    workers_assigned: int
    capacity_delta: int
    computed: CellComputed


class CellUpdate(BaseModel):
    working_days: int | None = Field(default=None, ge=0, le=7)
    cadence_option_id: int | None = None
    workers_assigned: int | None = Field(default=None, ge=0)
    capacity_delta: int | None = None


class GridRow(BaseModel):
    line: ProductLineOut
    cells: list[CellOut]


class WorkforceStatus(BaseModel):
    iso_year_week: str
    target_workers: int
    assigned_workers: int
    status: str  # "above" | "at" | "below"
    delta: int


class WeekTotals(BaseModel):
    """Per-week totals across the plant's official lines (the spreadsheet's bottom row)."""

    iso_year_week: str
    total_expected_pieces: int
    total_actual_output: int
    total_workers: int


class GridResponse(BaseModel):
    plant: PlantOut
    weeks: list[str]
    rows: list[GridRow]
    workforce: list[WorkforceStatus]
    totals: list[WeekTotals]
    # Configurable label for the takt/cadence metric (R13, Column E). Editable
    # via configuration; the frontend uses it instead of a hardcoded string.
    takt_label: str = "Takt"


# --- Regional -------------------------------------------------------------


class PlatformAggregateRow(BaseModel):
    iso_year_week: str
    total_expected_pieces: int
    total_actual_output: int
    per_plant: dict[str, int]


class RegionalResponse(BaseModel):
    platform: str
    weeks: list[str]
    rows: list[PlatformAggregateRow]


# --- Notes ----------------------------------------------------------------


class NoteCreate(BaseModel):
    product_line_id: int
    iso_year_week: str
    text: str = Field(min_length=1)


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    week_cell_id: int
    author: str
    text: str
    created_at: datetime


# --- Scenarios / versions -------------------------------------------------


class ScenarioCreate(BaseModel):
    name: str = Field(min_length=1)
    plant_id: int | None = None
    description: str | None = None


class ScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    plant_id: int | None
    description: str | None
    status: ChangeStatus
    created_by: str
    created_at: datetime
    promoted: bool


class VersionCreate(BaseModel):
    name: str = Field(min_length=1)
    plant_id: int | None = None
    explanation: str | None = None


class VersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    plant_id: int | None
    kind: VersionKind
    explanation: str | None
    created_by: str
    created_at: datetime


class DiffCell(BaseModel):
    product_line_id: int
    iso_year_week: str
    field: str
    base_value: object
    current_value: object
    # R7.3: whether this change is already applied in Compass or still a proposal.
    status: ChangeStatus = ChangeStatus.proposal


class DiffResponse(BaseModel):
    base_version_id: int
    changes: list[DiffCell]


class SnapshotRow(BaseModel):
    """A single cell's stored values within a saved version (R7.4 historical access)."""

    model_config = ConfigDict(from_attributes=True)

    product_line_id: int
    line_name: str | None = None
    iso_year_week: str
    working_days: int
    cadence_label: str | None
    workers_assigned: int
    capacity_delta: int
    expected_pieces: int
    actual_output: int


class VersionSnapshotResponse(BaseModel):
    version_id: int
    rows: list[SnapshotRow]
    # Configurable takt label so the Official Version table matches the grid.
    takt_label: str = "Takt"


# --- Config ---------------------------------------------------------------


class ConfigEntryIn(BaseModel):
    key: str = Field(min_length=1)
    value: str


class ConfigEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    value: str


class RuleDefinitionIn(BaseModel):
    name: str = Field(min_length=1)
    rule_type: str = Field(min_length=1)
    params_json: str = "{}"
    active: bool = True


class RuleDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    rule_type: str
    params_json: str
    active: bool


class KpiDefinitionIn(BaseModel):
    name: str = Field(min_length=1)
    source_field: str = Field(min_length=1)
    aggregation: str = "sum"
    unit: str | None = None
    active: bool = True


class KpiDefinitionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source_field: str
    aggregation: str
    unit: str | None
    active: bool


class KpiValue(BaseModel):
    """A computed KPI for a plant over the requested weeks (R13.3)."""

    name: str
    source_field: str
    aggregation: str
    unit: str | None
    value: float


class KpiDashboardResponse(BaseModel):
    plant_id: int
    weeks: list[str]
    kpis: list[KpiValue]


class CompanyIn(BaseModel):
    name: str = Field(min_length=1)


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class LineMoveIn(BaseModel):
    plant_id: int


# --- Linked lines / Linee_Collegate (R4) ----------------------------------


class LineLinkIn(BaseModel):
    """Declare two lines of one plant as a combined process (Master/Slave).

    ``plant_id`` is the plant both lines belong to; ``master_line_id`` drives the
    output and ``slave_line_id`` is adjusted when the master is active. ``ratio``
    is the share of the master's output applied to the slave (1.0 mirrors it).
    """

    plant_id: int
    master_line_id: int
    slave_line_id: int
    ratio: float = 1.0


class LineLinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plant_id: int
    master_line_id: int
    slave_line_id: int
    master_line_name: str | None = None
    slave_line_name: str | None = None
    ratio: float


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    display_name: str | None
    role: RoleName
    scope_plant_id: int | None
    scope_region: str | None


class ImportResult(BaseModel):
    imported: int
    updated: int
    errors: list[str] = Field(default_factory=list)


# --- Production transfers (R8.3) ------------------------------------------


class TransferCreate(BaseModel):
    product_line_id: int
    from_plant_id: int
    to_plant_id: int
    market: str | None = None
    note: str | None = None


class TransferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_line_id: int
    from_plant_id: int
    to_plant_id: int
    market: str | None
    note: str | None
    sales_agreed: bool
    applied: bool
    created_by: str
    created_at: datetime
    # Human-facing reminder surfaced whenever the transfer is not yet agreed (R8.3).
    requires_sales_agreement: bool = True


class ErrorBody(BaseModel):
    code: str
    message: str
    correlation_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody
