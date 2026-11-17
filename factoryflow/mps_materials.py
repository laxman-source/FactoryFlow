"""Dated, nominal component requirements from proposed MPS production starts.

This simulation uses the approved BOM revision active on production start.
It does not turn proposed completions into actual output, material coverage into
whole-unit build feasibility, or purchase advice into confirmed supply.
Unresolved released/WIP lot disposition and stock holds fail closed.
"""

from collections import defaultdict

from factoryflow.ecn import (
    ProductionLot, _day, build_revisions, resolve_revision,
    validate_ecn_calendar,
)
from factoryflow.material_timeline import calculate_material_timeline
from factoryflow.mps import ProposedMPSCompletion


def calculate_mps_materials(
    proposed_completions, base_bom, inventory, receipts, as_of, planning_end, *,
    proposed_revisions=(), ecns=(), lots=(), stock_holds=(),
):
    """Explode dated MPS starts and run one shared component ledger.

    Provisional rule: direct components are needed on production_start, using
    the approved BOM revision active that day. MPS-1/MPS-2 currently requires
    production_start == completion_date; this integration enforces the same
    boundary while retaining both dates in its output.

    A timeline's nominal coverage is only a component-level projection. It
    does not imply complete component sets, feasible builds, actual component
    issues, or actual finished goods. Unmet dated needs remain outstanding;
    later receipts do not erase them or move the proposed production date.
    """
    _day(as_of, "Planning snapshot")
    _day(planning_end, "Planning end")
    if planning_end < as_of:
        raise ValueError("Planning end cannot precede the snapshot")
    for label, records in (
        ("Proposed completions", proposed_completions),
        ("Base BOM", base_bom),
        ("Inventory", inventory),
        ("Receipts", receipts),
        ("Proposed revisions", proposed_revisions),
        ("ECNs", ecns),
        ("Production lots", lots),
        ("Stock holds", stock_holds),
    ):
        if not isinstance(records, (list, tuple)):
            raise ValueError(f"{label} must be a list or tuple")
    if stock_holds:
        raise ValueError("MPS material planning with stock holds requires manual review")

    revisions = build_revisions(base_bom, proposed_revisions)
    masters = validate_ecn_calendar(ecns, revisions, inventory)
    proposal_keys = set()
    proposals = []
    for proposal in proposed_completions:
        if not isinstance(proposal, ProposedMPSCompletion):
            raise ValueError("Proposed completions must be ProposedMPSCompletion records")
        if not as_of <= proposal.production_start <= planning_end:
            raise ValueError("Production start must be within the planning horizon")
        if not as_of <= proposal.completion_date <= planning_end:
            raise ValueError("Completion date must be within the planning horizon")
        if proposal.production_start != proposal.completion_date:
            raise ValueError("This simulation requires same-day production start and completion")
        key = proposal.completion_date, proposal.finished_sku
        if key in proposal_keys:
            raise ValueError(f"Duplicate proposed MPS completion bucket: {key}")
        proposal_keys.add(key)
        if proposal.qty and (proposal.finished_sku, "A") not in revisions:
            raise ValueError(f"No base BOM for finished product {proposal.finished_sku}")
        revision, ecn_reference = resolve_revision(
            proposal.finished_sku, proposal.production_start, ecns,
        )
        selected = revisions.get((proposal.finished_sku, revision))
        if proposal.qty and selected is None:
            raise ValueError(
                f"No approved BOM revision {revision} for {proposal.finished_sku}"
            )
        proposals.append((proposal, selected, revision, ecn_reference))

    planned_skus = {proposal.finished_sku for proposal, _, _, _ in proposals
                    if proposal.qty}
    for lot in lots:
        if not isinstance(lot, ProductionLot):
            raise ValueError("Production lots must be ProductionLot records")
        if lot.finished_sku in planned_skus and lot.qty and lot.state != "new":
            raise ValueError(
                f"Manual ECN/WIP disposition review required for lot {lot.order_id}; "
                "proposed MPS quantities are not linked to released or WIP lots"
            )

    mps_rows = []
    requirement_rows = []
    grouped = defaultdict(int)
    for proposal, selected, revision, ecn_reference in sorted(
        proposals, key=lambda item: (
            item[0].production_start, item[0].finished_sku,
        ),
    ):
        mps_rows.append({
            "finished_sku": proposal.finished_sku,
            "production_start": proposal.production_start,
            "completion_date": proposal.completion_date,
            "proposed_mps_qty": proposal.qty,
            "bom_revision": revision,
            "ecn_reference": ecn_reference,
        })
        if not proposal.qty:
            continue
        for component, per_unit in selected.usage.items():
            if component not in masters:
                raise ValueError(f"Missing inventory master for BOM component {component}")
            required = proposal.qty * per_unit
            requirement_rows.append({
                "requirement_date": proposal.production_start,
                "finished_sku": proposal.finished_sku,
                "production_start": proposal.production_start,
                "completion_date": proposal.completion_date,
                "proposed_mps_qty": proposal.qty,
                "bom_revision": revision,
                "ecn_reference": ecn_reference,
                "component_sku": component,
                "qty_per_unit": per_unit,
                "gross_required": required,
            })
            grouped[proposal.production_start, component] += required

    daily_requirements = [
        {"requirement_date": day, "component_sku": component,
         "gross_required": qty}
        for (day, component), qty in sorted(grouped.items())
    ]
    # The existing timeline owns opening-stock, protected-stock, confirmed
    # receipt, same-day arrival, and chronological nonnegative balance rules.
    timeline = calculate_material_timeline(
        inventory, receipts,
        [{"date": row["requirement_date"], "component_sku": row["component_sku"],
          "qty": row["gross_required"]} for row in daily_requirements],
        as_of, planning_end,
    )
    outstanding = defaultdict(int)
    ledger = []
    shortages = []
    for row in timeline:
        sku = row["component_sku"]
        outstanding[sku] += row["unmet_need"]
        entry = {
            "date": row["date"],
            "component_sku": sku,
            "opening_usable": row["opening_balance"],
            "confirmed_receipts": row["receipts"],
            "gross_required": row["requirement"],
            "nominal_covered": row["consumption"],
            "material_shortage": row["unmet_need"],
            "outstanding_requirement": outstanding[sku],
            "projected_closing_usable": row["closing_balance"],
        }
        ledger.append(entry)
        if entry["material_shortage"]:
            shortages.append({
                "requirement_date": entry["date"],
                "component_sku": sku,
                "material_shortage": entry["material_shortage"],
                "outstanding_requirement": entry["outstanding_requirement"],
            })
    return {
        "scope": "nominal proposed MPS material requirements",
        "mps_proposals": mps_rows,
        "material_requirements": requirement_rows,
        "daily_component_requirements": daily_requirements,
        "component_ledger": ledger,
        "shortages": shortages,
    }
