"""Unit tests for ISO week helpers and frozen-period logic (R6.3)."""
from __future__ import annotations

from app.domain import weeks


def test_week_range_generates_consecutive_labels():
    labels = weeks.week_range("2026-W34", 3)
    assert labels == ["2026-W34", "2026-W35", "2026-W36"]


def test_week_range_crosses_year_boundary():
    labels = weeks.week_range("2026-W52", 3)
    assert labels[0] == "2026-W52"
    assert len(labels) == 3


def test_weeks_between():
    assert weeks.weeks_between("2026-W34", "2026-W37") == 3
    assert weeks.weeks_between("2026-W37", "2026-W34") == -3


def test_current_week_is_frozen():
    # Offset 0 falls within any positive frozen window.
    assert weeks.is_frozen("2026-W34", "2026-W34", frozen_weeks=3) is True


def test_weeks_within_window_are_frozen():
    # frozen_weeks=3 freezes offsets 0, 1, 2.
    assert weeks.is_frozen("2026-W34", "2026-W36", frozen_weeks=3) is True


def test_first_week_outside_window_is_open():
    # Offset 3 is the first non-frozen week for frozen_weeks=3.
    assert weeks.is_frozen("2026-W34", "2026-W37", frozen_weeks=3) is False


def test_past_weeks_are_frozen():
    assert weeks.is_frozen("2026-W34", "2026-W30", frozen_weeks=3) is True


def test_casale_six_week_freeze():
    # Casale example: six-week frozen period.
    assert weeks.is_frozen("2026-W34", "2026-W39", frozen_weeks=6) is True
    assert weeks.is_frozen("2026-W34", "2026-W40", frozen_weeks=6) is False


# --- Friday finalization / weekly cycle (R6.4) ----------------------------


def test_first_open_week_is_after_frozen_window():
    # With a 3-week frozen period, the first open week is 3 weeks out.
    assert weeks.first_open_week("2026-W10", 3) == "2026-W13"


def test_is_finalization_week_matches_first_open_week():
    assert weeks.is_finalization_week("2026-W10", "2026-W13", 3) is True
    assert weeks.is_finalization_week("2026-W10", "2026-W14", 3) is False
    # A week inside the frozen window is not the finalization week.
    assert weeks.is_finalization_week("2026-W10", "2026-W11", 3) is False


def test_finalization_overdue_after_friday():
    from datetime import date

    # 2026-W10 Monday..Sunday. Saturday/Sunday are overdue; Mon-Fri are not.
    monday = weeks.monday_of("2026-W10")
    for offset in range(5):  # Mon..Fri
        day = date.fromordinal(monday.toordinal() + offset)
        assert weeks.finalization_overdue(day, "2026-W10") is False
    saturday = date.fromordinal(monday.toordinal() + 5)
    sunday = date.fromordinal(monday.toordinal() + 6)
    assert weeks.finalization_overdue(saturday, "2026-W10") is True
    assert weeks.finalization_overdue(sunday, "2026-W10") is True
