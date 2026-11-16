"""Independent Phase 5A examples and ECN safety rules, using fictional stock."""

from datetime import date

import pytest

from factoryflow.data import BOM, DEFAULT_DEMAND, DEMO_AS_OF, INVENTORY, RECEIPTS
from factoryflow.ecn import (
    BOMRevision, ECN, ECNChangeLine, ProductionLot, StockHold,
    approve_ecn, cancel_ecn,
)
from factoryflow.ecn_planning import calculate_ecn_plan
from factoryflow.production_schedule import calculate_production_schedule


LAMP = "FG-LAMP-01"
CHARGER = "FG-CHARGER-02"
SNAPSHOT = date(2026, 11, 30)
D1, D2, D3, D4 = (date(2026, 12, day) for day in range(1, 5))
LINES = [{"finished_sku": LAMP, "name": "Lamp line", "daily_capacity": 2}]
BASE_BOM = [
    {"finished_sku": LAMP, "component_sku": "LED-100", "qty_per_unit": 1},
    {"finished_sku": LAMP, "component_sku": "HSG", "qty_per_unit": 1},
    {"finished_sku": LAMP, "component_sku": "SCR", "qty_per_unit": 4},
    {"finished_sku": LAMP, "component_sku": "ADP", "qty_per_unit": 1},
]
REV_B = BOMRevision(LAMP, "B", (
    ("LED-101", 1), ("HSG", 1), ("SCR", 4), ("ADP", 1),
))
CHANGE = ECNChangeLine("LED-100", "LED-101", 1, 1)


def stock(old=8, new=4):
    return [
        {"sku": sku, "name": sku, "on_hand": qty, "reserved": 0,
         "safety_stock": 0, "lead_days": 7, "pack_size": 5}
        for sku, qty in (("LED-100", old), ("LED-101", new),
                         ("HSG", 8), ("SCR", 32), ("ADP", 8))
    ]


def draft(*, disposition="hold"):
    return ECN("ECN-001", LAMP, "A", "B", D3, (CHANGE,), disposition)


def approved(*, inventory=None):
    return approve_ecn(
        draft(), approval_date=D2, effective_date=D3,
        approved_by="Fictional engineering approver", base_bom=BASE_BOM,
        proposed_revisions=[REV_B], inventory=stock() if inventory is None else inventory,
    )


def plan(*, demand=8, end=D4, inventory=None, receipts=(), ecns=None,
         holds=(), lots=None, base_bom=BASE_BOM, revisions=(REV_B,), lines=LINES):
    return calculate_ecn_plan(
        {LAMP: demand}, base_bom, stock() if inventory is None else inventory,
        list(receipts), SNAPSHOT, D1, end, proposed_revisions=revisions,
        ecns=[approved()] if ecns is None else ecns, stock_holds=holds,
        lots=lots, lines=lines,
    )


def builds(result):
    return [row["actual_buildable_units"] for row in result["daily_schedule"]
            if row["finished_sku"] == LAMP]


def consumed(result, sku):
    return sum(row["simulated_use"] for row in result["stock_ledger"]
               if row["component_sku"] == sku)


@pytest.mark.parametrize("case,options,expected_builds,expected_revisions,expected_old,expected_new", [
    ("A draft", {"ecns": [draft()]}, [2, 2, 2, 2], ["A"] * 4, 0, 4),
    ("B approved before effect", {"demand": 4, "end": D2}, [2, 2], ["A", "A"], 4, 4),
    ("C spanning effect", {}, [2, 2, 2, 2], ["A", "A", "B", "B"], 4, 0),
    ("D new-part shortage", {"inventory": stock(new=1)}, [2, 2, 1, 0],
     ["A", "A", "B", "B"], 4, 0),
    ("E old-stock hold", {"inventory": stock(old=12),
                          "holds": [StockHold("LED-100", 8, D3, "Fictional approver", D2)]},
     [2, 2, 2, 2], ["A", "A", "B", "B"], 0, 0),
    ("F late new-part receipt", {"inventory": stock(new=0),
                                 "receipts": [{"component_sku": "LED-101", "qty": 4,
                                               "due_date": D4, "confirmed": True}]},
     [2, 2, 0, 2], ["A", "A", "B", "B"], 4, 2),
    ("G cancelled", {"ecns": [cancel_ecn(approved(), cancellation_date=D2,
                                        reason="Fictional change withdrawn")]},
     [2, 2, 2, 2], ["A"] * 4, 0, 4),
])
def test_design_scenarios_a_to_g(case, options, expected_builds,
                                 expected_revisions, expected_old, expected_new):
    result = plan(**options)
    rows = result["daily_schedule"]
    assert builds(result) == expected_builds, case
    assert [row["bom_revision"] for row in rows] == expected_revisions, case
    assert result["summary"]["total_completed"] == sum(expected_builds)
    assert result["summary"]["total_remaining"] == options.get("demand", 8) - sum(expected_builds)
    assert result["summary"]["remaining_inventory"]["LED-100"] == expected_old
    assert result["summary"]["remaining_inventory"]["LED-101"] == expected_new
    assert consumed(result, "LED-100") == sum(
        qty for qty, revision in zip(expected_builds, expected_revisions) if revision == "A"
    )
    assert consumed(result, "LED-101") == sum(
        qty for qty, revision in zip(expected_builds, expected_revisions) if revision == "B"
    )
    assert [row["date"] for row in rows] == [D1, D2, D3, D4][:len(rows)]
    for row in result["stock_ledger"]:
        assert (row["opening_usable"] + row["confirmed_receipts"]
                - row["authorized_hold"] - row["simulated_use"]
                == row["closing_usable"] >= 0)


def test_scenario_c_trace_and_revision_aware_requirements():
    result = plan()
    trace = result["revision_trace"]
    assert [(row["date"], row["bom_revision"], row["ecn_reference"], row["simulated_units"])
            for row in trace] == [
        (D1, "A", None, 2), (D2, "A", None, 2),
        (D3, "B", "ECN-001", 2), (D4, "B", "ECN-001", 2),
    ]
    led_needs = [(row["date"], row["component_sku"], row["qty"])
                 for row in result["material_requirements"]
                 if row["component_sku"].startswith("LED-")]
    assert led_needs == [(D1, "LED-100", 2), (D2, "LED-100", 2),
                         (D3, "LED-101", 2), (D4, "LED-101", 2)]
    assert consumed(result, "SCR") == 8 * 4
    assert result["summary"]["by_product"][0]["completed_by_revision"] == {"A": 4, "B": 4}


@pytest.mark.parametrize("notice", [
    draft(),
    cancel_ecn(draft(), cancellation_date=D2, reason="Withdrawn"),
])
def test_inactive_ecn_cannot_require_or_consume_new_component(notice):
    old_only = [item for item in stock() if item["sku"] != "LED-101"]
    result = plan(inventory=old_only, ecns=[notice])
    assert builds(result) == [2, 2, 2, 2]
    assert all(row["bom_revision"] == "A" for row in result["daily_schedule"])
    assert "LED-101" not in result["summary"]["remaining_inventory"]


def test_scenario_d_purchase_advice_uses_first_short_day_and_pack_size():
    result = plan(inventory=stock(new=1))
    led = next(row for row in result["purchase_advice"]
               if row["component_sku"] == "LED-101")
    assert (led["dated_shortage"], led["first_shortage_date"],
            led["suggested_order_qty"], led["latest_order_date"], led["status"]) == (
        3, D3, 5, date(2026, 11, 26), "At risk: expedite",
    )
    assert all(row["component_sku"] != "LED-100" for row in result["purchase_advice"])
    assert result["summary"]["remaining_inventory"]["LED-101"] == 0


def test_scenario_e_hold_keeps_physical_stock_without_automatic_scrap():
    result = plan(inventory=stock(old=12),
                  holds=[StockHold("LED-100", 8, D3, "Fictional approver", D2)])
    summary = result["summary"]
    assert (summary["physical_inventory"]["LED-100"],
            summary["held_inventory"]["LED-100"],
            summary["remaining_inventory"]["LED-100"]) == (8, 8, 0)
    assert result["disposition_review"][0]["manual_action_required"] is False


def test_stock_hold_requires_prior_authorization():
    with pytest.raises(ValueError, match="authorization"):
        StockHold("LED-100", 8, D3, "Fictional approver", D4)


@pytest.mark.parametrize("disposition", ["use-up", "hold", "return", "scrap"])
def test_disposition_proposal_never_posts_an_inventory_transaction(disposition):
    notice = approve_ecn(
        draft(disposition=disposition), approval_date=D2, effective_date=D3,
        approved_by="Fictional approver", base_bom=BASE_BOM,
        proposed_revisions=[REV_B], inventory=stock(old=12),
    )
    result = plan(inventory=stock(old=12), ecns=[notice])
    review = result["disposition_review"][0]
    assert (review["disposition"], review["physical_on_hand"],
            review["held_qty"], review["remaining_usable"]) == (disposition, 8, 0, 8)
    assert review["manual_action_required"] is True
    assert review["automatic_stock_change"] is False
    assert result["summary"]["total_completed"] == 8


def test_scenario_f_late_receipt_does_not_supply_first_revision_b_day():
    result = plan(inventory=stock(new=0), receipts=[
        {"component_sku": "LED-101", "qty": 4, "due_date": D4},
    ])
    ledger = [row for row in result["stock_ledger"] if row["component_sku"] == "LED-101"]
    assert [(row["date"], row["confirmed_receipts"], row["simulated_use"])
            for row in ledger if row["date"] in (D3, D4)] == [(D3, 0, 0), (D4, 4, 2)]
    assert next(row for row in result["purchase_advice"]
                if row["component_sku"] == "LED-101")["dated_shortage"] == 2


def test_scenario_h_conflicting_approved_revisions_publish_no_schedule():
    rev_c = BOMRevision(LAMP, "C", (
        ("LED-102", 1), ("HSG", 1), ("SCR", 4), ("ADP", 1),
    ))
    other = ECN("ECN-002", LAMP, "A", "C", D3,
                (ECNChangeLine("LED-100", "LED-102", 1, 1),), "hold")
    inventory = stock() + [{"sku": "LED-102", "name": "LED-102", "on_hand": 4,
                            "reserved": 0, "safety_stock": 0,
                            "lead_days": 7, "pack_size": 5}]
    other_approved = approve_ecn(
        other, approval_date=D2, effective_date=D3, approved_by="Fictional approver",
        base_bom=BASE_BOM, proposed_revisions=[rev_c], inventory=inventory,
    )
    with pytest.raises(ValueError, match="Conflicting"):
        plan(inventory=inventory, revisions=[REV_B, rev_c],
             ecns=[approved(), other_approved])


def test_status_transitions_and_late_approval_are_rejected():
    first = draft()
    assert first.status == "draft"
    accepted = approved()
    assert accepted.status == "approved" and first.status == "draft"
    cancelled = cancel_ecn(accepted, cancellation_date=D2, reason="Withdrawn")
    assert cancelled.status == "cancelled" and accepted.status == "approved"
    with pytest.raises(ValueError, match="draft"):
        approve_ecn(accepted, approval_date=D2, effective_date=D3,
                    approved_by="Engineer", base_bom=BASE_BOM,
                    proposed_revisions=[REV_B], inventory=stock())
    with pytest.raises(ValueError, match="draft"):
        approve_ecn(cancelled, approval_date=D2, effective_date=D3,
                    approved_by="Engineer", base_bom=BASE_BOM,
                    proposed_revisions=[REV_B], inventory=stock())
    with pytest.raises(ValueError, match="later"):
        approve_ecn(first, approval_date=D3, effective_date=D3,
                    approved_by="Engineer", base_bom=BASE_BOM,
                    proposed_revisions=[REV_B], inventory=stock())
    with pytest.raises(ValueError, match="retroactively"):
        cancel_ecn(accepted, cancellation_date=D3, reason="Too late")
    with pytest.raises(ValueError, match="transition"):
        cancel_ecn(cancelled, cancellation_date=D2, reason="Again")
    assert cancel_ecn(first, cancellation_date=D2, reason="Withdrawn").status == "cancelled"


@pytest.mark.parametrize("fields", [
    {"status": "unknown"},
    {"status": "draft", "cancellation_reason": "No date"},
    {"status": "approved", "approval_date": D2, "effective_date": D3,
     "approved_by": "Engineer", "cancellation_reason": "Conflicting state"},
    {"status": "cancelled", "cancellation_date": D3,
     "cancellation_reason": "Too late", "approval_date": D2,
     "effective_date": D3, "approved_by": "Engineer"},
])
def test_inconsistent_ecn_records_are_rejected(fields):
    values = dict(reference="ECN-BAD", finished_sku=LAMP, from_revision="A",
                  to_revision="B", proposed_effective_date=D3,
                  changes=(CHANGE,), disposition="hold")
    values.update(fields)
    with pytest.raises(ValueError):
        ECN(**values)


def test_approval_requires_complete_bom_and_new_component_master():
    with pytest.raises(ValueError, match="Missing inventory master"):
        approved(inventory=[item for item in stock() if item["sku"] != "LED-101"])
    incomplete = BOMRevision(LAMP, "B", (("LED-101", 1), ("HSG", 1)))
    with pytest.raises(ValueError, match="complete"):
        approve_ecn(draft(), approval_date=D2, effective_date=D3,
                    approved_by="Engineer", base_bom=BASE_BOM,
                    proposed_revisions=[incomplete], inventory=stock())
    with pytest.raises(ValueError, match="disposition"):
        approve_ecn(draft(disposition=None), approval_date=D2, effective_date=D3,
                    approved_by="Engineer", base_bom=BASE_BOM,
                    proposed_revisions=[REV_B], inventory=stock())


def test_released_old_revision_is_held_after_effect_and_new_lot_can_run():
    lots = [
        ProductionLot("OLD", LAMP, 6, SNAPSHOT, "released", "A"),
        ProductionLot("NEW", LAMP, 2, D3),
    ]
    result = plan(lots=lots)
    assert builds(result) == [2, 2, 2, 0]
    assert result["summary"]["review_required_units"] == 2
    assert result["summary"]["total_remaining"] == 2
    assert consumed(result, "LED-100") == 4
    assert consumed(result, "LED-101") == 2
    old_d3 = next(row for row in result["revision_trace"]
                  if row["date"] == D3 and row["order_id"] == "OLD")
    assert old_d3["review_required"] and old_d3["simulated_units"] == 0
    assert old_d3["active_revision"] == "B" and old_d3["pinned_revision"] == "A"


def test_wip_is_never_assumed_reworked_or_reissued():
    lot = ProductionLot("WIP-1", LAMP, 4, SNAPSHOT, "wip", "A")
    result = plan(demand=4, lots=[lot])
    assert result["summary"]["total_completed"] == 0
    assert result["summary"]["review_required_units"] == 4
    assert consumed(result, "LED-100") == consumed(result, "LED-101") == 0
    assert all(row["review_required"] for row in result["revision_trace"])


def test_competing_same_product_lots_require_a_dispatch_decision():
    lots = [ProductionLot("ONE", LAMP, 4, SNAPSHOT),
            ProductionLot("TWO", LAMP, 4, SNAPSHOT)]
    with pytest.raises(ValueError, match="dispatch priority"):
        plan(lots=lots)


def test_idle_weekend_does_not_require_lot_dispatch_priority():
    lots = [ProductionLot("ONE", LAMP, 4, SNAPSHOT),
            ProductionLot("TWO", LAMP, 4, SNAPSHOT)]
    result = calculate_ecn_plan(
        {LAMP: 8}, BASE_BOM, stock(), [], SNAPSHOT,
        date(2026, 12, 5), date(2026, 12, 6),
        proposed_revisions=[REV_B], ecns=[approved()], lines=LINES, lots=lots,
    )
    assert result["summary"]["total_completed"] == 0
    assert result["summary"]["total_remaining"] == 8


def test_new_order_creation_date_does_not_choose_revision_or_allow_early_build():
    lot = ProductionLot("NEW-ON-D3", LAMP, 2, D3)
    result = plan(demand=2, lots=[lot])
    assert builds(result) == [0, 0, 2, 0]
    assert consumed(result, "LED-100") == 0
    assert consumed(result, "LED-101") == 2
    assert result["summary"]["total_remaining"] == 0
    assert next(row for row in result["revision_trace"]
                if row["date"] == D3)["bom_revision"] == "B"


def test_old_receipts_remain_old_and_unconfirmed_new_receipt_is_excluded():
    result = plan(inventory=stock(new=0), receipts=[
        {"component_sku": "LED-100", "qty": 5, "due_date": D3, "confirmed": True},
        {"component_sku": "LED-101", "qty": 10, "due_date": D3, "confirmed": False},
    ])
    assert builds(result) == [2, 2, 0, 0]
    assert result["summary"]["physical_inventory"]["LED-100"] == 9
    assert result["summary"]["remaining_inventory"]["LED-101"] == 0
    assert result["old_receipt_review"] == [{
        "ecn_reference": "ECN-001", "component_sku": "LED-100",
        "qty": 5, "due_date": D3,
        "action": "manual supplier/disposition review",
    }]


def test_shared_component_priority_is_preserved_under_revision_b():
    base = BASE_BOM + [
        {"finished_sku": CHARGER, "component_sku": "PCB", "qty_per_unit": 1},
        {"finished_sku": CHARGER, "component_sku": "SCR", "qty_per_unit": 2},
    ]
    inventory = stock() + [{"sku": "PCB", "name": "PCB", "on_hand": 2,
                            "reserved": 0, "safety_stock": 0,
                            "lead_days": 7, "pack_size": 5}]
    next(item for item in inventory if item["sku"] == "SCR")["on_hand"] = 5
    lines = LINES + [{"finished_sku": CHARGER, "name": "Charger line", "daily_capacity": 2}]
    result = calculate_ecn_plan(
        {LAMP: 2, CHARGER: 2}, base, inventory, [], SNAPSHOT, D3, D3,
        proposed_revisions=[REV_B], ecns=[approved(inventory=inventory)], lines=lines,
    )
    assert [(row["finished_sku"], row["actual_buildable_units"])
            for row in result["daily_schedule"]] == [(CHARGER, 2), (LAMP, 0)]
    assert result["summary"]["remaining_inventory"]["SCR"] == 1
    assert consumed(result, "SCR") == 4


@pytest.mark.parametrize("change", [
    {"demand": -1},
    {"inventory": stock(new=-1)},
    {"receipts": [{"component_sku": "LED-101", "qty": -1, "due_date": D3}]},
    {"receipts": [{"component_sku": "LED-101", "qty": 3,
                   "due_date": D3, "confirmed": "yes"}]},
    {"holds": [StockHold("LED-100", 99, D3, "Approver", D2)]},
    {"lots": [ProductionLot("X", LAMP, 8, SNAPSHOT, "released", "Z")]},
    {"lots": [ProductionLot("X", LAMP, 8, date(2026, 12, 5))]},
    {"inventory": stock() + [stock()[0]]},
    {"inventory": [dict(item) if item["sku"] != "LED-101" else
                   {key: value for key, value in item.items() if key != "name"}
                   for item in stock()]},
])
def test_invalid_stock_and_plan_inputs_fail_closed(change):
    with pytest.raises(ValueError):
        plan(**change)


@pytest.mark.parametrize("options", [
    {},
    {"overtime_by_sku": {LAMP: 20}},
    {"downtime_by_sku": {LAMP: [D2]}},
    {"overtime_by_sku": {LAMP: 20}, "downtime_by_sku": {CHARGER: [D1]}},
])
def test_no_ecn_matches_phase4d_production_and_component_balances(options):
    receipts = RECEIPTS + [{"component_sku": "LED-100", "qty": 1000,
                            "due_date": D1, "confirmed": False}]
    legacy = calculate_production_schedule(
        DEFAULT_DEMAND, BOM, INVENTORY, receipts, DEMO_AS_OF, D1, D4,
        **options,
    )
    current = calculate_ecn_plan(
        DEFAULT_DEMAND, BOM, INVENTORY, receipts, DEMO_AS_OF, D1, D4,
        **options,
    )
    assert [(row["date"], row["finished_sku"], row["actual_buildable_units"],
             row["components_consumed"], row["remaining_inventory"])
            for row in current["daily_schedule"]] == [
        (row["date"], row["finished_sku"], row["actual_buildable_units"],
         row["components_consumed"], row["remaining_inventory"])
        for row in legacy["daily_schedule"]
    ]
    assert current["summary"]["total_completed"] == legacy["summary"]["total_completed"]
    if not options:
        assert current["summary"]["total_completed"] == 260
    assert current["summary"]["remaining_inventory"] == legacy["summary"]["remaining_inventory"]


def test_future_authorized_hold_is_reserved_in_nominal_requirements():
    """Nominal advice must not consume stock that actual builds leave for a hold."""
    replacement = BOMRevision(
        LAMP, "B",
        tuple(
            ("LED-101" if row["component_sku"] == "LED-100"
             else row["component_sku"], row["qty_per_unit"])
            for row in BOM if row["finished_sku"] == LAMP
        ),
    )
    inventory = [row.copy() for row in INVENTORY] + [{
        "sku": "LED-101", "name": "Fictional replacement LED",
        "on_hand": 0, "reserved": 0, "safety_stock": 0,
        "lead_days": 7, "pack_size": 5,
    }]
    notice = approve_ecn(
        ECN("ECN-001", LAMP, "A", "B", D3, (CHANGE,), "hold"),
        approval_date=D2, effective_date=D3,
        approved_by="Fictional approver", base_bom=BOM,
        proposed_revisions=[replacement], inventory=inventory,
    )
    result = calculate_ecn_plan(
        DEFAULT_DEMAND, BOM, inventory, RECEIPTS, DEMO_AS_OF, D1, D4,
        proposed_revisions=[replacement], ecns=[notice],
        stock_holds=[StockHold(
            "LED-100", 10, D3, "Fictional stock controller", D2,
        )],
    )
    nominal_dec2 = next(
        row for row in result["requirement_ledger"]
        if row["date"] == D2 and row["component_sku"] == "LED-100"
    )
    closing_old = next(
        row for row in result["stock_ledger"]
        if row["date"] == D4 and row["component_sku"] == "LED-100"
    )
    assert nominal_dec2["unmet_need"] == 10
    assert result["summary"]["total_completed"] == 250
    assert (closing_old["closing_physical"], closing_old["closing_held"],
            closing_old["closing_usable"]) == (10, 10, 0)
