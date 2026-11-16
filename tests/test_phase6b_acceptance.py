"""Phase 6B.2 acceptance oracles from the fictional Phase 6B.1 case records.

Expected numbers below are the hand calculations in PHASE6B_ACCEPTANCE_SPEC.md.
These tests do not establish a manufacturer-approved planning policy.
"""

from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from factoryflow.capacity import calculate_capacity_plan
from factoryflow.ecn import BOMRevision, ECN, ECNChangeLine, ProductionLot, StockHold, approve_ecn
from factoryflow.ecn_planning import calculate_ecn_plan
from factoryflow.material_timeline import calculate_material_timeline
from factoryflow.planning import calculate_plan
from factoryflow.production_schedule import calculate_production_schedule


LAMP, CHARGER = "FG-LAMP-01", "FG-CHARGER-02"
NOV14, NOV30 = date(2026, 11, 14), date(2026, 11, 30)
D1, D2, D3, D4 = (date(2026, 12, n) for n in range(1, 5))


def stock(sku, qty, *, reserved=0, safety=0, lead=7, pack=5, name=None):
    return {"sku": sku, "name": name or sku, "on_hand": qty,
            "reserved": reserved, "safety_stock": safety,
            "lead_days": lead, "pack_size": pack}


def line(sku, capacity):
    return {"finished_sku": sku, "name": f"Fictional {sku} line",
            "daily_capacity": capacity}


def bom(sku, components):
    return [{"finished_sku": sku, "component_sku": part,
             "qty_per_unit": qty} for part, qty in components]


def receipt(sku, qty, day, confirmed=True):
    return {"component_sku": sku, "qty": qty, "due_date": day,
            "confirmed": confirmed}


def lamp_input(*, demand=8, start=D1, end=D4, old=8, lots=None, holds=()):
    base = bom(LAMP, (("LED-100", 1), ("HSG", 1), ("SCR", 4), ("ADP", 1)))
    revision_b = BOMRevision(LAMP, "B", (("LED-101", 1), ("HSG", 1),
                                             ("SCR", 4), ("ADP", 1)))
    inventory = [stock(sku, qty) for sku, qty in
                 (("LED-100", old), ("LED-101", 4), ("HSG", 8),
                  ("SCR", 32), ("ADP", 8))]
    draft = ECN("ECN-001", LAMP, "A", "B", D3,
                (ECNChangeLine("LED-100", "LED-101", 1, 1),), "hold")
    approved = approve_ecn(draft, approval_date=D2, effective_date=D3,
                           approved_by="Fictional engineer", base_bom=base,
                           proposed_revisions=[revision_b], inventory=inventory)
    if lots is None:
        lots = [ProductionLot("LAMP-NEW", LAMP, demand, NOV30)]
    args = ({LAMP: demand}, base, inventory, [], NOV30, start, end)
    kwargs = {"lines": [line(LAMP, 2)], "lots": lots,
              "proposed_revisions": [revision_b], "ecns": [approved],
              "stock_holds": list(holds)}
    return args, kwargs


def one_input(*, demand, capacity, start=D1, end=D1, physical,
              reserved=0, safety=0, lead=0, pack=1, receipts=()):
    inventory = [stock("MAT", physical, reserved=reserved, safety=safety,
                       lead=lead, pack=pack, name="Fictional material")]
    return ({LAMP: demand}, bom(LAMP, (("MAT", 1),)), inventory,
            list(receipts), NOV30, start, end), {"lines": [line(LAMP, capacity)]}


def rows_for(result, sku=LAMP):
    return [row for row in result["daily_schedule"] if row["finished_sku"] == sku]


def ledger_for(result, sku):
    return [row for row in result["stock_ledger"] if row["component_sku"] == sku]


def assert_ecn_conservation(result, inventory):
    """Reconcile usable and physical stock independently on every ledger date."""
    last_physical = {item["sku"]: item["on_hand"] for item in inventory}
    last_usable = {item["sku"]: max(0, item["on_hand"] - item["reserved"]
                                    - item["safety_stock"]) for item in inventory}
    for row in result["stock_ledger"]:
        sku = row["component_sku"]
        assert row["opening_usable"] == last_usable[sku]
        assert row["closing_usable"] == (row["opening_usable"]
                + row["confirmed_receipts"] - row["authorized_hold"]
                - row["simulated_use"])
        last_physical[sku] += row["confirmed_receipts"] - row["simulated_use"]
        assert row["closing_physical"] == last_physical[sku]
        assert row["closing_usable"] >= 0
        assert row["closing_physical"] >= 0
        last_usable[sku] = row["closing_usable"]
    assert result["summary"]["remaining_inventory"] == last_usable
    assert result["summary"]["physical_inventory"] == last_physical


def assert_demand_balance(result, demand):
    summary = result["summary"]
    assert summary["total_demand"] == sum(demand.values())
    assert summary["total_demand"] == (summary["total_completed"]
                                       + summary["total_remaining"])
    for product in summary["by_product"]:
        assert product["demand"] == (product["completed_units"]
                                     + product["remaining_units"])
        assert product["completed_units"] >= 0
        assert product["remaining_units"] >= 0
    assert all(0 <= row["actual_buildable_units"] <= row["available_capacity"]
               for row in result["daily_schedule"])


def assert_legacy_conservation(result, inventory, receipts, as_of):
    """Check the final product turn's stock against input supply and all use."""
    balances = {item["sku"]: item["on_hand"] - item["reserved"]
                - item["safety_stock"] for item in inventory}
    dates = sorted({row["date"] for row in result["daily_schedule"]})
    for day in dates:
        for received in receipts:
            if (received["due_date"] == day and day > as_of
                    and received["confirmed"]):
                balances[received["component_sku"]] += received["qty"]
        for row in (r for r in result["daily_schedule"] if r["date"] == day):
            for sku, qty in row["components_consumed"].items():
                balances[sku] -= qty
            assert row["remaining_inventory"] == balances
            assert all(value >= 0 for value in balances.values())
    assert result["summary"]["remaining_inventory"] == balances


def test_ac02_approved_change_uses_production_date_and_separate_led_stock():
    args, kwargs = lamp_input()
    result = calculate_ecn_plan(*args, **kwargs)
    daily = rows_for(result)
    assert [(r["date"], r["bom_revision"], r["actual_buildable_units"])
            for r in daily] == [(D1, "A", 2), (D2, "A", 2),
                               (D3, "B", 2), (D4, "B", 2)]
    assert [(r["date"], r["bom_revision"], r["simulated_units"])
            for r in result["revision_trace"]] == [
                (D1, "A", 2), (D2, "A", 2), (D3, "B", 2), (D4, "B", 2)]
    assert [r["components_consumed"] for r in daily] == [
        {"LED-100": 2, "HSG": 2, "SCR": 8, "ADP": 2}] * 2 + [
        {"LED-101": 2, "HSG": 2, "SCR": 8, "ADP": 2}] * 2
    assert result["summary"]["remaining_inventory"] == {
        "LED-100": 4, "LED-101": 0, "HSG": 0, "SCR": 0, "ADP": 0}
    assert (result["summary"]["total_completed"], result["summary"]["total_remaining"]) == (8, 0)
    assert_demand_balance(result, args[0])
    assert_ecn_conservation(result, args[2])


def test_ac03_partial_receipts_and_unconfirmed_supply():
    args, kwargs = one_input(demand=5, capacity=2, end=D3, physical=0,
        receipts=(receipt("MAT", 1, D1), receipt("MAT", 2, D2),
                  receipt("MAT", 2, D3), receipt("MAT", 10, D1, False)))
    timeline = calculate_material_timeline(args[2], args[3], [], NOV30, D3)
    assert [(r["date"], r["receipts"]) for r in timeline if r["date"] >= D1] == [
        (D1, 1), (D2, 2), (D3, 2)]
    result = calculate_production_schedule(*args, **kwargs)
    assert [r["actual_buildable_units"] for r in rows_for(result)] == [1, 2, 2]
    assert [r["components_consumed"] for r in rows_for(result)] == [
        {"MAT": 1}, {"MAT": 2}, {"MAT": 2}]
    assert [r["remaining_inventory"]["MAT"] for r in rows_for(result)] == [0, 0, 0]
    assert result["summary"]["remaining_inventory"] == {"MAT": 0}
    assert_demand_balance(result, args[0])
    assert_legacy_conservation(result, args[2], args[3], NOV30)


def test_ac04_late_receipt_does_not_recover_earlier_capacity():
    args, kwargs = one_input(demand=4, capacity=2, end=D2, physical=0,
                             receipts=(receipt("MAT", 4, D2),))
    result = calculate_production_schedule(*args, **kwargs)
    daily = rows_for(result)
    assert [(r["date"], r["actual_buildable_units"], r["unfinished_demand"],
             r["remaining_inventory"]["MAT"]) for r in daily] == [
                (D1, 0, 4, 0), (D2, 2, 2, 2)]
    assert [r["components_consumed"] for r in daily] == [{}, {"MAT": 2}]
    assert (result["summary"]["total_completed"], result["summary"]["total_remaining"]) == (2, 2)
    assert_demand_balance(result, args[0])
    assert_legacy_conservation(result, args[2], args[3], NOV30)


def test_ac05_shared_screws_go_to_charger_once():
    demand = {CHARGER: 2, LAMP: 2}
    base = bom(CHARGER, (("SCR", 2),)) + bom(LAMP, (("SCR", 4),))
    inventory = [stock("SCR", 6, reserved=0, safety=0, lead=5,
                       pack=1, name="Fictional screws")]
    lots = [ProductionLot("CHG-NEW", CHARGER, 2, NOV30),
            ProductionLot("LAMP-NEW", LAMP, 2, NOV30)]
    result = calculate_ecn_plan(demand, base, inventory, [], NOV30, D1, D1,
        lines=[line(CHARGER, 2), line(LAMP, 2)], lots=lots)
    assert [(r["finished_sku"], r["actual_buildable_units"], r["components_consumed"])
            for r in result["daily_schedule"]] == [
                (CHARGER, 2, {"SCR": 4}), (LAMP, 0, {})]
    assert result["summary"]["remaining_inventory"] == {"SCR": 2}
    assert (result["summary"]["total_completed"], result["summary"]["total_remaining"]) == (2, 2)
    assert [r["simulated_use"] for r in ledger_for(result, "SCR") if r["date"] == D1] == [4]
    assert_demand_balance(result, demand)
    assert_ecn_conservation(result, inventory)


def test_ac06_wip_requires_review_without_component_issue():
    wip = [ProductionLot("WIP-LAMP", LAMP, 4, NOV30, "wip", "A")]
    args, kwargs = lamp_input(demand=4, start=D3, lots=wip)
    result = calculate_ecn_plan(*args, **kwargs)
    assert [(r["date"], r["bom_revision"], r["available_capacity"],
             r["actual_buildable_units"], r["blocked_wip_units"])
            for r in rows_for(result)] == [
                (D3, "B", 2, 0, 4), (D4, "B", 2, 0, 4)]
    assert [(r["simulated_units"], r["bom_revision"], r["review_required"])
            for r in result["revision_trace"]] == [(0, None, True)] * 2
    assert (result["summary"]["total_remaining"],
            result["summary"]["review_required_units"]) == (4, 4)
    assert result["summary"]["remaining_inventory"]["LED-100"] == 8
    assert result["summary"]["remaining_inventory"]["LED-101"] == 4
    assert all(row["simulated_use"] == 0 for row in result["stock_ledger"])
    assert_demand_balance(result, args[0])
    assert_ecn_conservation(result, args[2])


def test_ac07_downtime_overrides_overtime():
    args, kwargs = one_input(demand=6, capacity=2, end=D2, physical=6)
    options = {"overtime_by_sku": {LAMP: 1}, "downtime_by_sku": {LAMP: [D1]}}
    capacity = calculate_capacity_plan(args[0], kwargs["lines"], D1, D2, **options)[0]
    assert (capacity["available_capacity"], capacity["capacity_shortage"],
            capacity["projected_completion"]) == (3, 3, D3)
    result = calculate_production_schedule(*args, **kwargs, **options)
    assert [(r["date"], r["available_capacity"], r["actual_buildable_units"],
             r["remaining_inventory"]["MAT"]) for r in rows_for(result)] == [
                (D1, 0, 0, 6), (D2, 3, 3, 3)]
    assert (result["summary"]["total_completed"], result["summary"]["total_remaining"]) == (3, 3)
    assert_demand_balance(result, args[0])
    assert_legacy_conservation(result, args[2], args[3], NOV30)


def test_ac08_protected_stock_and_authorized_hold_reconcile():
    args, kwargs = one_input(demand=5, capacity=5, physical=10,
                             reserved=2, safety=2)
    hold = StockHold("MAT", 2, D1, "Fictional stock approver", NOV30)
    result = calculate_ecn_plan(*args, **kwargs, stock_holds=[hold])
    row = next(r for r in ledger_for(result, "MAT") if r["date"] == D1)
    assert (row["opening_usable"], row["authorized_hold"], row["simulated_use"],
            row["closing_usable"], row["closing_physical"], row["closing_held"]) == (6, 2, 4, 0, 6, 2)
    assert (result["summary"]["total_completed"], result["summary"]["total_remaining"]) == (4, 1)
    assert rows_for(result)[0]["components_consumed"] == {"MAT": 4}
    assert_demand_balance(result, args[0])
    assert_ecn_conservation(result, args[2])


def test_ac08_invalid_holds_fail_closed():
    args, kwargs = one_input(demand=5, capacity=5, physical=10,
                             reserved=2, safety=2)
    with pytest.raises(ValueError, match="Hold authorization cannot follow"):
        StockHold("MAT", 2, D1, "Fictional stock approver", D2)
    oversized = StockHold("MAT", 7, D1, "Fictional stock approver", NOV30)
    with pytest.raises(ValueError, match="Stock hold exceeds usable"):
        calculate_ecn_plan(*args, **kwargs, stock_holds=[oversized])


def test_ac09_same_product_ready_lots_fail_closed_without_dispatch_rule():
    args, kwargs = one_input(demand=4, capacity=3, physical=4)
    lots = [ProductionLot("L1", LAMP, 2, NOV30),
            ProductionLot("L2", LAMP, 2, NOV30)]
    with pytest.raises(ValueError, match="lot dispatch|ready lots"):
        calculate_ecn_plan(*args, **kwargs, lots=lots)
    assert args[2][0]["on_hand"] == 4  # A rejected projection has no stock posting.


def test_ac10_pack_only_mrp_advice_has_no_moq_rule_or_receipt():
    inventory = [stock("MAT", 3, lead=7, pack=5, name="Fictional material")]
    result = calculate_plan({LAMP: 11}, bom(LAMP, (("MAT", 1),)), inventory,
                            [], D1, date(2026, 12, 10))
    assert len(result) == 1
    row = result[0]
    assert (row["gross_required"], row["usable_stock"], row["incoming_on_time"],
            row["net_shortage"], row["suggested_order_qty"],
            row["latest_order_date"]) == (11, 3, 0, 8, 10, D3)
    assert "moq" not in row and "confirmed_receipt" not in row
    assert inventory[0]["on_hand"] == 3


def test_ac11_old_stock_hold_retains_physical_units():
    hold = StockHold("LED-100", 8, D3, "Fictional stock approver", D2)
    args, kwargs = lamp_input(old=12, holds=(hold,))
    result = calculate_ecn_plan(*args, **kwargs)
    assert [r["actual_buildable_units"] for r in rows_for(result)] == [2, 2, 2, 2]
    assert [r["bom_revision"] for r in rows_for(result)] == ["A", "A", "B", "B"]
    old = next(r for r in ledger_for(result, "LED-100") if r["date"] == D4)
    assert (old["closing_usable"], old["closing_physical"], old["closing_held"]) == (0, 8, 8)
    assert result["summary"]["remaining_inventory"]["LED-101"] == 0
    assert [(r["date"], r["simulated_use"], r["authorized_hold"])
            for r in ledger_for(result, "LED-100") if r["date"] >= D1] == [
                (D1, 2, 0), (D2, 2, 0), (D3, 0, 8), (D4, 0, 0)]
    assert result["disposition_review"][0]["automatic_stock_change"] is False
    assert_demand_balance(result, args[0])
    assert_ecn_conservation(result, args[2])


def test_ac12_simulated_plan_does_not_claim_actual_output():
    args, kwargs = one_input(demand=4, capacity=2, end=D2, physical=4)
    result = calculate_production_schedule(*args, **kwargs)
    assert [r["actual_buildable_units"] for r in rows_for(result)] == [2, 2]
    assert result["summary"]["remaining_inventory"] == {"MAT": 0}
    assert (result["summary"]["total_completed"], result["summary"]["total_remaining"]) == (4, 0)
    assert "actual_completed" not in result["summary"]
    assert_demand_balance(result, args[0])
    assert_legacy_conservation(result, args[2], args[3], NOV30)
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py", default_timeout=30).run()
    assert not app.exception
    assert any("SIMULATION ONLY" in item.value for item in app.warning)
    assert any(item.label == "Simulated buildable units" for item in app.metric)


def test_ac13_revision_crossing_backlog_is_separate_from_nominal_advice():
    demand = {LAMP: 200, CHARGER: 100}
    base = bom(LAMP, (("LED-100", 1), ("LAM-HSG-110", 1),
                      ("SCR-120", 4), ("ADP-130", 1))) + bom(
        CHARGER, (("PCB-200", 1), ("CHG-HSG-210", 1),
                  ("SCR-120", 2), ("USB-220", 1)))
    revision_b = BOMRevision(LAMP, "B", (("LED-101", 1), ("LAM-HSG-110", 1),
                ("SCR-120", 4), ("ADP-130", 1)))
    inventory = [stock(sku, qty, safety=safety, lead=lead, pack=pack)
                 for sku, qty, safety, lead, pack in (
                     ("LED-100", 120, 0, 7, 20), ("LED-101", 0, 0, 7, 5),
                     ("LAM-HSG-110", 240, 0, 5, 10), ("SCR-120", 1000, 100, 5, 200),
                     ("ADP-130", 150, 0, 12, 25), ("PCB-200", 90, 0, 10, 10),
                     ("CHG-HSG-210", 110, 0, 6, 10), ("USB-220", 60, 0, 6, 10))]
    receipts = [receipt("LED-100", 40, date(2026, 11, 27)),
                receipt("PCB-200", 20, date(2026, 11, 25)),
                receipt("USB-220", 50, NOV30), receipt("ADP-130", 20, D3)]
    draft = ECN("ECN-001", LAMP, "A", "B", D3,
                (ECNChangeLine("LED-100", "LED-101", 1, 1),), "hold")
    approved = approve_ecn(draft, approval_date=D2, effective_date=D3,
                           approved_by="Fictional engineer", base_bom=base,
                           proposed_revisions=[revision_b], inventory=inventory)
    lots = [ProductionLot("LAMP-NEW", LAMP, 200, NOV14),
            ProductionLot("CHG-NEW", CHARGER, 100, NOV14)]
    result = calculate_ecn_plan(demand, base, inventory, receipts, NOV14, D1, D4,
        lines=[line(LAMP, 80), line(CHARGER, 60)], lots=lots,
        proposed_revisions=[revision_b], ecns=[approved])
    assert [(r["date"], r["finished_sku"], r["bom_revision"],
             r["actual_buildable_units"]) for r in result["daily_schedule"]] == [
                (D1, CHARGER, "A", 60), (D1, LAMP, "A", 80),
                (D2, CHARGER, "A", 40), (D2, LAMP, "A", 70),
                (D3, CHARGER, "A", 0), (D3, LAMP, "B", 0),
                (D4, CHARGER, "A", 0), (D4, LAMP, "B", 0)]
    assert [(r["date"], r["simulated_use"]) for r in ledger_for(result, "SCR-120")
            if r["date"] >= D1] == [(D1, 440), (D2, 360), (D3, 0), (D4, 0)]
    assert result["summary"]["total_completed"] == 250
    assert result["summary"]["total_remaining"] == 50
    products = {r["finished_sku"]: r for r in result["summary"]["by_product"]}
    assert (products[LAMP]["completed_units"], products[LAMP]["remaining_units"],
            products[LAMP]["completed_by_revision"]) == (150, 50, {"A": 150, "B": 0})
    assert (products[CHARGER]["completed_units"], products[CHARGER]["remaining_units"]) == (100, 0)
    assert result["summary"]["remaining_inventory"] == {
        "LED-100": 10, "LED-101": 0, "LAM-HSG-110": 90, "SCR-120": 100,
        "ADP-130": 20, "PCB-200": 10, "CHG-HSG-210": 10, "USB-220": 10}
    assert result["summary"]["physical_inventory"]["SCR-120"] == 200
    advice = {r["component_sku"]: r for r in result["purchase_advice"]}
    assert (advice["LED-101"]["dated_shortage"],
            advice["LED-101"]["suggested_order_qty"]) == (40, 40)
    assert (advice["ADP-130"]["dated_shortage"],
            advice["ADP-130"]["suggested_order_qty"]) == (30, 50)
    assert (advice["SCR-120"]["dated_shortage"],
            advice["SCR-120"]["suggested_order_qty"]) == (100, 200)
    assert [(r["date"], r["bom_revision"], r["planned_units"])
            for r in result["material_requirements"]
            if r["finished_sku"] == LAMP and r["component_sku"].startswith("LED-")] == [
                (D1, "A", 80), (D2, "A", 80), (D3, "B", 40)]
    assert_demand_balance(result, demand)
    assert_ecn_conservation(result, inventory)
