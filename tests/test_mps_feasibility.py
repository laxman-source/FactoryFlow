"""Independent fictional oracles for dated MPS whole-unit feasibility."""

from datetime import date

import pytest

from factoryflow.data import (
    BOM, DEFAULT_DEMAND, DEMO_AS_OF, DEMO_PRODUCTION_DATE, INVENTORY, RECEIPTS,
)
from factoryflow.ecn import (
    BOMRevision, ECN, ECNChangeLine, ProductionLot, StockHold, approve_ecn,
)
from factoryflow.ecn_planning import calculate_ecn_plan
from factoryflow.mps import ProposedMPSCompletion, calculate_mps
from factoryflow.mps_data import (
    DEMO_FG_OPENING, DEMO_FINISHED_SKUS, DEMO_FIRM_ORDERS, DEMO_FORECASTS,
    DEMO_MPS_AS_OF, DEMO_MPS_COMPLETIONS, DEMO_MPS_END,
)
from factoryflow.mps_feasibility import calculate_mps_feasibility
from factoryflow.planning import calculate_plan

LAMP, CHARGER, FAN = "FG-LAMP-01", "FG-CHARGER-02", "FG-FAN-03"
SNAPSHOT = date(2026, 11, 30)
D1, D2, D3 = (date(2026, 12, n) for n in (1, 2, 3))


def proposal(sku, day, qty):
    return ProposedMPSCompletion(sku, day, day, qty)


def bom(sku, component, qty=1):
    return {"finished_sku": sku, "component_sku": component,
            "qty_per_unit": qty}


def stock(sku, qty, *, reserved=0, safety=0):
    return {"sku": sku, "name": sku, "on_hand": qty, "reserved": reserved,
            "safety_stock": safety, "lead_days": 5, "pack_size": 1}


def line(sku, capacity=3):
    return {"finished_sku": sku, "name": sku, "daily_capacity": capacity}


def run(proposals, base_bom, inventory, receipts=(), *, lines=None, end=D3, **options):
    if lines is None:
        lines = [line(LAMP)]
    return calculate_mps_feasibility(
        proposals, base_bom, inventory, receipts, SNAPSHOT, end,
        lines=lines, **options,
    )


def row(result, day, sku=LAMP):
    return next(item for item in result["feasibility_rows"]
                if item["production_start"] == day and item["finished_sku"] == sku)


def balance(result, day, component):
    return next(item for item in result["simulated_consumption_ledger"]
                if item["date"] == day and item["component_sku"] == component)


def test_fully_feasible_proposal_builds_complete_units():
    result = run(
        [proposal(LAMP, D1, 2)],
        [bom(LAMP, "A", 2), bom(LAMP, "B", 1)],
        [stock("A", 4), stock("B", 2)],
        lines=[line(LAMP, 2)],
    )
    built = row(result, D1)
    assert (built["proposed_mps_units"], built["available_capacity"],
            built["simulated_buildable_units"], built["known_unbuilt_units"],
            built["unresolved_units"]) == (2, 2, 2, 0, 0)
    assert built["simulated_components_consumed"] == {"A": 4, "B": 2}
    assert built["simulated_capacity_used"] == 2
    assert balance(result, D1, "A")["simulated_closing_usable"] == 0
    assert balance(result, D1, "B")["simulated_closing_usable"] == 0
    assert result["shared_component_conflicts"] == []


def test_material_constraint_consumes_only_complete_product_sets():
    result = run(
        [proposal(LAMP, D1, 3)],
        [bom(LAMP, "A", 2), bom(LAMP, "B", 1)],
        [stock("A", 5), stock("B", 3)],
    )
    built = row(result, D1)
    assert (built["simulated_buildable_units"], built["material_unbuilt_units"],
            built["known_unbuilt_units"]) == (2, 1, 1)
    assert built["simulated_components_consumed"] == {"A": 4, "B": 2}
    assert (balance(result, D1, "A")["simulated_closing_usable"],
            balance(result, D1, "B")["simulated_closing_usable"]) == (1, 1)
    nominal = result["nominal_material_plan"]["component_ledger"]
    assert next(r for r in nominal if r["date"] == D1 and r["component_sku"] == "B")[
        "nominal_covered"
    ] == 3
    assert balance(result, D1, "B")["simulated_use"] == 2


def test_capacity_constraint_leaves_material_unconsumed_and_does_not_reschedule():
    result = run(
        [proposal(LAMP, D1, 5)], [bom(LAMP, "MAT")],
        [stock("MAT", 5)], lines=[line(LAMP, 3)],
    )
    built = row(result, D1)
    assert (built["available_capacity"], built["simulated_buildable_units"],
            built["capacity_unbuilt_units"], built["known_unbuilt_units"]) == (
                3, 3, 2, 2,
            )
    assert balance(result, D1, "MAT")["simulated_closing_usable"] == 2
    assert balance(result, D2, "MAT")["simulated_closing_usable"] == 2
    assert len(result["feasibility_rows"]) == 1


def test_combined_capacity_and_material_limits_are_separate():
    result = run(
        [proposal(LAMP, D1, 5)], [bom(LAMP, "MAT")],
        [stock("MAT", 2)], lines=[line(LAMP, 3)],
    )
    built = row(result, D1)
    assert (built["simulated_buildable_units"],
            built["capacity_unbuilt_units"], built["material_unbuilt_units"],
            built["known_unbuilt_units"]) == (2, 2, 1, 3)
    assert built["simulated_capacity_used"] == 2
    assert balance(result, D1, "MAT")["simulated_use"] == 2


def test_remaining_inventory_carries_to_later_explicit_mps_date():
    result = run(
        [proposal(LAMP, D1, 2), proposal(LAMP, D2, 2)],
        [bom(LAMP, "MAT")], [stock("MAT", 4)],
        lines=[line(LAMP, 1)],
        overtime_by_sku={LAMP: 1},
        downtime_by_sku={LAMP: [D1]},
    )
    assert (row(result, D1)["available_capacity"],
            row(result, D1)["simulated_buildable_units"]) == (0, 0)
    assert (row(result, D2)["available_capacity"],
            row(result, D2)["simulated_buildable_units"]) == (2, 2)
    assert (balance(result, D1, "MAT")["simulated_closing_usable"],
            balance(result, D2, "MAT")["simulated_closing_usable"]) == (4, 2)
    assert result["summary"] == {
        "total_proposed_mps_units": 4,
        "total_simulated_buildable_units": 2,
        "total_known_unbuilt_units": 2,
        "total_unresolved_units": 0,
    }


def test_overtime_adds_capacity_and_downtime_overrides_it():
    result = run(
        [proposal(LAMP, D1, 3), proposal(LAMP, D2, 3)],
        [bom(LAMP, "MAT")], [stock("MAT", 6)],
        lines=[line(LAMP, 2)],
        overtime_by_sku={LAMP: 1},
        downtime_by_sku={LAMP: [D1]},
    )
    assert [(r["production_start"], r["available_capacity"],
             r["simulated_buildable_units"], r["known_unbuilt_units"])
            for r in result["feasibility_rows"]] == [
                (D1, 0, 0, 3), (D2, 3, 3, 0),
            ]
    assert balance(result, D2, "MAT")["simulated_closing_usable"] == 3


def test_confirmed_receipt_before_need_is_available_on_explicit_date():
    result = run(
        [proposal(LAMP, D2, 3)], [bom(LAMP, "MAT")],
        [stock("MAT", 0)],
        [{"component_sku": "MAT", "qty": 3, "due_date": D1,
          "confirmed": True}],
    )
    assert balance(result, D1, "MAT")["simulated_closing_usable"] == 3
    assert row(result, D2)["simulated_buildable_units"] == 3
    assert balance(result, D2, "MAT")["simulated_closing_usable"] == 0


def test_late_receipt_cannot_build_missed_mps_date():
    result = run(
        [proposal(LAMP, D1, 2)], [bom(LAMP, "MAT")],
        [stock("MAT", 0)],
        [{"component_sku": "MAT", "qty": 2, "due_date": D2,
          "confirmed": True}],
    )
    assert row(result, D1)["simulated_buildable_units"] == 0
    assert row(result, D1)["known_unbuilt_units"] == 2
    assert balance(result, D2, "MAT")["simulated_closing_usable"] == 2
    assert len(result["feasibility_rows"]) == 1


def test_unconfirmed_receipt_and_snapshot_receipt_are_not_added_again():
    result = run(
        [proposal(LAMP, D1, 3)], [bom(LAMP, "MAT")],
        [stock("MAT", 1)],
        [{"component_sku": "MAT", "qty": 10, "due_date": D1,
          "confirmed": False},
         {"component_sku": "MAT", "qty": 10, "due_date": SNAPSHOT,
          "confirmed": True}],
    )
    assert row(result, D1)["simulated_buildable_units"] == 1
    assert balance(result, D1, "MAT")["confirmed_receipts"] == 0


def test_sufficient_shared_stock_builds_both_without_priority():
    result = run(
        [proposal(LAMP, D1, 1), proposal(CHARGER, D1, 1)],
        [bom(LAMP, "SCR", 4), bom(CHARGER, "SCR", 2)],
        [stock("SCR", 6)],
        lines=[line(LAMP, 1), line(CHARGER, 1)],
    )
    assert (row(result, D1, LAMP)["simulated_buildable_units"],
            row(result, D1, CHARGER)["simulated_buildable_units"]) == (1, 1)
    assert balance(result, D1, "SCR")["simulated_use"] == 6
    assert result["shared_component_conflicts"] == []


def test_scarce_shared_stock_marks_both_products_unresolved_without_consumption():
    result = run(
        [proposal(LAMP, D1, 1), proposal(CHARGER, D1, 2)],
        [bom(LAMP, "SCR", 4), bom(CHARGER, "SCR", 2)],
        [stock("SCR", 6)],
        lines=[line(LAMP, 1), line(CHARGER, 2)],
    )
    assert result["shared_component_conflicts"] == [{
        "date": D1, "component_sku": "SCR", "available_quantity": 6,
        "conflicting_skus": [CHARGER, LAMP],
        "competing_requirements": {CHARGER: 4, LAMP: 4},
    }]
    for sku, proposed in ((LAMP, 1), (CHARGER, 2)):
        item = row(result, D1, sku)
        assert item["simulated_buildable_units"] is None
        assert item["unresolved_units"] == proposed
        assert item["simulated_components_consumed"] == {}
        assert item["simulated_capacity_used"] == 0
    stock_row = balance(result, D1, "SCR")
    assert (stock_row["simulated_use"], stock_row["simulated_closing_usable"],
            stock_row["balance_status"]) == (
                0, 6, "conditional on unresolved allocation",
            )
    assert result["summary"]["total_unresolved_units"] == 3


def test_every_scarce_shared_component_is_reported():
    result = run(
        [proposal(LAMP, D1, 2), proposal(CHARGER, D1, 2)],
        [bom(LAMP, "A"), bom(LAMP, "B"),
         bom(CHARGER, "A"), bom(CHARGER, "B")],
        [stock("A", 3), stock("B", 3)],
        lines=[line(LAMP, 2), line(CHARGER, 2)],
    )
    assert [(c["component_sku"], c["available_quantity"],
             c["competing_requirements"]) for c in result[
                 "shared_component_conflicts"
             ]] == [
                 ("A", 3, {CHARGER: 2, LAMP: 2}),
                 ("B", 3, {CHARGER: 2, LAMP: 2}),
             ]
    assert row(result, D1, LAMP)["simulated_buildable_units"] is None
    assert row(result, D1, CHARGER)["simulated_buildable_units"] is None

def test_shared_conflict_is_invariant_to_proposal_and_bom_input_order():
    proposals = [proposal(LAMP, D1, 1), proposal(CHARGER, D1, 2)]
    base = [bom(LAMP, "SCR", 4), bom(CHARGER, "SCR", 2)]
    args = {"inventory": [stock("SCR", 6)],
            "lines": [line(LAMP, 1), line(CHARGER, 2)]}
    forward = run(proposals, base, **args)
    reverse = run(list(reversed(proposals)), list(reversed(base)), **args)
    assert forward["shared_component_conflicts"] == reverse["shared_component_conflicts"]
    assert forward["feasibility_rows"] == reverse["feasibility_rows"]


def test_disjoint_product_can_build_while_other_products_are_unresolved():
    result = run(
        [proposal(LAMP, D1, 1), proposal(CHARGER, D1, 2),
         proposal(FAN, D1, 1)],
        [bom(LAMP, "SCR", 4), bom(CHARGER, "SCR", 2),
         bom(FAN, "FAN-MAT")],
        [stock("SCR", 6), stock("FAN-MAT", 1)],
        lines=[line(LAMP, 1), line(CHARGER, 2), line(FAN, 1)],
    )
    assert row(result, D1, FAN)["simulated_buildable_units"] == 1
    assert balance(result, D1, "FAN-MAT")["simulated_use"] == 1
    assert row(result, D1, LAMP)["simulated_buildable_units"] is None
    assert row(result, D1, CHARGER)["simulated_buildable_units"] is None


def test_later_use_of_unresolved_shared_stock_remains_unresolved():
    result = run(
        [proposal(LAMP, D1, 1), proposal(CHARGER, D1, 2),
         proposal(LAMP, D2, 1)],
        [bom(LAMP, "SCR", 4), bom(CHARGER, "SCR", 2)],
        [stock("SCR", 6)],
        lines=[line(LAMP, 1), line(CHARGER, 2)],
    )
    later = row(result, D2, LAMP)
    assert later["simulated_buildable_units"] is None
    assert later["reason"] == "prior unresolved component allocation"
    assert balance(result, D2, "SCR")["balance_status"] == (
        "conditional on unresolved allocation"
    )
    assert result["summary"]["total_unresolved_units"] == 4


def test_definite_zero_build_does_not_create_shared_contention():
    result = run(
        [proposal(LAMP, D1, 1), proposal(CHARGER, D1, 1)],
        [bom(LAMP, "SCR", 2), bom(LAMP, "LED"),
         bom(CHARGER, "SCR", 2)],
        [stock("SCR", 2), stock("LED", 0)],
        lines=[line(LAMP, 1), line(CHARGER, 1)],
    )
    assert row(result, D1, LAMP)["simulated_buildable_units"] == 0
    assert row(result, D1, CHARGER)["simulated_buildable_units"] == 1
    assert result["shared_component_conflicts"] == []
    assert balance(result, D1, "SCR")["simulated_use"] == 2


def ecn_case():
    base = [bom(LAMP, "LED-A"), bom(LAMP, "SCR")]
    rev_b = BOMRevision(LAMP, "B", (("LED-B", 1), ("SCR", 1)))
    inventory = [stock("LED-A", 1), stock("LED-B", 1), stock("SCR", 2)]
    draft = ECN("ECN-MPS", LAMP, "A", "B", D3,
                (ECNChangeLine("LED-A", "LED-B", 1, 1),), "hold")
    approved = approve_ecn(
        draft, approval_date=D2, effective_date=D3,
        approved_by="Fictional engineer", base_bom=base,
        proposed_revisions=[rev_b], inventory=inventory,
    )
    return base, rev_b, inventory, approved


def test_ecn_boundary_builds_with_date_specific_complete_bom():
    base, rev_b, inventory, approved = ecn_case()
    result = run(
        [proposal(LAMP, D2, 1), proposal(LAMP, D3, 1)],
        base, inventory, lines=[line(LAMP, 1)],
        proposed_revisions=[rev_b], ecns=[approved],
    )
    assert [(r["production_start"], r["bom_revision"],
             r["simulated_buildable_units"], r["simulated_components_consumed"])
            for r in result["feasibility_rows"]] == [
                (D2, "A", 1, {"LED-A": 1, "SCR": 1}),
                (D3, "B", 1, {"LED-B": 1, "SCR": 1}),
            ]
    assert (balance(result, D3, "LED-A")["simulated_closing_usable"],
            balance(result, D3, "LED-B")["simulated_closing_usable"],
            balance(result, D3, "SCR")["simulated_closing_usable"]) == (0, 0, 0)


@pytest.mark.parametrize("state", ["wip", "released"])
def test_wip_and_released_lots_require_manual_disposition(state):
    base, rev_b, inventory, approved = ecn_case()
    lot = ProductionLot("OLD-LOT", LAMP, 1, SNAPSHOT, state, "A")
    with pytest.raises(ValueError, match="Manual ECN/WIP disposition"):
        run(
            [proposal(LAMP, D3, 1)], base, inventory,
            lines=[line(LAMP, 1)], proposed_revisions=[rev_b],
            ecns=[approved], lots=[lot],
        )


def test_single_new_lot_id_and_revision_are_retained():
    base, rev_b, inventory, approved = ecn_case()
    result = run(
        [proposal(LAMP, D2, 1), proposal(LAMP, D3, 1)],
        base, inventory, lines=[line(LAMP, 1)],
        proposed_revisions=[rev_b], ecns=[approved],
        lots=[ProductionLot("NEW-LOT", LAMP, 2, SNAPSHOT)],
    )
    assert [(r["lot_id"], r["bom_revision"], r["ecn_reference"])
            for r in result["feasibility_rows"]] == [
                ("NEW-LOT", "A", None), ("NEW-LOT", "B", "ECN-MPS"),
            ]


def test_multiple_new_lots_need_dispatch_linkage():
    with pytest.raises(ValueError, match="Lot dispatch priority"):
        run(
            [proposal(LAMP, D1, 2)], [bom(LAMP, "MAT")],
            [stock("MAT", 2)], lines=[line(LAMP, 2)],
            lots=[ProductionLot("L1", LAMP, 1, SNAPSHOT),
                  ProductionLot("L2", LAMP, 1, SNAPSHOT)],
        )


def test_lot_must_exist_before_earliest_positive_start_regardless_of_input_order():
    with pytest.raises(ValueError, match="created after its MPS start"):
        run(
            [proposal(LAMP, D2, 1), proposal(LAMP, D1, 1)],
            [bom(LAMP, "MAT")], [stock("MAT", 2)],
            lines=[line(LAMP, 1)],
            lots=[ProductionLot("LATE-LOT", LAMP, 2, D2)],
        )

def test_stock_hold_requires_manual_review():
    with pytest.raises(ValueError, match="stock holds requires manual review"):
        run(
            [proposal(LAMP, D1, 1)], [bom(LAMP, "MAT")],
            [stock("MAT", 1)], lines=[line(LAMP, 1)],
            stock_holds=[StockHold("MAT", 1, D1, "Fictional owner", SNAPSHOT)],
        )


def test_missing_line_fails_before_feasibility_result():
    with pytest.raises(ValueError, match="No production line"):
        run(
            [proposal(CHARGER, D1, 1)], [bom(CHARGER, "MAT")],
            [stock("MAT", 1)], lines=[line(LAMP, 1)],
        )


def test_simulated_inventory_and_capacity_conservation():
    result = run(
        [proposal(LAMP, D1, 2), proposal(LAMP, D2, 2)],
        [bom(LAMP, "A", 2), bom(LAMP, "B")],
        [stock("A", 7), stock("B", 4)],
        [{"component_sku": "A", "qty": 1, "due_date": D2,
          "confirmed": True}],
        lines=[line(LAMP, 2)],
    )
    assert [r["simulated_buildable_units"]
            for r in result["feasibility_rows"]] == [2, 2]
    for entry in result["simulated_consumption_ledger"]:
        assert entry["opening_usable"] + entry["confirmed_receipts"] - entry[
            "simulated_use"
        ] == entry["simulated_closing_usable"] >= 0
    for entry in result["feasibility_rows"]:
        assert entry["simulated_capacity_used"] <= entry["available_capacity"]
        assert entry["proposed_mps_units"] == (
            entry["simulated_buildable_units"] + entry["known_unbuilt_units"]
            + entry["unresolved_units"]
        )
    assert (balance(result, D2, "A")["simulated_closing_usable"],
            balance(result, D2, "B")["simulated_closing_usable"]) == (0, 0)


def test_proposed_mps_finished_goods_are_not_recast_as_actual_completion():
    from factoryflow.mps import FinishedGoodsOpening

    proposed = [proposal(LAMP, D1, 3)]
    fg_rows = calculate_mps(
        [LAMP], [FinishedGoodsOpening(LAMP, 0)], [], [], proposed, D1, D1,
    )
    result = run(proposed, [bom(LAMP, "MAT")], [stock("MAT", 1)])
    assert fg_rows[0]["proposed_mps_completion"] == 3
    assert fg_rows[0]["projected_fg_balance"] == 3
    assert row(result, D1)["simulated_buildable_units"] == 1
    assert row(result, D1)["known_unbuilt_units"] == 2
    assert fg_rows[0]["projected_fg_balance"] == 3
    assert "actual_production" not in result
    assert "finished_goods_receipts" not in result

def test_existing_mps_mrp_and_ecn_results_are_preserved():
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
            mrp["LED-100"]["net_shortage"],
            mrp["SCR-120"]["gross_required"],
            mrp["SCR-120"]["net_shortage"]) == (200, 40, 1000, 100)
    base, rev_b, inventory, approved = ecn_case()
    old_ecn = calculate_ecn_plan(
        {LAMP: 2}, base, inventory, [], SNAPSHOT, D2, D3,
        proposed_revisions=[rev_b], ecns=[approved],
        lines=[line(LAMP, 1)],
    )
    assert [(r["date"], r["bom_revision"], r["actual_buildable_units"])
            for r in old_ecn["daily_schedule"]] == [
                (D2, "A", 1), (D3, "B", 1),
            ]
