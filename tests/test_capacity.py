"""Capacity calculations are separate from the Phase 1 material plan."""

from datetime import date, datetime

import pytest

from factoryflow.capacity import PRODUCTION_LINES, calculate_capacity_plan
from factoryflow.data import BOM, DEFAULT_DEMAND, DEMO_AS_OF, INVENTORY, RECEIPTS
from factoryflow.planning import calculate_plan


def make_capacity_plan(demand=None, production_start=date(2026, 12, 1),
                       target_completion=date(2026, 12, 4), lines=None):
    return {
        row["finished_sku"]: row
        for row in calculate_capacity_plan(
            DEFAULT_DEMAND if demand is None else demand,
            PRODUCTION_LINES if lines is None else lines,
            production_start,
            target_completion,
        )
    }


def test_fictional_lines_have_independent_daily_capacities():
    plan = make_capacity_plan()
    lamp = plan["FG-LAMP-01"]
    charger = plan["FG-CHARGER-02"]
    assert (lamp["daily_capacity"], charger["daily_capacity"]) == (80, 60)
    assert (lamp["required_working_days"], charger["required_working_days"]) == (3, 2)
    assert (lamp["projected_completion"], charger["projected_completion"]) == (
        date(2026, 12, 3), date(2026, 12, 2)
    )
    assert (lamp["available_capacity"], charger["available_capacity"]) == (320, 240)
    assert all(row["capacity_shortage"] == 0 for row in plan.values())


def test_weekend_inside_window_adds_no_capacity():
    lamp = make_capacity_plan(
        demand={"FG-LAMP-01": 200},
        production_start=date(2026, 11, 27),  # Friday
        target_completion=date(2026, 11, 30),  # Monday
    )["FG-LAMP-01"]
    assert lamp["window_working_days"] == 2
    assert lamp["available_capacity"] == 160
    assert lamp["required_working_days"] == 3
    assert lamp["projected_completion"] == date(2026, 12, 1)
    assert lamp["capacity_shortage"] == 40
    assert lamp["capacity_status"] == "Potentially late"


def test_weekend_start_moves_first_production_to_monday():
    lamp = make_capacity_plan(
        demand={"FG-LAMP-01": 60},
        production_start=date(2026, 11, 28),  # Saturday
        target_completion=date(2026, 11, 29),  # Sunday
    )["FG-LAMP-01"]
    assert lamp["first_production_date"] == date(2026, 11, 30)
    assert lamp["window_working_days"] == 0
    assert lamp["available_capacity"] == 0
    assert lamp["capacity_shortage"] == 60
    assert lamp["projected_completion"] == date(2026, 11, 30)


def test_exact_capacity_finishes_on_target_date():
    charger = make_capacity_plan(
        demand={"FG-CHARGER-02": 120},
        production_start=date(2026, 12, 3),
        target_completion=date(2026, 12, 4),
    )["FG-CHARGER-02"]
    assert charger["required_working_days"] == 2
    assert charger["available_capacity"] == 120
    assert charger["capacity_shortage"] == 0
    assert charger["projected_completion"] == date(2026, 12, 4)
    assert charger["capacity_status"] == "Within capacity"


def test_zero_demand_requires_no_production_even_without_workdays():
    plan = make_capacity_plan(
        demand={"FG-LAMP-01": 0, "FG-CHARGER-02": 0},
        production_start=date(2026, 11, 28),
        target_completion=date(2026, 11, 29),
    )
    for row in plan.values():
        assert row["required_working_days"] == 0
        assert row["first_production_date"] is None
        assert row["projected_completion"] is None
        assert row["available_capacity"] == 0
        assert row["capacity_shortage"] == 0
        assert row["capacity_status"] == "Within capacity"


@pytest.mark.parametrize("start,end", [
    (date(2026, 12, 5), date(2026, 12, 4)),
    ("2026-12-01", date(2026, 12, 4)),
    (date(2026, 12, 1), None),
    (datetime(2026, 12, 1), date(2026, 12, 4)),
])
def test_invalid_dates_are_rejected(start, end):
    with pytest.raises(ValueError, match="date|earlier"):
        make_capacity_plan(production_start=start, target_completion=end)


@pytest.mark.parametrize("capacity", [0, -1, 2.5, True])
def test_invalid_daily_capacity_is_rejected(capacity):
    lines = [dict(PRODUCTION_LINES[0], daily_capacity=capacity)]
    with pytest.raises(ValueError, match="Daily capacity"):
        make_capacity_plan(demand={"FG-LAMP-01": 1}, lines=lines)


def test_unknown_product_cannot_be_planned_on_an_unrelated_line():
    with pytest.raises(ValueError, match="No production line"):
        make_capacity_plan(demand={"UNKNOWN": 1})


def test_capacity_result_does_not_hide_material_shortages():
    capacity = make_capacity_plan()
    materials = calculate_plan(
        demand=DEFAULT_DEMAND,
        bom=BOM,
        inventory=INVENTORY,
        receipts=RECEIPTS,
        as_of=DEMO_AS_OF,
        production_date=date(2026, 12, 1),
    )
    assert all(row["capacity_shortage"] == 0 for row in capacity.values())
    assert {row["sku"] for row in materials if row["net_shortage"] > 0} == {
        "LED-100", "SCR-120", "ADP-130"
    }
