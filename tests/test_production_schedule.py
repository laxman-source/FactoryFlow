"""Supply-constrained builds use complete BOM sets and dedicated line capacity."""

from datetime import date

import pytest

from factoryflow.data import BOM as DEMO_BOM, DEMO_AS_OF, INVENTORY as DEMO_INVENTORY, RECEIPTS as DEMO_RECEIPTS
from factoryflow.production_schedule import calculate_production_schedule


SNAPSHOT = date(2026, 11, 26)  # Thursday
FRIDAY = date(2026, 11, 27)
SATURDAY = date(2026, 11, 28)
MONDAY = date(2026, 11, 30)
LAMP = "FG-LAMP-01"
CHARGER = "FG-CHARGER-02"
LINES = [
    {"finished_sku": LAMP, "name": "Lamp line", "daily_capacity": 3},
    {"finished_sku": CHARGER, "name": "Charger line", "daily_capacity": 2},
]
BOM = [
    {"finished_sku": LAMP, "component_sku": "A", "qty_per_unit": 1},
    {"finished_sku": LAMP, "component_sku": "S", "qty_per_unit": 2},
    {"finished_sku": CHARGER, "component_sku": "B", "qty_per_unit": 1},
    {"finished_sku": CHARGER, "component_sku": "S", "qty_per_unit": 1},
]


def stock(a=10, b=10, shared=30, *, reserved=0, safety=0):
    return [
        {"sku": "A", "name": "Lamp part", "on_hand": a, "reserved": reserved, "safety_stock": safety},
        {"sku": "B", "name": "Charger part", "on_hand": b, "reserved": 0, "safety_stock": 0},
        {"sku": "S", "name": "Shared part", "on_hand": shared, "reserved": 0, "safety_stock": 0},
    ]


def receipt(day, sku, qty, **options):
    return {"due_date": day, "component_sku": sku, "qty": qty, **options}


def schedule(demand=None, *, inventory=None, receipts=None, start=FRIDAY, end=MONDAY,
             overtime=None, downtime=None):
    return calculate_production_schedule(
        {LAMP: 0, CHARGER: 0} if demand is None else demand,
        BOM, stock() if inventory is None else inventory,
        [] if receipts is None else receipts, SNAPSHOT, start, end,
        lines=LINES, overtime_by_sku=overtime, downtime_by_sku=downtime,
    )


def daily(result, day, sku):
    return next(row for row in result["daily_schedule"]
                if row["date"] == day and row["finished_sku"] == sku)


def summary(result, sku):
    return next(row for row in result["summary"]["by_product"]
                if row["finished_sku"] == sku)


def test_sufficient_materials_and_capacity_complete_both_products():
    result = schedule({LAMP: 4, CHARGER: 3}, inventory=stock(a=4, b=3, shared=11))
    assert (daily(result, FRIDAY, LAMP)["actual_buildable_units"],
            daily(result, FRIDAY, CHARGER)["actual_buildable_units"]) == (3, 2)
    assert (daily(result, MONDAY, LAMP)["actual_buildable_units"],
            daily(result, MONDAY, CHARGER)["actual_buildable_units"]) == (1, 1)
    assert (result["summary"]["total_demand"], result["summary"]["total_completed"],
            result["summary"]["total_remaining"]) == (7, 7, 0)
    assert result["summary"]["remaining_inventory"]["S"] == 0


def test_missing_material_limits_output_despite_free_line_capacity():
    result = schedule({LAMP: 3}, inventory=stock(a=2, shared=10))
    friday = daily(result, FRIDAY, LAMP)
    assert (friday["available_capacity"], friday["material_limit_units"],
            friday["actual_buildable_units"]) == (3, 2, 2)
    assert friday["components_consumed"] == {"A": 2, "S": 4}
    assert (summary(result, LAMP)["remaining_units"],
            summary(result, LAMP)["remaining_reasons"]) == (1, ["material"])


def test_capacity_limits_output_despite_sufficient_materials():
    result = schedule({LAMP: 7}, inventory=stock(a=10, shared=20))
    assert (daily(result, FRIDAY, LAMP)["actual_buildable_units"],
            daily(result, MONDAY, LAMP)["actual_buildable_units"]) == (3, 3)
    assert (summary(result, LAMP)["remaining_units"],
            summary(result, LAMP)["remaining_reasons"]) == (1, ["capacity"])


def test_late_component_receipt_starts_builds_on_next_working_day():
    result = schedule({LAMP: 3}, inventory=stock(a=1),
                      receipts=[receipt(SATURDAY, "A", 2)])
    assert daily(result, FRIDAY, LAMP)["actual_buildable_units"] == 1
    assert (daily(result, SATURDAY, LAMP)["available_capacity"],
            daily(result, SATURDAY, LAMP)["actual_buildable_units"]) == (0, 0)
    assert (daily(result, MONDAY, LAMP)["available_components"]["A"],
            daily(result, MONDAY, LAMP)["actual_buildable_units"]) == (2, 2)
    assert result["summary"]["complete"]


def test_same_day_confirmed_receipt_is_available_before_production():
    result = schedule({LAMP: 2}, inventory=stock(a=0),
                      receipts=[receipt(FRIDAY, "A", 2)], end=FRIDAY)
    assert daily(result, FRIDAY, LAMP)["actual_buildable_units"] == 2


def test_ascending_sku_priority_gives_scarce_shared_part_to_charger():
    result = schedule({LAMP: 2, CHARGER: 2},
                      inventory=stock(a=2, b=2, shared=3), end=FRIDAY)
    charger = daily(result, FRIDAY, CHARGER)
    lamp = daily(result, FRIDAY, LAMP)
    assert result["summary"]["priority_rule"] == "ascending finished SKU"
    assert charger["actual_buildable_units"] == 2
    assert lamp["available_components"]["S"] == 1
    assert lamp["actual_buildable_units"] == 0
    assert lamp["critical_components"] == ["S"]
    assert result["summary"]["remaining_inventory"]["S"] == 1


def test_partial_receipts_feed_shared_stock_once_across_three_days():
    # Hand calculation: usable S starts at 4 - 2 safety = 2. Receipts of
    # 3, 2, and 2 add seven; the unconfirmed ten never enter stock.
    # Chargers use 3 S; three lamps use 6 S, leaving zero.
    start = date(2026, 12, 1)
    middle = date(2026, 12, 2)
    end = date(2026, 12, 3)
    inventory = [
        {"sku": "A", "name": "Lamp part", "on_hand": 4, "reserved": 0, "safety_stock": 0},
        {"sku": "B", "name": "Charger part", "on_hand": 3, "reserved": 0, "safety_stock": 0},
        {"sku": "S", "name": "Shared part", "on_hand": 4, "reserved": 0, "safety_stock": 2},
    ]
    receipts = [
        receipt(start, "S", 3),
        receipt(middle, "S", 2),
        receipt(end, "S", 2),
        receipt(start, "S", 10, confirmed=False),
    ]
    result = calculate_production_schedule(
        {LAMP: 4, CHARGER: 3}, BOM, inventory, receipts,
        date(2026, 11, 30), start, end, lines=LINES,
    )

    # Each day gives chargers first claim on the shared part. S closes at
    # 1, 0, and 0; a fourth lamp remains unfinished despite free line capacity.
    assert [daily(result, day, CHARGER)["actual_buildable_units"]
            for day in (start, middle, end)] == [2, 1, 0]
    assert [daily(result, day, LAMP)["actual_buildable_units"]
            for day in (start, middle, end)] == [1, 1, 1]
    assert [daily(result, day, LAMP)["remaining_inventory"]["S"]
            for day in (start, middle, end)] == [1, 0, 0]
    assert [daily(result, day, LAMP)["remaining_inventory"]["A"]
            for day in (start, middle, end)] == [3, 2, 1]
    assert [daily(result, day, LAMP)["remaining_inventory"]["B"]
            for day in (start, middle, end)] == [1, 0, 0]
    assert (summary(result, CHARGER)["completed_units"],
            summary(result, LAMP)["completed_units"],
            summary(result, LAMP)["remaining_units"]) == (3, 3, 1)
    assert result["summary"]["remaining_inventory"] == {"A": 1, "B": 0, "S": 0}


def test_overtime_increases_actual_builds_when_materials_exist():
    normal = schedule({LAMP: 4}, end=FRIDAY)
    overtime = schedule({LAMP: 4}, end=FRIDAY, overtime={LAMP: 2})
    assert daily(normal, FRIDAY, LAMP)["actual_buildable_units"] == 3
    assert daily(overtime, FRIDAY, LAMP)["actual_buildable_units"] == 4
    assert summary(overtime, LAMP)["remaining_units"] == 0


def test_full_day_downtime_blocks_production_and_preserves_stock():
    result = schedule({LAMP: 3}, downtime={LAMP: [FRIDAY]})
    friday = daily(result, FRIDAY, LAMP)
    assert (friday["line_state"], friday["available_capacity"],
            friday["actual_buildable_units"]) == ("Downtime", 0, 0)
    assert friday["components_consumed"] == {}
    assert friday["remaining_inventory"]["A"] == 10
    assert daily(result, MONDAY, LAMP)["actual_buildable_units"] == 3


def test_atomic_bom_consumption_never_uses_parts_for_unbuilt_units():
    result = schedule({LAMP: 2}, inventory=stock(a=0, shared=20), end=FRIDAY)
    lamp = daily(result, FRIDAY, LAMP)
    assert lamp["actual_buildable_units"] == 0
    assert lamp["components_consumed"] == {}
    assert lamp["remaining_inventory"]["S"] == 20


def test_protected_stock_and_unconfirmed_receipts_cannot_support_builds():
    result = schedule({LAMP: 3}, inventory=stock(a=5, reserved=2, safety=2),
                      receipts=[receipt(FRIDAY, "A", 10, confirmed=False)], end=FRIDAY)
    assert daily(result, FRIDAY, LAMP)["actual_buildable_units"] == 1
    assert daily(result, FRIDAY, LAMP)["remaining_inventory"]["A"] == 0


def test_zero_demand_and_incomplete_demand_have_finite_summaries():
    zero = schedule()
    assert (zero["summary"]["total_completed"], zero["summary"]["total_remaining"]) == (0, 0)
    assert all(row["actual_buildable_units"] == 0 for row in zero["daily_schedule"])
    short = schedule({LAMP: 3}, inventory=stock(a=0), end=FRIDAY)
    assert summary(short, LAMP)["remaining_units"] == 3
    assert summary(short, LAMP)["remaining_reasons"] == ["material"]
    assert "projected_completion" not in short["summary"]


def test_receipt_after_window_cannot_complete_current_demand():
    result = schedule({LAMP: 2}, inventory=stock(a=0),
                      receipts=[receipt(date(2026, 12, 1), "A", 2)], end=MONDAY)
    assert summary(result, LAMP)["completed_units"] == 0
    assert summary(result, LAMP)["remaining_units"] == 2
    assert summary(result, LAMP)["remaining_reasons"] == ["material"]


def test_weekend_only_window_has_no_line_capacity():
    result = schedule({LAMP: 1}, start=SATURDAY, end=SATURDAY)
    assert daily(result, SATURDAY, LAMP)["line_state"] == "Weekend"
    assert daily(result, SATURDAY, LAMP)["actual_buildable_units"] == 0
    assert summary(result, LAMP)["remaining_reasons"] == ["capacity"]


def test_all_balances_and_build_counts_remain_nonnegative_whole_units():
    result = schedule({LAMP: 20, CHARGER: 20},
                      inventory=stock(a=1, b=1, shared=1),
                      receipts=[receipt(MONDAY, "S", 1)])
    for row in result["daily_schedule"]:
        assert isinstance(row["actual_buildable_units"], int)
        assert 0 <= row["actual_buildable_units"] <= row["planned_remaining_demand"]
        assert all(qty >= 0 for qty in row["remaining_inventory"].values())
    assert result["summary"]["total_completed"] <= result["summary"]["total_demand"]


def test_demo_data_expected_versus_actual_with_shared_screws():
    result = calculate_production_schedule(
        {LAMP: 200, CHARGER: 100}, DEMO_BOM, DEMO_INVENTORY, DEMO_RECEIPTS,
        DEMO_AS_OF, date(2026, 12, 1), date(2026, 12, 4),
    )
    assert (summary(result, CHARGER)["completed_units"],
            summary(result, LAMP)["completed_units"]) == (100, 160)
    assert result["summary"]["total_remaining"] == 40
    assert summary(result, LAMP)["remaining_reasons"] == ["material"]


@pytest.mark.parametrize("demand", [{LAMP: -1}, {LAMP: 1.5}, {LAMP: True}, {"UNKNOWN": 1}])
def test_invalid_demand_is_rejected(demand):
    with pytest.raises(ValueError):
        schedule(demand)


def test_missing_bom_and_inventory_are_rejected():
    with pytest.raises(ValueError, match="No BOM"):
        calculate_production_schedule({LAMP: 1}, [], stock(), [], SNAPSHOT, FRIDAY, FRIDAY, lines=LINES)
    with pytest.raises(ValueError, match="Missing inventory"):
        schedule({LAMP: 1}, inventory=stock()[1:])


def test_production_cannot_precede_inventory_snapshot():
    with pytest.raises(ValueError, match="earlier"):
        schedule({LAMP: 1}, start=date(2026, 11, 25))
