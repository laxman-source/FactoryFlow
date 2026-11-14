"""Component stock is consumed once, on the day it is actually needed."""

from datetime import date

import pytest

from factoryflow.data import DEMO_AS_OF, INVENTORY, RECEIPTS
from factoryflow.material_timeline import calculate_material_timeline


SNAPSHOT = date(2026, 11, 26)  # Thursday
FRIDAY = date(2026, 11, 27)
SATURDAY = date(2026, 11, 28)
SUNDAY = date(2026, 11, 29)
MONDAY = date(2026, 11, 30)


def stock(on_hand=10, reserved=0, safety_stock=0):
    return [{
        "sku": "SCR-120", "name": "Assembly screws", "on_hand": on_hand,
        "reserved": reserved, "safety_stock": safety_stock,
    }]


def need(day, qty, product="FG-LAMP-01"):
    return {"date": day, "component_sku": "SCR-120", "qty": qty,
            "finished_sku": product}


def receipt(day, qty, **options):
    return {"component_sku": "SCR-120", "due_date": day, "qty": qty,
            **options}


def timeline(*, inventory=None, receipts=None, requirements=None, end_date=MONDAY):
    return calculate_material_timeline(
        stock() if inventory is None else inventory,
        [] if receipts is None else receipts,
        [] if requirements is None else requirements,
        SNAPSHOT, end_date,
    )


def row(rows, day):
    return next(item for item in rows if item["date"] == day)


def test_opening_material_is_available_before_production():
    rows = timeline(requirements=[need(FRIDAY, 7)])
    assert (row(rows, SNAPSHOT)["opening_balance"], row(rows, SNAPSHOT)["closing_balance"]) == (10, 10)
    assert (row(rows, FRIDAY)["consumption"], row(rows, FRIDAY)["closing_balance"]) == (7, 3)


def test_receipt_on_requirement_date_is_available_first():
    day = row(timeline(inventory=stock(2), receipts=[receipt(FRIDAY, 5)],
                       requirements=[need(FRIDAY, 7)]), FRIDAY)
    assert (day["opening_balance"], day["receipts"], day["consumption"],
            day["unmet_need"], day["closing_balance"]) == (2, 5, 7, 0, 0)


def test_late_receipt_does_not_erase_earlier_unmet_need():
    rows = timeline(inventory=stock(2), receipts=[receipt(MONDAY, 5)],
                    requirements=[need(FRIDAY, 7)])
    assert (row(rows, FRIDAY)["consumption"], row(rows, FRIDAY)["unmet_need"]) == (2, 5)
    assert (row(rows, MONDAY)["receipts"], row(rows, MONDAY)["closing_balance"]) == (5, 5)


def test_insufficient_components_are_capped_at_available_stock():
    day = row(timeline(inventory=stock(4), requirements=[need(FRIDAY, 9)]), FRIDAY)
    assert (day["requirement"], day["consumption"], day["unmet_need"],
            day["closing_balance"]) == (9, 4, 5, 0)


def test_shared_components_from_two_products_use_one_stock_pool():
    rows = timeline(inventory=stock(8), requirements=[
        need(FRIDAY, 6, "FG-LAMP-01"), need(FRIDAY, 5, "FG-CHARGER-02"),
        need(MONDAY, 3, "FG-CHARGER-02"),
    ])
    assert (row(rows, FRIDAY)["requirement"], row(rows, FRIDAY)["consumption"],
            row(rows, FRIDAY)["unmet_need"]) == (11, 8, 3)
    assert (row(rows, MONDAY)["opening_balance"], row(rows, MONDAY)["unmet_need"]) == (0, 3)


def test_zero_requirements_leave_stock_and_receipts_available():
    rows = timeline(receipts=[receipt(FRIDAY, 3)], requirements=[need(FRIDAY, 0)])
    assert row(rows, FRIDAY)["closing_balance"] == 13
    assert all(day["consumption"] == day["unmet_need"] == 0 for day in rows)
    assert row(rows, MONDAY)["closing_balance"] == 13


def test_reserved_and_safety_stock_are_deducted_once_at_snapshot():
    rows = timeline(inventory=stock(20, reserved=4, safety_stock=6),
                    receipts=[receipt(MONDAY, 5)],
                    requirements=[need(FRIDAY, 7), need(MONDAY, 6)])
    assert row(rows, SNAPSHOT)["opening_balance"] == 10
    assert row(rows, FRIDAY)["closing_balance"] == 3
    assert (row(rows, MONDAY)["opening_balance"], row(rows, MONDAY)["receipts"],
            row(rows, MONDAY)["consumption"], row(rows, MONDAY)["closing_balance"]) == (3, 5, 6, 2)


def test_multiple_receipts_for_same_component_and_date_are_added():
    day = row(timeline(inventory=stock(0), receipts=[receipt(FRIDAY, 3), receipt(FRIDAY, 4)],
                       requirements=[need(FRIDAY, 8)]), FRIDAY)
    assert (day["receipts"], day["consumption"], day["unmet_need"]) == (7, 7, 1)


def test_weekend_receipt_is_available_on_weekend_and_following_monday():
    rows = timeline(inventory=stock(0), receipts=[receipt(SATURDAY, 6)],
                    requirements=[need(FRIDAY, 2), need(SUNDAY, 4), need(MONDAY, 2)])
    assert row(rows, FRIDAY)["unmet_need"] == 2
    assert (row(rows, SATURDAY)["receipts"], row(rows, SATURDAY)["closing_balance"]) == (6, 6)
    assert row(rows, SUNDAY)["closing_balance"] == 2
    assert (row(rows, MONDAY)["consumption"], row(rows, MONDAY)["closing_balance"]) == (2, 0)


def test_balances_never_go_negative_even_when_protected_stock_exceeds_free_stock():
    rows = timeline(inventory=stock(5, reserved=3, safety_stock=9),
                    requirements=[need(FRIDAY, 20), need(MONDAY, 10)])
    assert all(day["opening_balance"] >= 0 and day["closing_balance"] >= 0 for day in rows)
    assert row(rows, FRIDAY)["unmet_need"] == 20
    assert row(rows, MONDAY)["unmet_need"] == 10


def test_unconfirmed_receipts_and_snapshot_receipts_are_not_added():
    rows = timeline(inventory=stock(0), receipts=[
        receipt(SNAPSHOT, 10), receipt(FRIDAY, 20, confirmed=False),
        receipt(MONDAY, 3, confirmed=True),
    ], requirements=[need(FRIDAY, 2)])
    assert row(rows, FRIDAY)["unmet_need"] == 2
    assert row(rows, MONDAY)["closing_balance"] == 3


@pytest.mark.parametrize("requirements", [
    [need(FRIDAY, -1)],
    [need(FRIDAY, True)],
    [need(date(2026, 12, 1), 1)],
    [{"date": "2026-11-27", "component_sku": "SCR-120", "qty": 1}],
    [{"date": FRIDAY, "component_sku": "UNKNOWN", "qty": 1}],
])
def test_invalid_daily_requirements_are_rejected(requirements):
    with pytest.raises(ValueError):
        timeline(requirements=requirements)


def test_duplicate_inventory_and_invalid_receipt_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        timeline(inventory=stock() + stock())
    with pytest.raises(ValueError, match="Receipt quantity"):
        timeline(receipts=[receipt(FRIDAY, -1)])


def test_existing_demo_stock_and_receipts_work_with_daily_component_needs():
    production_day = date(2026, 12, 1)
    rows = calculate_material_timeline(INVENTORY, RECEIPTS, [
        {"date": production_day, "component_sku": "SCR-120", "qty": 800,
         "finished_sku": "FG-LAMP-01"},
        {"date": production_day, "component_sku": "SCR-120", "qty": 200,
         "finished_sku": "FG-CHARGER-02"},
        {"date": production_day, "component_sku": "LED-100", "qty": 200,
         "finished_sku": "FG-LAMP-01"},
    ], DEMO_AS_OF, production_day)
    by_sku = {item["component_sku"]: item for item in rows
              if item["date"] == production_day}
    assert (by_sku["SCR-120"]["requirement"], by_sku["SCR-120"]["unmet_need"]) == (1000, 100)
    assert (by_sku["LED-100"]["opening_balance"], by_sku["LED-100"]["unmet_need"]) == (160, 40)
