"""Whole-unit feasibility for dated, proposed MPS production.

The legacy schedulers carry work forward and allocate shared parts by SKU.
This separate simulation respects fixed MPS dates and stops short of an
unapproved dispatch decision when shared stock is scarce.
"""

from collections import defaultdict
from datetime import timedelta

from factoryflow.capacity import PRODUCTION_LINES, calculate_capacity_plan
from factoryflow.ecn import ProductionLot
from factoryflow.mps_materials import calculate_mps_materials


def calculate_mps_feasibility(
    proposed_completions, base_bom, inventory, receipts, as_of, planning_end, *,
    proposed_revisions=(), ecns=(), lines=PRODUCTION_LINES, lots=(),
    stock_holds=(), overtime_by_sku=None, downtime_by_sku=None,
):
    """Return nominal needs and a distinct, conservative build simulation.

    A resolved build is the minimum of proposed units, that date's line
    capacity, and complete sets from the shared usable-component pool. Only
    whole simulated builds consume components and capacity. No unfinished MPS
    quantity is moved to another date.

    If individually possible products need more of a shared component than
    is available together, no product priority is inferred. Those quantities
    are unresolved (buildable_units=None), not reported as zero feasible.
    Their possible component use makes dependent later balances conditional;
    later proposals using those components also remain unresolved. Products
    using disjoint components may still be simulated.
    """
    nominal = calculate_mps_materials(
        proposed_completions, base_bom, inventory, receipts, as_of, planning_end,
        proposed_revisions=proposed_revisions, ecns=ecns, lots=lots,
        stock_holds=stock_holds,
    )
    if not isinstance(lines, (list, tuple)):
        raise ValueError("Production lines must be a list or tuple")
    if not isinstance(lots, (list, tuple)):
        raise ValueError("Production lots must be a list or tuple")

    proposals = nominal["mps_proposals"]
    by_day = defaultdict(list)
    quantities_by_sku = defaultdict(int)
    first_start = {}
    for row in proposals:
        sku = row["finished_sku"]
        by_day[row["production_start"]].append(row)
        if row["proposed_mps_qty"]:
            quantities_by_sku[sku] += row["proposed_mps_qty"]
            first_start[sku] = min(
                first_start.get(sku, row["production_start"]),
                row["production_start"],
            )

    # A single new lot per product can be traced across its MPS dates. Multiple
    # ready lots need a reviewed dispatch/linkage rule; released/WIP lots were
    # already rejected by the dated material contract.
    lots_by_sku = defaultdict(list)
    lot_ids = set()
    for lot in lots:
        if not isinstance(lot, ProductionLot):
            raise ValueError("Production lots must be ProductionLot records")
        if lot.order_id in lot_ids:
            raise ValueError(f"Duplicate production lot ID: {lot.order_id}")
        lot_ids.add(lot.order_id)
        if lot.qty:
            lots_by_sku[lot.finished_sku].append(lot)
    for sku, product_lots in lots_by_sku.items():
        if sku not in quantities_by_sku or not quantities_by_sku[sku]:
            raise ValueError(f"Lot for {sku} has no proposed MPS quantity")
        if len(product_lots) != 1:
            raise ValueError(f"Lot dispatch priority is undefined for {sku}")
        lot = product_lots[0]
        if lot.state != "new":
            raise ValueError(f"Manual disposition required for lot {lot.order_id}")
        if lot.qty != quantities_by_sku[sku]:
            raise ValueError(f"Lot quantity must equal proposed MPS units for {sku}")
        if lot.created_date > first_start[sku]:
            raise ValueError(f"Lot {lot.order_id} was created after its MPS start")
    lot_id_by_sku = {sku: product_lots[0].order_id
                     for sku, product_lots in lots_by_sku.items()}

    usage = defaultdict(dict)
    for row in nominal["material_requirements"]:
        usage[row["requirement_date"], row["finished_sku"]][
            row["component_sku"]
        ] = row["qty_per_unit"]

    # The nominal ledger supplies the existing validated opening and confirmed
    # receipt timing rules. Its nominal coverage/closing balances are never used
    # as the simulated-consumption balances below.
    components = sorted({row["component_sku"]
                         for row in nominal["component_ledger"]})
    balances = {row["component_sku"]: row["opening_usable"]
                for row in nominal["component_ledger"] if row["date"] == as_of}
    receipt_by_day = {
        (row["date"], row["component_sku"]): row["confirmed_receipts"]
        for row in nominal["component_ledger"]
    }

    feasibility_rows = []
    consumption_ledger = []
    conflicts = []
    uncertain_components = set()
    for offset in range((planning_end - as_of).days + 1):
        day = as_of + timedelta(days=offset)
        opening_today = balances.copy()
        received = {component: receipt_by_day[day, component]
                    for component in components}
        for component in components:
            balances[component] += received[component]
        used_today = defaultdict(int)

        capacity_rows = calculate_capacity_plan(
            {}, lines, day, day, overtime_by_sku=overtime_by_sku,
            downtime_by_sku=downtime_by_sku,
        )
        capacity = {row["finished_sku"]: row["available_capacity"]
                    for row in capacity_rows}
        day_proposals = {row["finished_sku"]: row for row in by_day[day]}
        unknown = set(day_proposals) - set(capacity)
        if unknown:
            raise ValueError(
                f"No production line for finished product {', '.join(sorted(unknown))}"
            )

        candidates = {}
        potential = {}
        for sku, proposal in day_proposals.items():
            candidates[sku] = min(proposal["proposed_mps_qty"], capacity[sku])
            component_limits = [
                balances[component] // per_unit
                for component, per_unit in usage[day, sku].items()
            ]
            potential[sku] = min(
                candidates[sku], min(component_limits, default=0),
            )

        unresolved = {
            sku for sku in day_proposals
            if potential[sku] and set(usage[day, sku]) & uncertain_components
        }
        reasons = {sku: "prior unresolved component allocation"
                   for sku in unresolved}

        # A conflict exists only when two or more products could individually
        # build units but their combined component claims exceed available stock.
        # Freeze eligibility for this pass so every scarce shared component is
        # reported, even when the first conflict already marked its SKUs.
        eligible = {
            sku for sku in day_proposals if sku not in unresolved and potential[sku]
        }
        for component in components:
            claimants = sorted(
                sku for sku in eligible if component in usage[day, sku]
            )
            if len(claimants) < 2:
                continue
            claims = {
                sku: potential[sku] * usage[day, sku][component]
                for sku in claimants
            }
            if sum(claims.values()) > balances[component]:
                unresolved.update(claimants)
                for sku in claimants:
                    reasons[sku] = "shared component allocation unresolved"
                conflicts.append({
                    "date": day,
                    "component_sku": component,
                    "available_quantity": balances[component],
                    "conflicting_skus": claimants,
                    "competing_requirements": claims,
                })

        # A product depending on stock whose allocation is unresolved cannot
        # consume that stock here. Propagate uncertainty across its complete BOM.
        today_uncertain = uncertain_components.copy()
        for sku in unresolved:
            today_uncertain.update(usage[day, sku])
        changed = True
        while changed:
            changed = False
            for sku in day_proposals:
                if sku in unresolved or not potential[sku]:
                    continue
                if set(usage[day, sku]) & today_uncertain:
                    unresolved.add(sku)
                    reasons[sku] = "dependent on unresolved component allocation"
                    today_uncertain.update(usage[day, sku])
                    changed = True
        uncertain_components = today_uncertain

        for sku in sorted(day_proposals):
            proposal = day_proposals[sku]
            proposed = proposal["proposed_mps_qty"]
            cap_limited = candidates[sku]
            if sku in unresolved:
                built = None
                unresolved_units = cap_limited
                known_unbuilt = proposed - cap_limited
                consumed = {}
                material_unbuilt = None
                status = "unresolved"
            else:
                built = potential[sku]
                unresolved_units = 0
                known_unbuilt = proposed - built
                consumed = {
                    component: built * per_unit
                    for component, per_unit in usage[day, sku].items()
                    if built
                }
                material_unbuilt = cap_limited - built
                status = "resolved"
                for component, qty in consumed.items():
                    balances[component] -= qty
                    used_today[component] += qty
            feasibility_rows.append({
                "production_start": day,
                "completion_date": proposal["completion_date"],
                "finished_sku": sku,
                "lot_id": lot_id_by_sku.get(sku),
                "bom_revision": proposal["bom_revision"],
                "ecn_reference": proposal["ecn_reference"],
                "proposed_mps_units": proposed,
                "available_capacity": capacity[sku],
                "capacity_limited_units": cap_limited,
                "simulated_buildable_units": built,
                "capacity_unbuilt_units": proposed - cap_limited,
                "material_unbuilt_units": material_unbuilt,
                "known_unbuilt_units": known_unbuilt,
                "unresolved_units": unresolved_units,
                "status": status,
                "reason": reasons.get(sku),
                "simulated_components_consumed": consumed,
                "simulated_capacity_used": built if built is not None else 0,
            })

        for component in components:
            consumption_ledger.append({
                "date": day,
                "component_sku": component,
                "opening_usable": opening_today[component],
                "confirmed_receipts": received[component],
                "simulated_use": used_today[component],
                "simulated_closing_usable": balances[component],
                "balance_status": (
                    "conditional on unresolved allocation"
                    if component in uncertain_components else "resolved"
                ),
            })

    return {
        "scope": "simulated whole-unit MPS feasibility",
        "nominal_material_plan": nominal,
        "feasibility_rows": feasibility_rows,
        "simulated_consumption_ledger": consumption_ledger,
        "shared_component_conflicts": conflicts,
        "summary": {
            "total_proposed_mps_units": sum(
                row["proposed_mps_units"] for row in feasibility_rows
            ),
            "total_simulated_buildable_units": sum(
                row["simulated_buildable_units"] or 0
                for row in feasibility_rows
            ),
            "total_known_unbuilt_units": sum(
                row["known_unbuilt_units"] for row in feasibility_rows
            ),
            "total_unresolved_units": sum(
                row["unresolved_units"] for row in feasibility_rows
            ),
        },
    }
