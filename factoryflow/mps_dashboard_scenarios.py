"""Fictional, selectable inputs for the MPS dashboard.

Every component opening is a December 1 snapshot. Earlier demo receipts are
rolled into that snapshot once and are not passed again as dated supply.
These examples are planning exercises, not factory transactions.
"""

from copy import deepcopy
from datetime import date

from factoryflow.capacity import PRODUCTION_LINES
from factoryflow.data import BOM, INVENTORY, RECEIPTS
from factoryflow.ecn import BOMRevision, ECN, ECNChangeLine, ProductionLot, approve_ecn
from factoryflow.mps import ProposedMPSCompletion
from factoryflow.mps_data import (
    DEMO_FINISHED_SKUS, DEMO_FG_OPENING, DEMO_FIRM_ORDERS,
    DEMO_FORECASTS, DEMO_MPS_AS_OF, DEMO_MPS_END, DEMO_MPS_COMPLETIONS,
)

SCENARIO_NAMES = {
    "baseline": "Base two-product plan",
    "material": "Material shortage",
    "capacity": "Daily capacity restriction",
    "conflict": "Shared-component allocation conflict",
    "revision": "Approved revision change",
    "wip": "Unsupported WIP disposition",
}

SCENARIO_NOTES = {
    "baseline": "Both products use fictional proposed quantities and complete component sets.",
    "material": "Limited LED-100 permits fewer whole lamps than proposed.",
    "capacity": "The lamp line cannot build all proposed units on December 1.",
    "conflict": "The two products compete for scarce screws; allocation needs a human decision.",
    "revision": "Approved Revision B applies to lamp starts from December 2; new LED stock is limited.",
    "wip": "A WIP lot has no authorized MPS linkage or disposition rule.",
}


def scenario_inputs(code):
    """Return independent inputs for existing MPS and feasibility engines."""
    if code not in SCENARIO_NAMES:
        raise ValueError(f"Unknown MPS scenario: {code}")

    inventory = deepcopy(INVENTORY)
    receipts = deepcopy(RECEIPTS)
    for receipt in receipts:
        if receipt["due_date"] < DEMO_MPS_AS_OF and receipt.get("confirmed", True):
            item = next(row for row in inventory if row["sku"] == receipt["component_sku"])
            item["on_hand"] += receipt["qty"]
    receipts = [row for row in receipts if row["due_date"] > DEMO_MPS_AS_OF]
    proposals = list(DEMO_MPS_COMPLETIONS)
    revisions = []
    ecns = []
    lots = []

    if code == "material":
        next(row for row in inventory if row["sku"] == "LED-100")["on_hand"] = 18
    elif code == "capacity":
        proposals[0] = ProposedMPSCompletion(
            "FG-LAMP-01", date(2026, 12, 1), date(2026, 12, 1), 90,
        )
    elif code == "conflict":
        screws = next(row for row in inventory if row["sku"] == "SCR-120")
        screws["on_hand"] = 20
        screws["safety_stock"] = 0
    elif code == "revision":
        inventory.append({
            "sku": "LED-101", "name": "Revised lamp LED board",
            "on_hand": 8, "reserved": 0, "safety_stock": 0,
            "lead_days": 7, "pack_size": 5,
        })
        revisions = [BOMRevision(
            "FG-LAMP-01", "B",
            (("LED-101", 1), ("LAM-HSG-110", 1), ("SCR-120", 4), ("ADP-130", 1)),
        )]
        draft = ECN(
            "MPS-ECN-01", "FG-LAMP-01", "A", "B", date(2026, 12, 2),
            (ECNChangeLine("LED-100", "LED-101", 1, 1),), "use-up",
        )
        ecns = [approve_ecn(
            draft, approval_date=date(2026, 12, 1),
            effective_date=date(2026, 12, 2),
            approved_by="Fictional engineering approver",
            base_bom=BOM, proposed_revisions=revisions, inventory=inventory,
        )]
    elif code == "wip":
        lots = [ProductionLot(
            "FICTIONAL-WIP-01", "FG-LAMP-01", 30,
            date(2026, 11, 30), "wip", "A",
        )]

    return {
        "finished_skus": DEMO_FINISHED_SKUS,
        "fg_opening": DEMO_FG_OPENING,
        "firm_orders": DEMO_FIRM_ORDERS,
        "forecasts": DEMO_FORECASTS,
        "proposals": tuple(proposals),
        "as_of": DEMO_MPS_AS_OF,
        "planning_end": DEMO_MPS_END,
        "base_bom": deepcopy(BOM),
        "component_inventory": inventory,
        "receipts": receipts,
        "proposed_revisions": revisions,
        "ecns": ecns,
        "lots": lots,
        "lines": deepcopy(PRODUCTION_LINES),
    }

