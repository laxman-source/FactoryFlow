from datetime import date

import pytest

from factoryflow.data import (
    BOM, DEFAULT_DEMAND, DEMO_AS_OF, DEMO_PRODUCTION_DATE, INVENTORY, RECEIPTS,
)
from factoryflow.planning import calculate_plan


def make_plan(**overrides):
    arguments = dict(
        demand=DEFAULT_DEMAND,
        bom=BOM,
        inventory=INVENTORY,
        receipts=RECEIPTS,
        as_of=DEMO_AS_OF,
        production_date=DEMO_PRODUCTION_DATE,
    )
    arguments.update(overrides)
    return {item["sku"]: item for item in calculate_plan(**arguments)}


def test_led_shortage_accounts_for_on_time_receipt():
    result = make_plan()["LED-100"]
    assert result["gross_required"] == 200
    assert result["usable_stock"] == 120
    assert result["incoming_on_time"] == 40
    assert result["net_shortage"] == 40
    assert result["suggested_order_qty"] == 40


def test_shared_screws_are_aggregated_and_pack_rounded():
    screws = make_plan()["SCR-120"]
    assert screws["gross_required"] == 200 * 4 + 100 * 2
    assert screws["usable_stock"] == 900  # 100 held as safety stock
    assert screws["net_shortage"] == 100
    assert screws["suggested_order_qty"] == 200  # ordered in packs of 200


def test_late_receipt_not_counted_as_available():
    adapter = make_plan()["ADP-130"]
    assert adapter["incoming_on_time"] == 0
    assert adapter["incoming_late"] == 20
    assert adapter["net_shortage"] == 50


def test_on_time_receipt_can_cover_shortage():
    pcb = make_plan()["PCB-200"]
    assert pcb["gross_required"] == 100
    assert pcb["incoming_on_time"] == 20
    assert pcb["net_shortage"] == 0
    assert pcb["status"] == "Covered"


def test_supplier_delay_flags_expediting_risk():
    adapter = make_plan(extra_lead_days=15)["ADP-130"]
    assert adapter["status"] == "At risk: expedite"
    assert adapter["latest_order_date"] < DEMO_AS_OF


def test_zero_demand_has_no_purchase_recommendations():
    plan = make_plan(demand={"FG-LAMP-01": 0, "FG-CHARGER-02": 0})
    assert all(row["suggested_order_qty"] == 0 for row in plan.values())


def test_missing_inventory_raises_explanatory_error():
    with pytest.raises(ValueError, match="Missing inventory"):
        make_plan(inventory=[row for row in INVENTORY if row["sku"] != "LED-100"])


def test_unknown_finished_product_is_rejected():
    with pytest.raises(ValueError, match="No BOM defined"):
        make_plan(demand={"UNKNOWN-PRODUCT": 4})


def test_negative_demand_is_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        make_plan(demand={"FG-LAMP-01": -1})


def test_production_date_cannot_precede_snapshot():
    with pytest.raises(ValueError, match="earlier"):
        make_plan(production_date=date(2026, 11, 13))


def test_reserved_stock_reduces_usable_stock():
    inventory = [row.copy() for row in INVENTORY]
    next(row for row in inventory if row["sku"] == "LED-100")["reserved"] = 20
    led = make_plan(inventory=inventory)["LED-100"]
    assert led["usable_stock"] == 100
    assert led["net_shortage"] == 60


def test_incoming_arriving_on_snapshot_is_not_double_counted():
    receipts = list(RECEIPTS) + [
        {"component_sku": "LED-100", "qty": 999, "due_date": DEMO_AS_OF}
    ]
    assert make_plan(receipts=receipts)["LED-100"]["incoming_on_time"] == 40


def test_receipt_on_production_date_is_usable_but_next_day_is_late():
    receipts = [
        {"component_sku": "LED-100", "qty": 15, "due_date": DEMO_PRODUCTION_DATE},
        {"component_sku": "LED-100", "qty": 25, "due_date": date(2026, 12, 2)},
    ]
    led = make_plan(receipts=receipts)["LED-100"]
    assert led["incoming_on_time"] == 15
    assert led["incoming_late"] == 25
    assert led["net_shortage"] == 65
    assert led["suggested_order_qty"] == 80


def test_unconfirmed_receipt_does_not_cover_shortage_or_count_as_late():
    receipts = list(RECEIPTS) + [
        {"component_sku": "LED-100", "qty": 1000,
         "due_date": DEMO_PRODUCTION_DATE, "confirmed": False},
        {"component_sku": "ADP-130", "qty": 1000,
         "due_date": date(2026, 12, 3), "confirmed": False},
    ]
    plan = make_plan(receipts=receipts)
    assert plan["LED-100"]["incoming_on_time"] == 40
    assert plan["LED-100"]["net_shortage"] == 40
    assert plan["ADP-130"]["incoming_late"] == 20


def test_invalid_receipt_confirmation_is_rejected():
    receipts = list(RECEIPTS) + [
        {"component_sku": "LED-100", "qty": 10,
         "due_date": DEMO_PRODUCTION_DATE, "confirmed": "no"},
    ]
    with pytest.raises(ValueError, match="confirmation"):
        make_plan(receipts=receipts)


def test_safety_stock_cannot_make_usable_stock_negative():
    inventory = [row.copy() for row in INVENTORY]
    next(row for row in inventory if row["sku"] == "LED-100")["safety_stock"] = 200
    led = make_plan(inventory=inventory)["LED-100"]
    assert led["usable_stock"] == 0
    assert led["net_shortage"] == 160


def test_order_release_on_snapshot_date_is_still_on_time():
    inventory = [row.copy() for row in INVENTORY]
    next(row for row in inventory if row["sku"] == "LED-100")["lead_days"] = 17
    led = make_plan(inventory=inventory)["LED-100"]
    assert led["latest_order_date"] == DEMO_AS_OF
    assert led["status"] == "Order now"


def test_large_shortage_rounds_to_exact_supplier_multiple():
    # Division through float loses one unit at this otherwise valid integer.
    inventory = [dict(INVENTORY[0], on_hand=0, pack_size=2)]
    bom = [{"finished_sku": "FG-LAMP-01", "component_sku": "LED-100", "qty_per_unit": 1}]
    led = make_plan(
        demand={"FG-LAMP-01": 2**53 + 1},
        bom=bom,
        inventory=inventory,
        receipts=[],
    )["LED-100"]
    assert led["net_shortage"] == 2**53 + 1
    assert led["suggested_order_qty"] == 2**53 + 2
