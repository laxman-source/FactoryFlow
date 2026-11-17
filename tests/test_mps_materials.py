"""Independent fictional oracles for dated MPS-to-material planning."""

from datetime import date

import pytest

from factoryflow.data import (
    BOM, DEFAULT_DEMAND, DEMO_AS_OF, DEMO_PRODUCTION_DATE, INVENTORY, RECEIPTS,
)
from factoryflow.ecn import (
    BOMRevision, ECN, ECNChangeLine, ProductionLot, StockHold, approve_ecn,
)
from factoryflow.mps import ProposedMPSCompletion, calculate_mps
from factoryflow.mps_data import (
    DEMO_FG_OPENING, DEMO_FINISHED_SKUS, DEMO_FIRM_ORDERS, DEMO_FORECASTS,
    DEMO_MPS_AS_OF, DEMO_MPS_COMPLETIONS, DEMO_MPS_END,
)
from factoryflow.mps_materials import calculate_mps_materials
from factoryflow.planning import calculate_plan

LAMP, CHARGER = "FG-LAMP-01", "FG-CHARGER-02"
SNAPSHOT = date(2026, 11, 30)
D1, D2, D3 = (date(2026, 12, n) for n in (1, 2, 3))


def stock(sku, qty, *, reserved=0, safety=0):
    return {"sku": sku, "name": sku, "on_hand": qty, "reserved": reserved,
            "safety_stock": safety, "lead_days": 5, "pack_size": 1}


def bom(sku, component, per_unit):
    return {"finished_sku": sku, "component_sku": component,
            "qty_per_unit": per_unit}


def proposal(sku, day, qty):
    return ProposedMPSCompletion(sku, day, day, qty)


def run(proposals, base_bom, inventory, receipts=(), **options):
    return calculate_mps_materials(
        proposals, base_bom, inventory, receipts, SNAPSHOT, D3, **options,
    )


def ledger(result, sku):
    return {row["date"]: row for row in result["component_ledger"]
            if row["component_sku"] == sku}


def test_two_products_share_one_component_requirement_and_stock_pool():
    result = run(
        [proposal(LAMP, D1, 2), proposal(CHARGER, D1, 3)],
        [bom(LAMP, "SCR", 4), bom(CHARGER, "SCR", 2)],
        [stock("SCR", 10)],
    )
    assert [(r["finished_sku"], r["proposed_mps_qty"], r["gross_required"])
            for r in result["material_requirements"]] == [
                (CHARGER, 3, 6), (LAMP, 2, 8)]
    assert result["daily_component_requirements"] == [
        {"requirement_date": D1, "component_sku": "SCR", "gross_required": 14}
    ]
    row = ledger(result, "SCR")[D1]
    assert (row["opening_usable"], row["gross_required"],
            row["nominal_covered"], row["material_shortage"],
            row["projected_closing_usable"]) == (10, 14, 10, 4, 0)
    assert result["shortages"] == [{
        "requirement_date": D1, "component_sku": "SCR",
        "material_shortage": 4, "outstanding_requirement": 4,
    }]
    assert "actual_production" not in result
    assert "simulated_feasible_production" not in result
    assert "purchase_advice" not in result


def test_multiple_dates_carry_opening_stock_once_and_keep_shortage_outstanding():
    result = run(
        [proposal(LAMP, D1, 2), proposal(LAMP, D2, 3)],
        [bom(LAMP, "MAT", 2)], [stock("MAT", 7)],
    )
    rows = ledger(result, "MAT")
    assert [(rows[day]["opening_usable"], rows[day]["gross_required"],
             rows[day]["nominal_covered"], rows[day]["material_shortage"],
             rows[day]["projected_closing_usable"],
             rows[day]["outstanding_requirement"]) for day in (D1, D2, D3)] == [
                 (7, 4, 4, 0, 3, 0),
                 (3, 6, 3, 3, 0, 3),
                 (0, 0, 0, 0, 0, 3),
             ]
    assert [(r["requirement_date"], r["gross_required"])
            for r in result["daily_component_requirements"]] == [
                (D1, 4), (D2, 6),
            ]


def test_confirmed_receipt_before_requirement_carries_forward():
    result = run(
        [proposal(LAMP, D2, 5)], [bom(LAMP, "MAT", 1)],
        [stock("MAT", 2)],
        [{"component_sku": "MAT", "qty": 3, "due_date": D1,
          "confirmed": True}],
    )
    rows = ledger(result, "MAT")
    assert (rows[D1]["confirmed_receipts"], rows[D1]["projected_closing_usable"]) == (3, 5)
    assert (rows[D2]["opening_usable"], rows[D2]["gross_required"],
            rows[D2]["material_shortage"], rows[D2]["projected_closing_usable"]) == (
                5, 5, 0, 0,
            )


def test_late_receipt_does_not_erase_original_shortage_or_move_mps_date():
    result = run(
        [proposal(LAMP, D1, 4)], [bom(LAMP, "MAT", 1)],
        [stock("MAT", 1)],
        [{"component_sku": "MAT", "qty": 3, "due_date": D2,
          "confirmed": True}],
    )
    rows = ledger(result, "MAT")
    assert (rows[D1]["gross_required"], rows[D1]["material_shortage"],
            rows[D1]["projected_closing_usable"]) == (4, 3, 0)
    assert (rows[D2]["confirmed_receipts"], rows[D2]["projected_closing_usable"],
            rows[D2]["outstanding_requirement"]) == (3, 3, 3)
    assert result["mps_proposals"][0]["production_start"] == D1
    assert result["mps_proposals"][0]["completion_date"] == D1


def test_same_day_confirmed_receipt_counts_and_unconfirmed_does_not():
    result = run(
        [proposal(LAMP, D1, 4)], [bom(LAMP, "MAT", 1)],
        [stock("MAT", 0)],
        [{"component_sku": "MAT", "qty": 3, "due_date": D1,
          "confirmed": True},
         {"component_sku": "MAT", "qty": 20, "due_date": D1,
          "confirmed": False}],
    )
    row = ledger(result, "MAT")[D1]
    assert (row["confirmed_receipts"], row["nominal_covered"],
            row["material_shortage"]) == (3, 3, 1)


def test_snapshot_receipt_is_not_added_to_opening_stock_again():
    result = run(
        [proposal(LAMP, D1, 4)], [bom(LAMP, "MAT", 1)],
        [stock("MAT", 5)],
        [{"component_sku": "MAT", "qty": 5, "due_date": SNAPSHOT,
          "confirmed": True}],
    )
    row = ledger(result, "MAT")[D1]
    assert (row["opening_usable"], row["confirmed_receipts"],
            row["gross_required"], row["projected_closing_usable"]) == (5, 0, 4, 1)


def test_reserved_and_safety_stock_are_excluded_once():
    result = run(
        [proposal(LAMP, D1, 7)], [bom(LAMP, "MAT", 1)],
        [stock("MAT", 10, reserved=2, safety=1)],
    )
    row = ledger(result, "MAT")[D1]
    assert (row["opening_usable"], row["nominal_covered"],
            row["material_shortage"], row["projected_closing_usable"]) == (
                7, 7, 0, 0,
            )


def ecn_inputs():
    base = [bom(LAMP, "LED-A", 1), bom(LAMP, "SCR", 1),
            bom(CHARGER, "SCR", 2)]
    rev_b = BOMRevision(LAMP, "B", (("LED-B", 1), ("SCR", 1)))
    inventory = [stock("LED-A", 2), stock("LED-B", 1), stock("SCR", 10)]
    draft = ECN(
        "ECN-1", LAMP, "A", "B", D3,
        (ECNChangeLine("LED-A", "LED-B", 1, 1),), "hold",
    )
    approved = approve_ecn(
        draft, approval_date=D2, effective_date=D3,
        approved_by="Fictional engineer", base_bom=base,
        proposed_revisions=[rev_b], inventory=inventory,
    )
    return base, rev_b, inventory, draft, approved


def test_approved_ecn_uses_production_start_and_preserves_both_mps_dates():
    base, rev_b, inventory, _, approved = ecn_inputs()
    result = run(
        [proposal(LAMP, D2, 2), proposal(LAMP, D3, 3),
         proposal(CHARGER, D3, 1)],
        base, inventory, proposed_revisions=[rev_b], ecns=[approved],
    )
    assert [(r["production_start"], r["completion_date"],
             r["finished_sku"], r["proposed_mps_qty"], r["bom_revision"])
            for r in result["mps_proposals"]] == [
                (D2, D2, LAMP, 2, "A"),
                (D3, D3, CHARGER, 1, "A"),
                (D3, D3, LAMP, 3, "B"),
            ]
    assert [(r["requirement_date"], r["component_sku"],
             r["gross_required"]) for r in result["daily_component_requirements"]] == [
                 (D2, "LED-A", 2), (D2, "SCR", 2),
                 (D3, "LED-B", 3), (D3, "SCR", 5),
             ]
    assert (ledger(result, "LED-A")[D2]["projected_closing_usable"],
            ledger(result, "LED-B")[D3]["material_shortage"],
            ledger(result, "SCR")[D3]["projected_closing_usable"]) == (0, 2, 3)
    assert all(r["production_start"] == r["requirement_date"]
               for r in result["material_requirements"])


def test_draft_ecn_does_not_activate_proposed_revision():
    base, rev_b, inventory, draft, _ = ecn_inputs()
    result = run(
        [proposal(LAMP, D3, 1)], base, inventory,
        proposed_revisions=[rev_b], ecns=[draft],
    )
    assert result["mps_proposals"][0]["bom_revision"] == "A"
    assert [(r["component_sku"], r["gross_required"])
            for r in result["material_requirements"]] == [
                ("LED-A", 1), ("SCR", 1),
            ]


@pytest.mark.parametrize("lot", [
    ProductionLot("WIP-1", LAMP, 2, SNAPSHOT, "wip", "A"),
    ProductionLot("REL-1", LAMP, 2, SNAPSHOT, "released", "A"),
])
def test_unsupported_wip_or_released_lot_fails_closed(lot):
    base, rev_b, inventory, _, approved = ecn_inputs()
    with pytest.raises(ValueError, match="Manual ECN/WIP disposition review"):
        run([proposal(LAMP, D3, 2)], base, inventory,
            proposed_revisions=[rev_b], ecns=[approved], lots=[lot])


def test_conflicting_approved_ecns_fail_before_material_ledger():
    base, rev_b, inventory, _, approved = ecn_inputs()
    rev_c = BOMRevision(LAMP, "C", (("LED-C", 1), ("SCR", 1)))
    inventory.append(stock("LED-C", 5))
    competing = ECN(
        "ECN-2", LAMP, "A", "C", D3,
        (ECNChangeLine("LED-A", "LED-C", 1, 1),), "hold",
        status="approved", approval_date=D2, effective_date=D3,
        approved_by="Fictional engineer",
    )
    with pytest.raises(ValueError, match="Conflicting approved ECNs"):
        run([proposal(LAMP, D3, 1)], base, inventory,
            proposed_revisions=[rev_b, rev_c], ecns=[approved, competing])


def test_missing_new_revision_component_master_fails_closed():
    base, rev_b, inventory, _, approved = ecn_inputs()
    inventory = [item for item in inventory if item["sku"] != "LED-B"]
    with pytest.raises(ValueError, match="Missing inventory master"):
        run([proposal(LAMP, D3, 1)], base, inventory,
            proposed_revisions=[rev_b], ecns=[approved])


def test_stock_hold_requires_separate_review_in_this_milestone():
    with pytest.raises(ValueError, match="stock holds requires manual review"):
        run(
            [proposal(LAMP, D1, 1)], [bom(LAMP, "MAT", 1)], [stock("MAT", 1)],
            stock_holds=[StockHold("MAT", 1, D1, "Fictional approver", SNAPSHOT)],
        )


@pytest.mark.parametrize("proposals,base,inventory,match", [
    ([proposal(LAMP, D1, 1), proposal(LAMP, D1, 2)],
     [bom(LAMP, "MAT", 1)], [stock("MAT", 3)], "Duplicate"),
    ([ProposedMPSCompletion(LAMP, D1, D2, 1)],
     [bom(LAMP, "MAT", 1)], [stock("MAT", 3)], "same-day"),
    ([proposal(LAMP, date(2026, 12, 4), 1)],
     [bom(LAMP, "MAT", 1)], [stock("MAT", 3)], "horizon"),
    ([proposal(LAMP, D1, 1)],
     [bom(LAMP, "MAT", 1)], [], "Missing inventory master"),
    ([proposal("UNKNOWN", D1, 1)],
     [bom(LAMP, "MAT", 1)], [stock("MAT", 3)], "No base BOM"),
])
def test_invalid_mps_material_inputs_reject(proposals, base, inventory, match):
    with pytest.raises(ValueError, match=match):
        run(proposals, base, inventory)


def test_component_ledger_conserves_one_chronological_stock_pool():
    result = run(
        [proposal(LAMP, D1, 2), proposal(CHARGER, D2, 2)],
        [bom(LAMP, "SCR", 3), bom(CHARGER, "SCR", 2)],
        [stock("SCR", 7)],
        [{"component_sku": "SCR", "qty": 2, "due_date": D2,
          "confirmed": True}],
    )
    rows = ledger(result, "SCR")
    assert [(rows[d]["gross_required"], rows[d]["confirmed_receipts"],
             rows[d]["material_shortage"], rows[d]["projected_closing_usable"])
            for d in (D1, D2)] == [(6, 0, 0, 1), (4, 2, 1, 0)]
    for row in rows.values():
        assert (row["opening_usable"] + row["confirmed_receipts"]
                - row["nominal_covered"] == row["projected_closing_usable"])
        assert row["gross_required"] == (
            row["nominal_covered"] + row["material_shortage"]
        )


def test_existing_mps_and_mrp_oracles_remain_unchanged():
    mps = calculate_mps(
        DEMO_FINISHED_SKUS, DEMO_FG_OPENING, DEMO_FIRM_ORDERS,
        DEMO_FORECASTS, DEMO_MPS_COMPLETIONS, DEMO_MPS_AS_OF, DEMO_MPS_END,
    )
    assert [(r["planning_date"], r["finished_sku"], r["projected_fg_balance"])
            for r in mps] == [
                (D1, CHARGER, 3), (D1, LAMP, 10),
                (D2, CHARGER, 3), (D2, LAMP, 10),
                (D3, CHARGER, 3), (D3, LAMP, 10),
            ]
    mrp = {r["sku"]: r for r in calculate_plan(
        DEFAULT_DEMAND, BOM, INVENTORY, RECEIPTS,
        DEMO_AS_OF, DEMO_PRODUCTION_DATE,
    )}
    assert (mrp["LED-100"]["gross_required"],
            mrp["LED-100"]["incoming_on_time"],
            mrp["LED-100"]["net_shortage"]) == (200, 40, 40)
    assert (mrp["SCR-120"]["gross_required"],
            mrp["SCR-120"]["usable_stock"],
            mrp["SCR-120"]["net_shortage"]) == (1000, 900, 100)
