"""Planning service: bridges the ORM and the pure rules engine.

Provides grid assembly, cell editing (with frozen-period, approved-combo, and
linked-line rules), workforce evaluation, and regional aggregation.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import FrozenWeekError, NotFoundError
from app.domain import rules, weeks
from app.domain.rules import CadenceCombo, CellInput
from app.models import (
    CadenceOption,
    ConfigEntry,
    LineLink,
    Note,
    Plant,
    ProductLine,
    RuleDefinition,
    WeekCell,
    WorkforceTarget,
)

# Config key for the customizable takt/cadence display label (R13, Column E).
# Previously the label was hardcoded; it is now editable via configuration.
TAKT_LABEL_KEY = "takt_label"
DEFAULT_TAKT_LABEL = "Takt"


def current_week_label() -> str:
    """The current ISO week; overridable in tests via monkeypatch."""
    return weeks.iso_week_label(date.today())


def get_config_value(db: Session, key: str, default: str) -> str:
    """Read a single config-over-code value, falling back to a default (R13)."""
    entry = db.scalar(select(ConfigEntry).where(ConfigEntry.key == key))
    if entry is None or entry.value is None or entry.value == "":
        return default
    return entry.value


def takt_label(db: Session) -> str:
    """The configurable takt label shown in the grid, editor, and exports.

    Editable through configuration (key ``takt_label``); defaults to "Takt".
    """
    return get_config_value(db, TAKT_LABEL_KEY, DEFAULT_TAKT_LABEL)


def _combo_from_option(opt: CadenceOption | None) -> CadenceCombo | None:
    if opt is None:
        return None
    return CadenceCombo(
        id=opt.id,
        label=opt.label,
        workers=opt.workers,
        shifts=opt.shifts,
        pieces_per_week=opt.pieces_per_week,
    )


def approved_cadence_map(db: Session) -> dict[int, CadenceCombo]:
    """All active approved cadence combinations, keyed by id (R2.2)."""
    opts = db.scalars(select(CadenceOption).where(CadenceOption.active.is_(True))).all()
    return {o.id: _combo_from_option(o) for o in opts}


def get_plant_or_404(db: Session, plant_id: int) -> Plant:
    plant = db.get(Plant, plant_id)
    if plant is None:
        raise NotFoundError(f"Plant {plant_id} not found.")
    return plant


def get_or_create_cell(db: Session, line_id: int, week: str) -> WeekCell:
    cell = db.scalar(
        select(WeekCell).where(
            WeekCell.product_line_id == line_id, WeekCell.iso_year_week == week
        )
    )
    if cell is None:
        cell = WeekCell(product_line_id=line_id, iso_year_week=week)
        db.add(cell)
        db.flush()
    return cell


def active_special_rules(db: Session) -> list[rules.SpecialRule]:
    """Load active configurable special rules from the RuleDefinition table (R4.2, R13.2)."""
    import json

    defs = db.scalars(
        select(RuleDefinition).where(RuleDefinition.active.is_(True)).order_by(RuleDefinition.id)
    ).all()
    result: list[rules.SpecialRule] = []
    for d in defs:
        try:
            params = json.loads(d.params_json) if d.params_json else {}
        except (ValueError, TypeError):
            params = {}
        if not isinstance(params, dict):
            params = {}
        result.append(rules.SpecialRule(name=d.name, rule_type=d.rule_type, params=params))
    return result


def _full_week_days_for_cell(cell: WeekCell) -> int:
    """Resolve the standard working week for a cell from its plant (5-day fallback)."""
    line = cell.product_line
    if line is not None and line.plant is not None:
        return line.plant.standard_working_days
    return rules.FULL_WEEK_DAYS


def compute_for_cell(
    cell: WeekCell,
    special_rules: list[rules.SpecialRule] | None = None,
    full_week_days: int | None = None,
) -> rules.CellResult:
    if full_week_days is None:
        full_week_days = _full_week_days_for_cell(cell)
    combo = _combo_from_option(cell.cadence_option)
    result = rules.compute_cell(
        CellInput(
            working_days=cell.working_days,
            workers_assigned=cell.workers_assigned,
            capacity_delta=cell.capacity_delta,
            cadence=combo,
            full_week_days=full_week_days,
        )
    )
    if special_rules:
        adjusted = rules.apply_special_rules(result.actual_output, special_rules)
        if adjusted != result.actual_output:
            result = rules.CellResult(
                expected_pieces=result.expected_pieces, actual_output=adjusted
            )
    return result


def linked_master_map(db: Session) -> dict[int, int]:
    """Map each Slave line to its Master line (Linee_Collegate, R4).

    ``LineLink.primary_line_id`` is the Master, ``secondary_line_id`` the Slave.
    Returned as ``{slave_line_id: master_line_id}``.
    """
    links = db.scalars(select(LineLink)).all()
    return {link.secondary_line_id: link.primary_line_id for link in links}


def compute_effective(
    db: Session,
    cell: WeekCell,
    special_rules: list[rules.SpecialRule] | None = None,
    full_week_days: int | None = None,
    master_map: dict[int, int] | None = None,
) -> rules.CellResult:
    """Compute a cell's result, applying the linked-line deduction for Slaves (R4.1).

    For a Slave line, the Master line's theoretical output for the same week is
    deducted from the Slave's output (``linked_slave_output``). For all other
    lines this is identical to :func:`compute_for_cell`.
    """
    base = compute_for_cell(cell, special_rules, full_week_days)
    if not master_map:
        return base
    master_line_id = master_map.get(cell.product_line_id)
    if master_line_id is None:
        return base

    master_cell = get_or_create_cell(db, master_line_id, cell.iso_year_week)
    master_full_week_days = _full_week_days_for_cell(master_cell)
    master_combo = _combo_from_option(master_cell.cadence_option)
    master_expected = rules.theoretical_output(
        master_combo, master_cell.working_days, master_full_week_days
    )
    adjusted = rules.linked_slave_output(
        base.expected_pieces, master_expected, cell.capacity_delta
    )
    return rules.CellResult(expected_pieces=base.expected_pieces, actual_output=adjusted)


def cell_has_note(db: Session, cell_id: int) -> bool:
    return db.scalar(select(Note.id).where(Note.week_cell_id == cell_id).limit(1)) is not None


def edit_cell(
    db: Session,
    line: ProductLine,
    week: str,
    *,
    working_days: int | None,
    cadence_option_id: int | None,
    workers_assigned: int | None,
    capacity_delta: int | None,
    unset_cadence: bool = False,
) -> WeekCell:
    """Apply an edit to a cell, enforcing business rules (R1.5, R2, R4).

    - Blocks edits inside the plant's frozen period (R1.5, R6).
    - Rejects unapproved cadence and mismatched worker headcount (R2.2).
    - Cascades to linked lines when a cadence/output change occurs (R4).
    """
    plant = line.plant
    if weeks.is_frozen(current_week_label(), week, plant.frozen_weeks):
        raise FrozenWeekError(
            f"Week {week} is within {plant.name}'s frozen period and cannot be edited."
        )

    cell = get_or_create_cell(db, line.id, week)
    approved = approved_cadence_map(db)

    if working_days is not None:
        cell.working_days = working_days

    # Resolve the intended cadence, validating against approved master data.
    if unset_cadence:
        cell.cadence_option_id = None
        combo = None
    elif cadence_option_id is not None:
        combo = rules.validate_cadence_choice(cadence_option_id, approved)
        cell.cadence_option_id = cadence_option_id
    else:
        combo = _combo_from_option(cell.cadence_option)

    if workers_assigned is not None:
        cell.workers_assigned = workers_assigned

    # Approved combinations only: assigned workers must match the cadence headcount.
    if combo is not None:
        rules.validate_workers_match(combo, cell.workers_assigned)

    if capacity_delta is not None:
        cell.capacity_delta = capacity_delta

    db.flush()

    # Refresh relationship so subsequent computation uses the new cadence. Linked
    # (Master/Slave) lines are resolved at read time via ``compute_effective``,
    # so no cascade/mutation of the Slave cell is needed here (R4.1).
    db.refresh(cell)
    return cell


def workforce_for_week(db: Session, plant: Plant, week: str) -> rules.WorkforceEval | None:
    """Evaluate assigned vs. target workers for a plant/week (R3)."""
    target = db.scalar(
        select(WorkforceTarget).where(
            WorkforceTarget.plant_id == plant.id, WorkforceTarget.iso_year_week == week
        )
    )
    if target is None:
        return None
    line_ids = [line.id for line in plant.product_lines]
    if not line_ids:
        assigned = 0
    else:
        cells = db.scalars(
            select(WeekCell).where(
                WeekCell.product_line_id.in_(line_ids), WeekCell.iso_year_week == week
            )
        ).all()
        assigned = sum(c.workers_assigned for c in cells)
    return rules.evaluate_workforce(target.target_workers, assigned)


def evaluate_kpis(db: Session, plant: Plant, week_labels: list[str]) -> list[dict]:
    """Compute each active dashboard KPI over a plant's grid (R13.3).

    KPIs are defined through configuration (KpiDefinition). Hypothetical/sandbox
    lines are excluded so KPIs reflect official data only (R15.2).
    """
    from app.models import KpiDefinition

    kpis = db.scalars(
        select(KpiDefinition).where(KpiDefinition.active.is_(True)).order_by(KpiDefinition.id)
    ).all()
    if not kpis:
        return []

    special_rules = active_special_rules(db)
    full_week_days = plant.standard_working_days
    master_map = linked_master_map(db)
    official_lines = [line for line in plant.product_lines if not line.hypothetical]

    # Collect per-cell values keyed by source field, computed once per cell.
    collected: dict[str, list[float]] = {f: [] for f in rules.KPI_SOURCE_FIELDS}
    for line in official_lines:
        for w in week_labels:
            cell = get_or_create_cell(db, line.id, w)
            result = compute_effective(db, cell, special_rules, full_week_days, master_map)
            collected["actual_output"].append(result.actual_output)
            collected["expected_pieces"].append(result.expected_pieces)
            collected["workers_assigned"].append(cell.workers_assigned)
            collected["capacity_delta"].append(cell.capacity_delta)

    results: list[dict] = []
    for kpi in kpis:
        values = collected.get(kpi.source_field, [])
        value = rules.aggregate_kpi(values, kpi.aggregation)
        results.append(
            {
                "name": kpi.name,
                "source_field": kpi.source_field,
                "aggregation": kpi.aggregation,
                "unit": kpi.unit,
                "value": value,
            }
        )
    return results


def snapshot_cells(
    db: Session,
    *,
    version_id: int | None = None,
    scenario_id: int | None = None,
    plant_id: int | None = None,
) -> int:
    """Capture immutable snapshots of the current cells (R5, R7).

    If ``plant_id`` is given, only that plant's lines are captured. Returns the
    number of snapshots created.
    """
    from app.models import WeekCellSnapshot

    line_ids: list[int] | None = None
    if plant_id is not None:
        plant = get_plant_or_404(db, plant_id)
        line_ids = [line.id for line in plant.product_lines]

    query = select(WeekCell)
    if line_ids is not None:
        query = query.where(WeekCell.product_line_id.in_(line_ids or [-1]))
    cells = db.scalars(query).all()

    master_map = linked_master_map(db)
    count = 0
    for cell in cells:
        result = compute_effective(db, cell, master_map=master_map)
        db.add(
            WeekCellSnapshot(
                version_id=version_id,
                scenario_id=scenario_id,
                product_line_id=cell.product_line_id,
                iso_year_week=cell.iso_year_week,
                working_days=cell.working_days,
                cadence_label=cell.cadence_option.label if cell.cadence_option else None,
                workers_assigned=cell.workers_assigned,
                capacity_delta=cell.capacity_delta,
                expected_pieces=result.expected_pieces,
                actual_output=result.actual_output,
            )
        )
        count += 1
    db.flush()
    return count
