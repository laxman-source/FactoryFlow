"""Reproducible Stage 3A overtime and machine downtime examples."""

from datetime import date, datetime

import pytest

from factoryflow.capacity import PRODUCTION_LINES, calculate_capacity_plan
from factoryflow.data import DEFAULT_DEMAND


def plan(demand=None, start=date(2026, 12, 1), end=date(2026, 12, 4),
         overtime=None, downtime=None):
    return {
        row["finished_sku"]: row
        for row in calculate_capacity_plan(
            DEFAULT_DEMAND if demand is None else demand,
            PRODUCTION_LINES,
            start,
            end,
            overtime_by_sku=overtime,
            downtime_by_sku=downtime,
        )
    }


def test_overtime_adds_units_to_each_operating_weekday():
    rows = plan(
        demand={"FG-LAMP-01": 350, "FG-CHARGER-02": 150},
        overtime={"FG-LAMP-01": 20, "FG-CHARGER-02": 10},
    )
    lamp, charger = rows["FG-LAMP-01"], rows["FG-CHARGER-02"]
    assert (lamp["daily_capacity"], lamp["overtime_units_per_day"], lamp["operating_daily_capacity"]) == (80, 20, 100)
    assert (lamp["available_capacity"], lamp["capacity_shortage"]) == (400, 0)
    assert (lamp["required_working_days"], lamp["projected_completion"]) == (4, date(2026, 12, 4))
    assert (charger["available_capacity"], charger["capacity_shortage"]) == (280, 0)
    assert (charger["required_working_days"], charger["projected_completion"]) == (3, date(2026, 12, 3))


def test_overtime_does_not_add_weekend_capacity():
    lamp = plan(
        demand={"FG-LAMP-01": 250},
        start=date(2026, 11, 27),  # Friday
        end=date(2026, 11, 30),  # Monday
        overtime={"FG-LAMP-01": 20},
    )["FG-LAMP-01"]
    assert lamp["window_working_days"] == 2
    assert lamp["available_capacity"] == 200
    assert lamp["capacity_shortage"] == 50
    assert lamp["projected_completion"] == date(2026, 12, 1)


def test_line_specific_downtime_reduces_capacity_and_delays_completion():
    rows = plan(
        demand={"FG-LAMP-01": 260, "FG-CHARGER-02": 100},
        downtime={"FG-LAMP-01": [date(2026, 12, 2)]},
    )
    lamp, charger = rows["FG-LAMP-01"], rows["FG-CHARGER-02"]
    assert (lamp["downtime_days_in_window"], lamp["operating_working_days"]) == (1, 3)
    assert (lamp["available_capacity"], lamp["capacity_shortage"]) == (240, 20)
    assert lamp["projected_completion"] == date(2026, 12, 7)  # Weekend follows Friday.
    assert (charger["downtime_days_in_window"], charger["available_capacity"]) == (0, 240)
    assert charger["projected_completion"] == date(2026, 12, 2)


def test_downtime_overrides_overtime_on_the_same_day():
    lamp = plan(
        demand={"FG-LAMP-01": 150},
        start=date(2026, 12, 1),
        end=date(2026, 12, 2),
        overtime={"FG-LAMP-01": 20},
        downtime={"FG-LAMP-01": [date(2026, 12, 2)]},
    )["FG-LAMP-01"]
    assert lamp["operating_daily_capacity"] == 100
    assert lamp["operating_working_days"] == 1
    assert lamp["available_capacity"] == 100  # No normal or overtime output on Dec 2.
    assert lamp["capacity_shortage"] == 50
    assert lamp["projected_completion"] == date(2026, 12, 3)


def test_overtime_and_downtime_together_can_cover_demand():
    lamp = plan(
        demand={"FG-LAMP-01": 250},
        overtime={"FG-LAMP-01": 20},
        downtime={"FG-LAMP-01": [date(2026, 12, 2)]},
    )["FG-LAMP-01"]
    assert (lamp["required_working_days"], lamp["operating_working_days"]) == (3, 3)
    assert (lamp["available_capacity"], lamp["capacity_shortage"]) == (300, 0)
    assert lamp["projected_completion"] == date(2026, 12, 4)


def test_downtime_after_target_still_affects_late_projection():
    lamp = plan(
        demand={"FG-LAMP-01": 200},
        end=date(2026, 12, 1),
        downtime={"FG-LAMP-01": [date(2026, 12, 2)]},
    )["FG-LAMP-01"]
    assert lamp["available_capacity"] == 80
    assert lamp["capacity_shortage"] == 120
    assert lamp["projected_completion"] == date(2026, 12, 4)


def test_downtime_on_first_day_shifts_actual_start():
    lamp = plan(
        demand={"FG-LAMP-01": 1},
        downtime={"FG-LAMP-01": [date(2026, 12, 1)]},
    )["FG-LAMP-01"]
    assert lamp["first_production_date"] == date(2026, 12, 2)
    assert lamp["projected_completion"] == date(2026, 12, 2)


def test_weekend_downtime_adds_no_extra_loss():
    lamp = plan(
        demand={"FG-LAMP-01": 200},
        start=date(2026, 11, 27),
        end=date(2026, 11, 30),
        downtime={"FG-LAMP-01": [date(2026, 11, 28)]},
    )["FG-LAMP-01"]
    assert lamp["downtime_days_in_window"] == 0
    assert lamp["available_capacity"] == 160
    assert lamp["projected_completion"] == date(2026, 12, 1)


def test_zero_demand_stays_unscheduled_with_overtime_and_downtime():
    lamp = plan(
        demand={"FG-LAMP-01": 0},
        overtime={"FG-LAMP-01": 20},
        downtime={"FG-LAMP-01": [date(2026, 12, 1)]},
    )["FG-LAMP-01"]
    assert lamp["required_working_days"] == 0
    assert lamp["first_production_date"] is None
    assert lamp["projected_completion"] is None
    assert lamp["capacity_shortage"] == 0


@pytest.mark.parametrize("value", [-1, True, 2.5, "20"])
def test_invalid_overtime_is_rejected(value):
    with pytest.raises(ValueError, match="Overtime"):
        plan(overtime={"FG-LAMP-01": value})


@pytest.mark.parametrize("downtime", [
    {"FG-LAMP-01": [date(2026, 12, 2), date(2026, 12, 2)]},
    {"FG-LAMP-01": ["2026-12-02"]},
    {"FG-LAMP-01": [datetime(2026, 12, 2)]},
    {"FG-LAMP-01": "2026-12-02"},
])
def test_invalid_downtime_is_rejected(downtime):
    with pytest.raises(ValueError, match="downtime|Downtime"):
        plan(downtime=downtime)


@pytest.mark.parametrize("options", [
    {"overtime": {"UNKNOWN": 10}},
    {"downtime": {"UNKNOWN": [date(2026, 12, 2)]}},
    {"overtime": [10]},
    {"downtime": [date(2026, 12, 2)]},
])
def test_unknown_lines_and_malformed_options_are_rejected(options):
    with pytest.raises(ValueError, match="line|mapping"):
        plan(**options)


def test_disabled_options_preserve_stage_1_results():
    without_options = calculate_capacity_plan(
        DEFAULT_DEMAND, PRODUCTION_LINES, date(2026, 12, 1), date(2026, 12, 4)
    )
    empty_options = calculate_capacity_plan(
        DEFAULT_DEMAND, PRODUCTION_LINES, date(2026, 12, 1), date(2026, 12, 4),
        overtime_by_sku={}, downtime_by_sku={},
    )
    assert without_options == empty_options
    assert [(row["available_capacity"], row["projected_completion"]) for row in without_options] == [
        (320, date(2026, 12, 3)), (240, date(2026, 12, 2))
    ]
