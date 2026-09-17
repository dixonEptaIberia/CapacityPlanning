"""Business rules engine (the core of the existing planning logic).

Implemented as pure functions over plain data so they are trivially testable and
independent of the ORM. The service layer feeds ORM values in and stores results.

Covers:
- Theoretical output from cadence x workers, and capacity delta (R2.1, R2.3, R2.4)
- Approved-combination enforcement (R2.2)
- Workforce target evaluation: above / at / below (R3)
- Combined/linked-line adjustment (R4)
- Frozen-period enforcement (R1.5, R6.3, R6.4)
- Regional aggregation across plants sharing a platform (R8.2)
"""
from __future__ import annotations

from dataclasses import dataclass


class RuleError(ValueError):
    """Raised when a planning value violates a business rule."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class CadenceCombo:
    """An approved rate/worker combination (subset of CadenceOption)."""

    id: int
    label: str
    workers: int
    shifts: int
    pieces_per_week: int


@dataclass(frozen=True)
class CellInput:
    working_days: int
    workers_assigned: int
    capacity_delta: int
    cadence: CadenceCombo | None
    # Standard working days in a full week for this line's plant; drives
    # short-week pro-rating. Defaults to the 5-day EMEA standard.
    full_week_days: int = 5


@dataclass(frozen=True)
class CellResult:
    expected_pieces: int
    actual_output: int


# Default standard working week (days); overridable per plant via
# ``full_week_days`` so 6-day plants (e.g. Istanbul) pro-rate correctly.
FULL_WEEK_DAYS = 5


def theoretical_output(
    cadence: CadenceCombo | None,
    working_days: int,
    full_week_days: int = FULL_WEEK_DAYS,
) -> int:
    """Theoretical weekly output from an approved cadence, pro-rated by working days (R2.1).

    ``pieces_per_week`` is defined for a standard full week of ``full_week_days``
    days (the plant's standard working week). Fewer working days scale the output
    proportionally: a 6-day plant with a "60 pieces" cadence yields 30 at 3 days.
    A full or longer week yields the full ``pieces_per_week``.
    """
    if cadence is None:
        return 0
    if full_week_days <= 0:
        return 0
    if working_days >= full_week_days:
        return cadence.pieces_per_week
    if working_days <= 0:
        return 0
    return round(cadence.pieces_per_week * working_days / full_week_days)


def compute_cell(cell: CellInput) -> CellResult:
    """Compute expected pieces and actual output for a cell (R2.1, R2.3, R2.4).

    ``actual_output = expected_pieces + capacity_delta`` (delta may be negative).
    Actual output is floored at zero. Pro-rating uses the plant's standard
    working week (``cell.full_week_days``).
    """
    expected = theoretical_output(cell.cadence, cell.working_days, cell.full_week_days)
    actual = max(0, expected + cell.capacity_delta)
    return CellResult(expected_pieces=expected, actual_output=actual)


def validate_cadence_choice(
    cadence_id: int | None, approved: dict[int, CadenceCombo]
) -> CadenceCombo | None:
    """Reject cadence values not present in approved master data (R2.2).

    Planners must use approved combinations rather than inventing staffing structures.
    """
    if cadence_id is None:
        return None
    combo = approved.get(cadence_id)
    if combo is None:
        raise RuleError(
            "cadence_not_approved",
            f"Cadence option {cadence_id} is not an approved combination.",
        )
    return combo


def validate_workers_match(cadence: CadenceCombo | None, workers_assigned: int) -> None:
    """Ensure assigned workers match the approved combination's headcount (R2.2)."""
    if cadence is None:
        return
    if workers_assigned != cadence.workers:
        raise RuleError(
            "workers_mismatch",
            (
                f"Assigned workers ({workers_assigned}) do not match the approved "
                f"cadence '{cadence.label}' headcount ({cadence.workers})."
            ),
        )


@dataclass(frozen=True)
class WorkforceEval:
    target_workers: int
    assigned_workers: int
    status: str  # "above" | "at" | "below"
    delta: int


def evaluate_workforce(target_workers: int, assigned_workers: int) -> WorkforceEval:
    """Compare assigned workers against the plant/period target (R3.2, R3.3)."""
    delta = assigned_workers - target_workers
    if delta > 0:
        status = "above"
    elif delta < 0:
        status = "below"
    else:
        status = "at"
    return WorkforceEval(target_workers, assigned_workers, status, delta)


def linked_slave_output(slave_expected: int, master_expected: int, adjustment: int) -> int:
    """Output of a Slave line linked to a Master line (Linee_Collegate, R4.1).

    Two lines that share the same physical output are configured as Master and
    Slave. The Master's theoretical output is deducted from the Slave's own
    theoretical output, then the Slave's Adj. Qnty is applied:

        slave_output = slave_expected - master_expected + adjustment

    The deduction only applies while the Master is actually producing
    (``master_expected > 0``); otherwise the Slave stands alone. The result is
    floored at zero (a line cannot produce a negative quantity).
    """
    if master_expected <= 0:
        return max(0, slave_expected + adjustment)
    return max(0, slave_expected - master_expected + adjustment)


def aggregate_regional(per_plant_actuals: dict[str, int]) -> int:
    """Total potential output across plants sharing a platform (R8.2)."""
    return sum(per_plant_actuals.values())


# --- Configurable special rules (R4.2, R13.2) -----------------------------


@dataclass(frozen=True)
class SpecialRule:
    """A configurable special rule from the RuleDefinition table.

    ``rule_type`` selects the behaviour; ``params`` are interpreted per type:

    - ``cap``   : clamp actual output to ``params['max']`` (a hard ceiling).
    - ``floor`` : raise actual output to at least ``params['min']``.
    - ``scale`` : multiply actual output by ``params['factor']`` and round.

    Unknown rule types are ignored so a bad config entry never breaks planning.
    """

    name: str
    rule_type: str
    params: dict


# --- Configurable dashboard KPIs (R13.3) ----------------------------------

KPI_SOURCE_FIELDS = ("actual_output", "expected_pieces", "workers_assigned", "capacity_delta")
KPI_AGGREGATIONS = ("sum", "avg", "min", "max")


def aggregate_kpi(values: list[float], aggregation: str) -> float:
    """Aggregate a list of per-cell values for a configured KPI (R13.3).

    Empty inputs yield 0. ``avg`` is rounded to two decimals.
    """
    if not values:
        return 0
    if aggregation == "sum":
        return sum(values)
    if aggregation == "avg":
        return round(sum(values) / len(values), 2)
    if aggregation == "min":
        return min(values)
    if aggregation == "max":
        return max(values)
    raise RuleError("unknown_aggregation", f"Unknown KPI aggregation '{aggregation}'.")


def apply_special_rules(actual_output: int, applicable: list[SpecialRule]) -> int:
    """Apply special rules to an actual output value, consistently and in order (R4.3).

    Rules are applied in the order given. The result is always floored at zero.
    """
    value = actual_output
    for rule in applicable:
        if rule.rule_type == "cap":
            max_val = rule.params.get("max")
            if isinstance(max_val, (int, float)):
                value = min(value, int(max_val))
        elif rule.rule_type == "floor":
            min_val = rule.params.get("min")
            if isinstance(min_val, (int, float)):
                value = max(value, int(min_val))
        elif rule.rule_type == "scale":
            factor = rule.params.get("factor")
            if isinstance(factor, (int, float)):
                value = round(value * factor)
        # Unknown rule types are intentionally ignored.
    return max(0, value)
