"""Unit tests for the business rules engine (R2, R3, R4, R8)."""
from __future__ import annotations

import pytest

from app.domain import rules
from app.domain.rules import CadenceCombo, CellInput, RuleError

# Cadence examples from the meeting notes.
ONE_WORKER = CadenceCombo(id=1, label="1", workers=1, shifts=1, pieces_per_week=60)
ELEVEN_PLUS_ELEVEN = CadenceCombo(id=2, label="11 + 11", workers=22, shifts=2, pieces_per_week=144)


# --- Theoretical output (R2.1) --------------------------------------------


def test_one_worker_full_week_yields_60():
    assert rules.theoretical_output(ONE_WORKER, working_days=5) == 60


def test_eleven_plus_eleven_full_week_yields_144():
    assert rules.theoretical_output(ELEVEN_PLUS_ELEVEN, working_days=5) == 144


def test_output_prorated_by_working_days():
    # Half a working week (approx) scales output down.
    assert rules.theoretical_output(ELEVEN_PLUS_ELEVEN, working_days=3) == round(144 * 3 / 5)


def test_output_prorated_by_six_day_week():
    # Istanbul-style 6-day plant: a "60 pieces" cadence at 3 of 6 days yields 30.
    assert rules.theoretical_output(ONE_WORKER, working_days=3, full_week_days=6) == 30
    # A full 6-day week yields the full pieces_per_week.
    assert rules.theoretical_output(ONE_WORKER, working_days=6, full_week_days=6) == 60
    # 5 of 6 days on the 6-day plant is a genuine short week (not capped).
    assert rules.theoretical_output(ONE_WORKER, working_days=5, full_week_days=6) == round(60 * 5 / 6)


def test_zero_full_week_days_yields_zero():
    assert rules.theoretical_output(ONE_WORKER, working_days=3, full_week_days=0) == 0


def test_no_cadence_yields_zero():
    assert rules.theoretical_output(None, working_days=5) == 0


def test_zero_working_days_yields_zero():
    assert rules.theoretical_output(ONE_WORKER, working_days=0) == 0


# --- Capacity delta (R2.3, R2.4) ------------------------------------------


def test_capacity_delta_adds_to_expected():
    cell = CellInput(working_days=5, workers_assigned=1, capacity_delta=10, cadence=ONE_WORKER)
    result = rules.compute_cell(cell)
    assert result.expected_pieces == 60
    assert result.actual_output == 70


def test_negative_delta_reduces_output():
    cell = CellInput(working_days=5, workers_assigned=1, capacity_delta=-20, cadence=ONE_WORKER)
    assert rules.compute_cell(cell).actual_output == 40


def test_actual_output_floored_at_zero():
    cell = CellInput(working_days=5, workers_assigned=1, capacity_delta=-100, cadence=ONE_WORKER)
    assert rules.compute_cell(cell).actual_output == 0


# --- Approved combinations (R2.2) -----------------------------------------


def test_validate_cadence_choice_accepts_approved():
    approved = {1: ONE_WORKER, 2: ELEVEN_PLUS_ELEVEN}
    assert rules.validate_cadence_choice(2, approved) is ELEVEN_PLUS_ELEVEN


def test_validate_cadence_choice_rejects_unapproved():
    approved = {1: ONE_WORKER}
    with pytest.raises(RuleError) as exc:
        rules.validate_cadence_choice(99, approved)
    assert exc.value.code == "cadence_not_approved"


def test_validate_cadence_choice_allows_none():
    assert rules.validate_cadence_choice(None, {1: ONE_WORKER}) is None


def test_validate_workers_match_rejects_invented_staffing():
    with pytest.raises(RuleError) as exc:
        rules.validate_workers_match(ONE_WORKER, workers_assigned=3)
    assert exc.value.code == "workers_mismatch"


def test_validate_workers_match_accepts_correct_headcount():
    rules.validate_workers_match(ELEVEN_PLUS_ELEVEN, workers_assigned=22)  # no raise


# --- Workforce target (R3) ------------------------------------------------


def test_workforce_above_target():
    ev = rules.evaluate_workforce(target_workers=20, assigned_workers=25)
    assert ev.status == "above"
    assert ev.delta == 5


def test_workforce_below_target():
    ev = rules.evaluate_workforce(target_workers=20, assigned_workers=18)
    assert ev.status == "below"
    assert ev.delta == -2


def test_workforce_at_target():
    ev = rules.evaluate_workforce(target_workers=20, assigned_workers=20)
    assert ev.status == "at"
    assert ev.delta == 0


# --- Combined/linked lines (R4, Linee_Collegate) --------------------------


def test_linked_slave_deducts_master_output():
    # Master and Slave share output: the master's pieces are deducted from the slave.
    assert rules.linked_slave_output(slave_expected=144, master_expected=100, adjustment=0) == 44


def test_linked_slave_applies_adjustment_after_deduction():
    assert rules.linked_slave_output(slave_expected=144, master_expected=100, adjustment=10) == 54


def test_linked_slave_without_active_master_stands_alone():
    # When the master is not producing, the slave keeps its own output (+ adj).
    assert rules.linked_slave_output(slave_expected=100, master_expected=0, adjustment=5) == 105


def test_linked_slave_floored_at_zero():
    # A master that out-produces the slave floors the slave at zero, not negative.
    assert rules.linked_slave_output(slave_expected=60, master_expected=144, adjustment=0) == 0


# --- Regional aggregation (R8.2) ------------------------------------------


def test_regional_aggregate_sums_across_plants():
    total = rules.aggregate_regional({"Limana": 100, "Casale": 80, "Bradford": 20})
    assert total == 200


# --- Configurable special rules (R4.2, R13.2) -----------------------------


def test_special_rule_cap_clamps_output():
    r = rules.SpecialRule(name="cap", rule_type="cap", params={"max": 100})
    assert rules.apply_special_rules(150, [r]) == 100
    assert rules.apply_special_rules(80, [r]) == 80


def test_special_rule_floor_raises_output():
    r = rules.SpecialRule(name="floor", rule_type="floor", params={"min": 50})
    assert rules.apply_special_rules(30, [r]) == 50
    assert rules.apply_special_rules(90, [r]) == 90


def test_special_rule_scale_multiplies_output():
    r = rules.SpecialRule(name="half", rule_type="scale", params={"factor": 0.5})
    assert rules.apply_special_rules(144, [r]) == 72


def test_special_rules_apply_in_order_and_floor_at_zero():
    scale = rules.SpecialRule(name="s", rule_type="scale", params={"factor": 0})
    assert rules.apply_special_rules(144, [scale]) == 0


def test_unknown_special_rule_is_ignored():
    r = rules.SpecialRule(name="x", rule_type="mystery", params={})
    assert rules.apply_special_rules(100, [r]) == 100


# --- Configurable KPIs (R13.3) --------------------------------------------


def test_aggregate_kpi_sum_avg_min_max():
    values = [100.0, 50.0, 30.0]
    assert rules.aggregate_kpi(values, "sum") == 180
    assert rules.aggregate_kpi(values, "avg") == 60.0
    assert rules.aggregate_kpi(values, "min") == 30
    assert rules.aggregate_kpi(values, "max") == 100


def test_aggregate_kpi_empty_is_zero():
    assert rules.aggregate_kpi([], "sum") == 0
    assert rules.aggregate_kpi([], "avg") == 0


def test_aggregate_kpi_rejects_unknown_aggregation():
    with pytest.raises(RuleError) as exc:
        rules.aggregate_kpi([1.0], "median")
    assert exc.value.code == "unknown_aggregation"
