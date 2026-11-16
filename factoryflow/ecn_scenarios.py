"""Fictional Phase 5A scenario inputs for the Streamlit ECN explorer.

These are sample records only. All planning calculations stay in calculate_ecn_plan.
"""

from datetime import date

from factoryflow.ecn import (
    BOMRevision, ECN, ECNChangeLine, StockHold, approve_ecn, cancel_ecn,
)

LAMP = "FG-LAMP-01"
SNAPSHOT = date(2026, 11, 30)
D1, D2, D3, D4 = (date(2026, 12, day) for day in range(1, 5))

SCENARIO_NAMES = {
    "A": "A — Draft change",
    "B": "B — Approved before effect",
    "C": "C — Production spans effect",
    "D": "D — New-part shortage",
    "E": "E — Excess old stock on hold",
    "F": "F — New-part receipt arrives late",
    "G": "G — Cancelled change",
    "H": "H — Conflicting approvals",
}

SCENARIO_NOTES = {
    "A": "A draft cannot activate Revision B. All eight lamps use LED-100.",
    "B": "Approval does not switch production before December 3.",
    "C": "Production dates select Revision A on December 1–2 and B on December 3–4.",
    "D": "Only one LED-101 is available. Purchase advice is not a confirmed receipt.",
    "E": "Eight old boards remain physically present and held; no stock is scrapped.",
    "F": "The December 4 receipt cannot support production on December 3.",
    "G": "A pre-effective cancellation leaves Revision A active.",
    "H": "Two approved revisions claim the same day. The engine rejects the plan.",
}


def _stock(old=8, new=4):
    return [
        {
            "sku": sku, "name": sku, "on_hand": qty, "reserved": 0,
            "safety_stock": 0, "lead_days": 7, "pack_size": 5,
        }
        for sku, qty in (
            ("LED-100", old), ("LED-101", new), ("HSG", 8),
            ("SCR", 32), ("ADP", 8),
        )
    ]


def scenario_inputs(code):
    """Return fresh inputs matching independently calculated design cases A–H."""
    if code not in SCENARIO_NAMES:
        raise ValueError(f"Unknown ECN scenario: {code}")

    base_bom = [
        {"finished_sku": LAMP, "component_sku": sku, "qty_per_unit": qty}
        for sku, qty in (
            ("LED-100", 1), ("HSG", 1), ("SCR", 4), ("ADP", 1),
        )
    ]
    revision_b = BOMRevision(
        LAMP, "B",
        (("LED-101", 1), ("HSG", 1), ("SCR", 4), ("ADP", 1)),
    )
    inventory = _stock(old=12 if code == "E" else 8,
                       new=1 if code == "D" else 0 if code == "F" else 4)
    draft = ECN(
        "ECN-001", LAMP, "A", "B", D3,
        (ECNChangeLine("LED-100", "LED-101", 1, 1),), "hold",
    )
    revisions = [revision_b]
    receipts = []
    holds = []
    if code == "E":
        holds.append(StockHold("LED-100", 8, D3, "Fictional approver", D2))
    if code == "F":
        receipts.append({
            "component_sku": "LED-101", "qty": 4,
            "due_date": D4, "confirmed": True,
        })

    if code == "A":
        ecns = [draft]
    else:
        approved = approve_ecn(
            draft, approval_date=D2, effective_date=D3,
            approved_by="Fictional engineering approver",
            base_bom=base_bom, proposed_revisions=revisions,
            inventory=inventory,
        )
        ecns = [approved]
        if code == "G":
            ecns = [cancel_ecn(
                approved, cancellation_date=D2,
                reason="Fictional change withdrawn",
            )]
        if code == "H":
            revision_c = BOMRevision(
                LAMP, "C",
                (("LED-102", 1), ("HSG", 1), ("SCR", 4), ("ADP", 1)),
            )
            inventory.append({
                "sku": "LED-102", "name": "LED-102", "on_hand": 4,
                "reserved": 0, "safety_stock": 0,
                "lead_days": 7, "pack_size": 5,
            })
            other = ECN(
                "ECN-002", LAMP, "A", "C", D3,
                (ECNChangeLine("LED-100", "LED-102", 1, 1),), "hold",
            )
            revisions.append(revision_c)
            ecns.append(approve_ecn(
                other, approval_date=D2, effective_date=D3,
                approved_by="Fictional engineering approver",
                base_bom=base_bom, proposed_revisions=[revision_c],
                inventory=inventory,
            ))

    return {
        "demand": {LAMP: 4 if code == "B" else 8},
        "base_bom": base_bom,
        "inventory": inventory,
        "receipts": receipts,
        "as_of": SNAPSHOT,
        "production_start": D1,
        "production_end": D2 if code == "B" else D4,
        "proposed_revisions": revisions,
        "ecns": ecns,
        "stock_holds": holds,
        "lines": [
            {"finished_sku": LAMP, "name": "Lamp line", "daily_capacity": 2},
        ],
    }
