"""Revision-aware, dated manufacturing planning without changing legacy engines.

All output is simulated. Purchase advice is never converted into a receipt, and
released or WIP lots are never silently switched to another BOM revision.
"""

from collections import defaultdict
from collections.abc import Mapping
from datetime import timedelta

from factoryflow.capacity import PRODUCTION_LINES, calculate_capacity_plan
from factoryflow.ecn import (
    ProductionLot, StockHold, _code, _day, _quantity,
    build_revisions, resolve_revision, validate_ecn_calendar,
)
from factoryflow.material_timeline import calculate_material_timeline


def _lots_for_demand(demand, lots, as_of, production_end, revisions):
    if lots is None:
        lots = [ProductionLot(f"PLAN-{sku}", sku, qty, as_of)
                for sku, qty in demand.items()]
    elif not isinstance(lots, (list, tuple)):
        raise ValueError("Production lots must be a list or tuple")
    seen, quantities = set(), defaultdict(int)
    for lot in lots:
        if not isinstance(lot, ProductionLot):
            raise ValueError("Production lots must be ProductionLot records")
        if lot.order_id in seen:
            raise ValueError(f"Duplicate production order ID: {lot.order_id}")
        seen.add(lot.order_id)
        if lot.finished_sku not in demand:
            raise ValueError(f"Lot refers to unknown demand product: {lot.finished_sku}")
        if lot.created_date > production_end:
            raise ValueError(f"Order {lot.order_id} was created after the production window")
        if lot.pinned_revision is not None and (lot.finished_sku, lot.pinned_revision) not in revisions:
            raise ValueError(f"Unknown pinned BOM revision for {lot.order_id}")
        quantities[lot.finished_sku] += lot.qty
    if any(quantities[sku] != qty for sku, qty in demand.items()):
        raise ValueError("Production lot quantities must equal product demand")
    return list(lots)


def _hold_events(stock_holds, masters, as_of, production_end):
    if not isinstance(stock_holds, (list, tuple)):
        raise ValueError("Stock holds must be a list or tuple")
    events = defaultdict(int)
    for hold in stock_holds:
        if not isinstance(hold, StockHold):
            raise ValueError("Stock holds must be authorized StockHold records")
        if hold.component_sku not in masters:
            raise ValueError(f"Hold refers to unknown component: {hold.component_sku}")
        if not as_of <= hold.effective_date <= production_end:
            raise ValueError("Hold effective date must fall within the planning window")
        events[hold.effective_date, hold.component_sku] += hold.qty
    return events


def _capacity_by_day(lines, start, end, overtime, downtime):
    capacities = {}
    for offset in range((end - start).days + 1):
        day = start + timedelta(days=offset)
        capacities[day] = {
            row["finished_sku"]: row["available_capacity"]
            for row in calculate_capacity_plan(
                {}, lines, day, day,
                overtime_by_sku=overtime, downtime_by_sku=downtime,
            )
        }
    return capacities


def _check_lot_contention(lots, remaining, sku, revision, day):
    ready = [lot for lot in lots if lot.finished_sku == sku
             and remaining[lot.order_id] and lot.created_date <= day
             and lot.state != "wip"
             and (lot.state != "released" or lot.pinned_revision == revision)]
    if len(ready) > 1:
        raise ValueError(
            f"Lot dispatch priority is undefined for {sku} on {day}; "
            "provide non-overlapping ready lots or a reviewed dispatch rule"
        )


def _nominal_requirements(lots, products, revisions, active, capacities):
    """Date requested work by line capacity, before considering material supply."""
    remaining = {lot.order_id: lot.qty for lot in lots}
    requirements = []
    for day, daily_capacity in capacities.items():
        for sku in products:
            revision, ecn_reference = active[day, sku]
            selected = revisions.get((sku, revision))
            usage = selected.usage if selected is not None else {}
            capacity = daily_capacity[sku]
            if capacity:
                _check_lot_contention(lots, remaining, sku, revision, day)
            for lot in lots:
                if (lot.finished_sku != sku or not remaining[lot.order_id]
                        or lot.created_date > day):
                    continue
                if lot.state == "wip" or (lot.state == "released" and
                                          lot.pinned_revision != revision):
                    continue
                planned = min(remaining[lot.order_id], capacity)
                remaining[lot.order_id] -= planned
                capacity -= planned
                for component, per_unit in usage.items():
                    if planned:
                        requirements.append({
                            "date": day,
                            "finished_sku": sku,
                            "order_id": lot.order_id,
                            "bom_revision": revision,
                            "ecn_reference": ecn_reference,
                            "planned_units": planned,
                            "component_sku": component,
                            "qty": planned * per_unit,
                        })
    return requirements


def _requirement_ledger(masters, receipts_by_day, opening, holds_by_day,
                        requirements, as_of, end):
    required = defaultdict(int)
    for row in requirements:
        required[row["date"], row["component_sku"]] += row["qty"]
    # Keep enough nominal stock for future authorized holds after accounting
    # for confirmed receipts that will arrive before each hold date.
    reserve_after = {}
    future_hold_need = {sku: 0 for sku in masters}
    for offset in range((end - as_of).days, -1, -1):
        day = as_of + timedelta(days=offset)
        for sku in masters:
            reserve_after[day, sku] = future_hold_need[sku]
            future_hold_need[sku] = max(
                0, future_hold_need[sku] + holds_by_day[day, sku]
                - receipts_by_day[day, sku],
            )
    balances = opening.copy()
    ledger = []
    for offset in range((end - as_of).days + 1):
        day = as_of + timedelta(days=offset)
        for sku in masters:
            before = balances[sku]
            received = receipts_by_day[day, sku]
            held = holds_by_day[day, sku]
            available = before + received
            if held > available:
                raise ValueError(f"Stock hold exceeds usable {sku} on {day}")
            available -= held
            need = required[day, sku]
            used = min(need, max(0, available - reserve_after[day, sku]))
            balances[sku] = available - used
            ledger.append({
                "date": day, "component_sku": sku,
                "opening_usable": before, "confirmed_receipts": received,
                "authorized_hold": held, "requirement": need,
                "simulated_coverage": used, "unmet_need": need - used,
                "closing_usable": balances[sku],
            })
    return ledger


def _purchase_advice(requirement_ledger, masters, as_of):
    shortages = defaultdict(int)
    first_shortage = {}
    for row in requirement_ledger:
        qty = row["unmet_need"]
        if qty:
            sku = row["component_sku"]
            shortages[sku] += qty
            first_shortage.setdefault(sku, row["date"])
    advice = []
    for sku in masters:
        shortage = shortages[sku]
        if not shortage:
            continue
        master = masters[sku]
        pack = master["pack_size"]
        latest = first_shortage[sku] - timedelta(days=master["lead_days"])
        advice.append({
            "component_sku": sku,
            "dated_shortage": shortage,
            "first_shortage_date": first_shortage[sku],
            "suggested_order_qty": ((shortage + pack - 1) // pack) * pack,
            "lead_days": master["lead_days"],
            "latest_order_date": latest,
            "status": "Order now" if as_of <= latest else "At risk: expedite",
        })
    return advice


def calculate_ecn_plan(
    demand, base_bom, inventory, receipts, as_of, production_start, production_end, *,
    proposed_revisions=(), ecns=(), lines=PRODUCTION_LINES, lots=None,
    stock_holds=(), overtime_by_sku=None, downtime_by_sku=None,
):
    """Simulate one window with a day-specific BOM and one shared stock ledger.

    `base_bom` is the existing unversioned Revision A list. Proposed revisions
    are BOMRevision records. Draft/cancelled ECNs do not activate them. Lots in
    product priority stays ascending SKU as in the Phase 4D scheduler. If two
    ready lots of one product compete, the plan fails until a dispatch rule is
    supplied outside this engine. WIP is held for review.

    Material requirements are nominal dated needs based on capacity before
    supply is applied. `purchase_advice` describes on-time shortages in that
    requirement stream, not guaranteed extra output or confirmed deliveries.
    `as_of` dates the inventory snapshot; supplied ECN statuses are scenario
    inputs, not a reconstruction of approvals known at that snapshot.
    """
    _day(as_of, "Inventory snapshot")
    _day(production_start, "Production start")
    _day(production_end, "Production end")
    if production_start < as_of or production_end < production_start:
        raise ValueError("Production window must follow the inventory snapshot")
    if not isinstance(demand, Mapping):
        raise ValueError("Demand must be a mapping from finished SKU to whole units")
    for sku, qty in demand.items():
        _code(sku, "Demand finished SKU")
        _quantity(qty, f"Demand for {sku}")
    if not isinstance(receipts, (list, tuple)):
        raise ValueError("Receipts must be a list or tuple")
    if not isinstance(ecns, (list, tuple)):
        raise ValueError("ECNs must be a list or tuple")
    revisions = build_revisions(base_bom, proposed_revisions)
    masters = validate_ecn_calendar(ecns, revisions, inventory)
    for sku, qty in demand.items():
        if qty and (sku, "A") not in revisions:
            raise ValueError(f"No base BOM for finished product {sku}")
    capacity_plan = calculate_capacity_plan(
        demand, lines, production_start, production_end,
        overtime_by_sku=overtime_by_sku, downtime_by_sku=downtime_by_sku,
    )
    products = sorted(row["finished_sku"] for row in capacity_plan)
    for sku in products:
        if demand.get(sku, 0) and (sku, "A") not in revisions:
            raise ValueError(f"No base BOM for production line {sku}")
    production_lots = _lots_for_demand(demand, lots, as_of, production_end, revisions)
    holds_by_day = _hold_events(stock_holds, masters, as_of, production_end)

    # Phase 4A remains the source of snapshot, protected-stock, confirmation,
    # and receipt timing rules. No planned consumption is passed to it here.
    supply = calculate_material_timeline(inventory, receipts, [], as_of, production_end)
    opening = {row["component_sku"]: row["opening_balance"]
               for row in supply if row["date"] == as_of}
    receipts_by_day = defaultdict(int, {
        (row["date"], row["component_sku"]): row["receipts"]
        for row in supply if row["receipts"]
    })
    for sku, qty in demand.items():
        if not qty:
            continue
        for revision in (item for key, item in revisions.items() if key[0] == sku):
            missing = set(revision.usage) - set(masters)
            if missing and (revision.revision == "A" or any(
                e.status == "approved" and e.finished_sku == sku and
                e.to_revision == revision.revision for e in ecns
            )):
                raise ValueError(f"Missing inventory master for BOM components: {', '.join(sorted(missing))}")

    capacities = _capacity_by_day(
        lines, production_start, production_end, overtime_by_sku, downtime_by_sku,
    )
    active = {
        (day, sku): resolve_revision(sku, day, ecns)
        for day in capacities for sku in products
    }
    material_requirements = _nominal_requirements(
        production_lots, products, revisions, active, capacities,
    )
    requirement_ledger = _requirement_ledger(
        masters, receipts_by_day, opening, holds_by_day,
        material_requirements, as_of, production_end,
    )
    purchase_advice = _purchase_advice(requirement_ledger, masters, as_of)

    balances = opening.copy()
    physical = {sku: item["on_hand"] for sku, item in masters.items()}
    held_balances = {sku: 0 for sku in masters}
    remaining = {lot.order_id: lot.qty for lot in production_lots}
    completed = defaultdict(int)
    completed_by_revision = defaultdict(int)
    material_blocked = defaultdict(bool)
    total_capacity = defaultdict(int)
    daily_schedule, trace, stock_ledger = [], [], []

    for offset in range((production_end - as_of).days + 1):
        day = as_of + timedelta(days=offset)
        opening_today = balances.copy()
        received_today = {sku: receipts_by_day[day, sku] for sku in masters}
        used_today = defaultdict(int)
        for sku in masters:
            balances[sku] += received_today[sku]
            physical[sku] += received_today[sku]
            held = holds_by_day[day, sku]
            if held > balances[sku]:
                raise ValueError(f"Stock hold exceeds usable {sku} on {day}")
            balances[sku] -= held
            held_balances[sku] += held

        if day >= production_start:
            for sku in products:
                revision, ecn_reference = active[day, sku]
                selected = revisions.get((sku, revision))
                usage = selected.usage if selected is not None else {}
                capacity = capacities[day][sku]
                total_capacity[sku] += capacity
                planned_remaining = sum(remaining[lot.order_id] for lot in production_lots
                                        if lot.finished_sku == sku)
                available_components = ({part: balances[part] for part in usage}
                                        if planned_remaining else {})
                limits = ({part: balances[part] // per_unit
                           for part, per_unit in usage.items()}
                          if planned_remaining else {})
                material_limit = min(limits.values(), default=0)
                critical = sorted(part for part, limit in limits.items()
                                  if limit == material_limit)
                produced, consumed = 0, defaultdict(int)
                blocked_wip, blocked_revision = 0, 0
                day_material_blocked = False
                if capacity:
                    _check_lot_contention(production_lots, remaining, sku, revision, day)
                for lot in production_lots:
                    if (lot.finished_sku != sku or not remaining[lot.order_id]
                            or lot.created_date > day):
                        continue
                    waiting = remaining[lot.order_id]
                    reason = None
                    if lot.state == "wip":
                        blocked_wip += waiting
                        reason = "WIP manual review"
                    elif lot.state == "released" and lot.pinned_revision != revision:
                        blocked_revision += waiting
                        reason = "Released revision manual review"
                    built = 0
                    if reason is None:
                        possible = min((balances[part] // per_unit
                                        for part, per_unit in usage.items()), default=0)
                        built = min(waiting, capacity, possible)
                        if capacity > 0 and possible < min(waiting, capacity):
                            material_blocked[sku] = True
                            day_material_blocked = True
                        if built:
                            for part, per_unit in usage.items():
                                amount = built * per_unit
                                balances[part] -= amount
                                physical[part] -= amount
                                used_today[part] += amount
                                consumed[part] += amount
                        remaining[lot.order_id] -= built
                        capacity -= built
                        produced += built
                        completed[sku] += built
                        completed_by_revision[sku, revision] += built
                    trace.append({
                        "date": day, "finished_sku": sku,
                        "order_id": lot.order_id, "lot_state": lot.state,
                        "active_revision": revision,
                        "bom_revision": revision if reason is None else None,
                        "pinned_revision": lot.pinned_revision,
                        "ecn_reference": ecn_reference,
                        "simulated_units": built,
                        "components_consumed": {part: built * per_unit
                                                for part, per_unit in usage.items() if built},
                        "review_required": reason is not None,
                        "block_reason": reason,
                    })
                unfinished = sum(remaining[lot.order_id] for lot in production_lots
                                 if lot.finished_sku == sku)
                constraints = []
                if planned_remaining > produced:
                    if capacities[day][sku] < planned_remaining:
                        constraints.append("capacity")
                    if day_material_blocked:
                        constraints.append("material")
                    if blocked_wip or blocked_revision:
                        constraints.append("manual review")
                daily_schedule.append({
                    "date": day, "finished_sku": sku,
                    "line_state": ("Weekend" if day.weekday() >= 5 else
                                   "Downtime" if day in (downtime_by_sku or {}).get(sku, ())
                                   else "Operating"),
                    "bom_revision": revision, "ecn_reference": ecn_reference,
                    "planned_remaining_demand": planned_remaining,
                    "available_capacity": capacities[day][sku],
                    "available_components": available_components,
                    "critical_components": critical,
                    "material_limit_units": material_limit,
                    "actual_buildable_units": produced,
                    "components_consumed": dict(consumed),
                    "remaining_inventory": balances.copy(),
                    "unfinished_demand": unfinished,
                    "blocked_wip_units": blocked_wip,
                    "blocked_revision_units": blocked_revision,
                    "constraints": constraints,
                })

        for sku in masters:
            stock_ledger.append({
                "date": day, "component_sku": sku,
                "opening_usable": opening_today[sku],
                "confirmed_receipts": received_today[sku],
                "authorized_hold": holds_by_day[day, sku],
                "simulated_use": used_today[sku],
                "closing_usable": balances[sku],
                "closing_physical": physical[sku],
                "closing_held": held_balances[sku],
            })

    by_product = []
    review_required = 0
    for sku in products:
        unfinished = sum(remaining[lot.order_id] for lot in production_lots
                         if lot.finished_sku == sku)
        blocked = sum(remaining[lot.order_id] for lot in production_lots
                      if lot.finished_sku == sku and (lot.state == "wip" or
                      (lot.state == "released" and lot.pinned_revision !=
                       active[production_end, sku][0])))
        review_required += blocked
        reasons = []
        if unfinished:
            if demand.get(sku, 0) > total_capacity[sku]:
                reasons.append("capacity")
            if material_blocked[sku]:
                reasons.append("material")
            if blocked:
                reasons.append("manual review")
        by_product.append({
            "finished_sku": sku, "demand": demand.get(sku, 0),
            "completed_units": completed[sku], "remaining_units": unfinished,
            "complete": unfinished == 0, "remaining_reasons": reasons,
            "completed_by_revision": {
                revision: qty for (product, revision), qty in completed_by_revision.items()
                if product == sku
            },
            "review_required_units": blocked,
        })

    old_receipt_review = []
    disposition_review = []
    for ecn in ecns:
        if ecn.status != "approved":
            continue
        for change in ecn.changes:
            old = change.old_component_sku
            effective = ecn.effective_date <= production_end
            physical_old = physical[old]
            held_old = held_balances[old]
            needs_action = effective and physical_old > 0 and (
                ecn.disposition != "hold" or held_old < physical_old
            )
            disposition_review.append({
                "ecn_reference": ecn.reference,
                "component_sku": old,
                "disposition": ecn.disposition,
                "physical_on_hand": physical_old,
                "held_qty": held_old,
                "remaining_usable": balances[old],
                "manual_action_required": needs_action,
                "automatic_stock_change": False,
            })
            for receipt in receipts:
                if (receipt["component_sku"] == change.old_component_sku
                        and receipt["due_date"] >= ecn.effective_date
                        and receipt.get("confirmed", True)):
                    old_receipt_review.append({
                        "ecn_reference": ecn.reference,
                        "component_sku": change.old_component_sku,
                        "qty": receipt["qty"], "due_date": receipt["due_date"],
                        "action": "manual supplier/disposition review",
                    })

    return {
        "daily_schedule": daily_schedule,
        "revision_trace": trace,
        "material_requirements": material_requirements,
        "requirement_ledger": requirement_ledger,
        "purchase_advice": purchase_advice,
        "stock_ledger": stock_ledger,
        "old_receipt_review": old_receipt_review,
        "disposition_review": disposition_review,
        "summary": {
            "production_start": production_start,
            "production_end": production_end,
            "priority_rule": "ascending finished SKU",
            "by_product": by_product,
            "total_demand": sum(demand.values()),
            "total_completed": sum(completed.values()),
            "total_remaining": sum(remaining.values()),
            "complete": all(qty == 0 for qty in remaining.values()),
            "remaining_inventory": balances.copy(),
            "physical_inventory": physical.copy(),
            "held_inventory": held_balances.copy(),
            "review_required_units": review_required,
        },
    }
