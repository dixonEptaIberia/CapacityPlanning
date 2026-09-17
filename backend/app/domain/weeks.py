"""ISO week helpers used by the planning grid and frozen-period logic."""
from __future__ import annotations

from datetime import date, timedelta


def iso_week_label(d: date) -> str:
    """Return an ISO year-week label like '2026-W34' for a date."""
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def parse_week_label(label: str) -> tuple[int, int]:
    """Parse '2026-W34' into (year, week)."""
    year_str, week_str = label.split("-W")
    return int(year_str), int(week_str)


def monday_of(label: str) -> date:
    """Return the Monday date of the given ISO year-week label."""
    year, week = parse_week_label(label)
    return date.fromisocalendar(year, week, 1)


def week_range(start_label: str, count: int) -> list[str]:
    """Return ``count`` consecutive ISO week labels starting at ``start_label``."""
    start = monday_of(start_label)
    return [iso_week_label(start + timedelta(weeks=i)) for i in range(count)]


def weeks_between(current_label: str, target_label: str) -> int:
    """Whole weeks from ``current_label`` to ``target_label`` (negative if in the past)."""
    delta = monday_of(target_label) - monday_of(current_label)
    return delta.days // 7


def is_frozen(current_label: str, target_label: str, frozen_weeks: int) -> bool:
    """A target week is frozen if it lies within the plant's frozen window.

    The current week and the next ``frozen_weeks - 1`` weeks are frozen (R6.3).
    Past weeks are also considered frozen (already closed).
    """
    offset = weeks_between(current_label, target_label)
    if offset < 0:
        return True
    return offset < frozen_weeks


def first_open_week(current_label: str, frozen_weeks: int) -> str:
    """The first week outside the plant's frozen period (R6.4).

    This is the week that must be finalized by the Friday of the current week.
    """
    start = monday_of(current_label)
    return iso_week_label(start + timedelta(weeks=frozen_weeks))


def is_finalization_week(current_label: str, target_label: str, frozen_weeks: int) -> bool:
    """Whether ``target_label`` is the week that must be finalized this cycle (R6.4).

    When the current week ends, the first week outside the frozen period must be
    finalized by the Friday of the current week; later weeks stay open for
    subsequent discussion.
    """
    return target_label == first_open_week(current_label, frozen_weeks)


def finalization_overdue(today: date, current_label: str) -> bool:
    """Whether the Friday finalization deadline for the current week has passed (R6.4).

    Returns True on Saturday and Sunday of the current week (i.e., after Friday).
    ``today`` must fall within ``current_label``'s week.
    """
    # isoweekday: Monday=1 .. Friday=5, Saturday=6, Sunday=7.
    return today.isoweekday() > 5
