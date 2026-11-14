"""Finite daily production simulation using confirmed supply and line capacity.

The simulation uses one-level BOMs and dedicated lines. It does not promise a
completion date beyond the selected window or create purchasing transactions.
"""

from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime, timedelta

from factoryflow.capacity import PRODUCTION_LINES, calculate_capacity_plan
from factoryflow.material_timeline import calculate_material_timeline


def calculate_production_schedule(
    demand, bom, inventory, receipts, as_of, production_start, production_end, *,
    lines=PRODUCTION_LINES, overtime_by_sku=None, downtime_by_sku=None,
):
    """Return daily_schedule and summary for the inclusive production window.

    Each daily row is one finished product. Products run in ascending SKU order,
    independent of input order; the earlier SKU has first claim on shared stock.
    Within a day, Phase 4A confirmed receipts enter before production. For each
    product, whole units built = min(remaining demand, line capacity, minimum of
    available component stock // BOM quantity per unit). Only then are *all*
    BOM components deducted for those completed units. There are no partial
    assemblies and unmet demand is carried to the next day in the window.
    Each row's remaining_inventory is the balance after that product's turn;
    the final row on a date is the date's closing balance. Summary reasons mark
    capacity when total window capacity is below demand and material when stock
    blocked an operating-day build. They are observed constraints, not a promise
    that purchasing alone would complete the order.
    """
    if not isinstance(production_start, date) or isinstance(production_start, datetime):
        raise ValueError("Production start must be a date")
    if not isinstance(as_of, date) or isinstance(as_of, datetime):
        raise ValueError("Inventory snapshot must be a date")
    if production_start < as_of:
        raise ValueError("Production start cannot be earlier than the inventory snapshot")
    if not isinstance(demand, Mapping):
        raise ValueError("Demand must be a mapping from finished SKU to whole units")
    if not isinstance(lines, (list, tuple)):
        raise ValueError("Production lines must be a list or tuple")

    # Reuse the verified capacity rules and option validation, without asking
    # that engine to project a finish beyond the finite simulation window.
    calculate_capacity_plan(
        {}, lines, production_start, production_end,
        overtime_by_sku=overtime_by_sku, downtime_by_sku=downtime_by_sku,
    )
    line_skus = {line["finished_sku"] for line in lines}
    for sku, quantity in demand.items():
        if sku not in line_skus:
            raise ValueError(f"No production line defined for finished product {sku}")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise ValueError(f"Demand for {sku} must be a non-negative whole number")

    usage = defaultdict(lambda: defaultdict(int))
    for line in bom:
        product, component = line["finished_sku"], line["component_sku"]
        per_unit = line["qty_per_unit"]
        if isinstance(per_unit, bool) or not isinstance(per_unit, int) or per_unit <= 0:
            raise ValueError("BOM usage must be a positive whole number")
        usage[product][component] += per_unit
    for sku, quantity in demand.items():
        if quantity and not usage[sku]:
            raise ValueError(f"No BOM defined for finished product {sku}")

    # This ledger owns the Phase 4A opening-stock, protected-stock, receipt
    # confirmation, snapshot, and same-day timing rules. It has no planned
    # consumption here; actual build quantities below drive deductions.
    supply_rows = calculate_material_timeline(
        inventory, receipts, [], as_of, production_end,
    )
    opening = {row["component_sku"]: row["opening_balance"]
               for row in supply_rows if row["date"] == as_of}
    missing = {component for sku in demand if demand[sku]
               for component in usage[sku] if component not in opening}
    if missing:
        raise ValueError(f"Missing inventory records for BOM components: {', '.join(sorted(missing))}")
    receipts_by_day = {(row["date"], row["component_sku"]): row["receipts"]
                       for row in supply_rows if row["receipts"]}

    balances = opening.copy()
    remaining = {sku: demand.get(sku, 0) for sku in line_skus}
    completed = {sku: 0 for sku in line_skus}
    total_capacity = {sku: 0 for sku in line_skus}
    material_blocked = {sku: False for sku in line_skus}
    downtime = {sku: set(days) for sku, days in (downtime_by_sku or {}).items()}
    priority = sorted(line_skus)
    daily_schedule = []

    for offset in range((production_end - as_of).days + 1):
        day = as_of + timedelta(days=offset)
        for component in balances:
            balances[component] += receipts_by_day.get((day, component), 0)
        if day < production_start:
            continue

        capacities = {
            row["finished_sku"]: row["available_capacity"]
            for row in calculate_capacity_plan(
                {}, lines, day, day,
                overtime_by_sku=overtime_by_sku, downtime_by_sku=downtime_by_sku,
            )
        }
        for sku in priority:
            planned_remaining = remaining[sku]
            available_capacity = capacities[sku]
            total_capacity[sku] += available_capacity
            available_components = {
                component: balances[component] for component in usage[sku]
            } if planned_remaining else {}
            component_limits = {
                component: balances[component] // per_unit
                for component, per_unit in usage[sku].items()
            } if planned_remaining else {}
            material_limit = min(component_limits.values(), default=0)
            critical = sorted(component for component, limit in component_limits.items()
                              if limit == material_limit)
            built = min(planned_remaining, available_capacity, material_limit)
            consumed = {component: built * per_unit
                        for component, per_unit in usage[sku].items() if built}
            for component, quantity in consumed.items():
                balances[component] -= quantity
            completed[sku] += built
            remaining[sku] -= built

            constraints = []
            if planned_remaining > built:
                if available_capacity < planned_remaining and available_capacity <= material_limit:
                    constraints.append("capacity")
                if (available_capacity > 0 and material_limit < planned_remaining
                        and material_limit <= available_capacity):
                    constraints.append("material")
                if material_limit < min(planned_remaining, available_capacity):
                    material_blocked[sku] = True
            line_state = ("Weekend" if day.weekday() >= 5 else
                          "Downtime" if day in downtime.get(sku, set()) else "Operating")
            daily_schedule.append({
                "date": day,
                "finished_sku": sku,
                "line_state": line_state,
                "planned_remaining_demand": planned_remaining,
                "available_capacity": available_capacity,
                "available_components": available_components,
                "critical_components": critical,
                "material_limit_units": material_limit,
                "actual_buildable_units": built,
                "components_consumed": consumed,
                "remaining_inventory": balances.copy(),
                "unfinished_demand": remaining[sku],
                "constraints": constraints,
            })

    by_product = []
    for sku in priority:
        reasons = []
        if remaining[sku]:
            if demand.get(sku, 0) > total_capacity[sku]:
                reasons.append("capacity")
            if material_blocked[sku]:
                reasons.append("material")
        by_product.append({
            "finished_sku": sku,
            "demand": demand.get(sku, 0),
            "completed_units": completed[sku],
            "remaining_units": remaining[sku],
            "complete": remaining[sku] == 0,
            "remaining_reasons": reasons,
        })
    return {
        "daily_schedule": daily_schedule,
        "summary": {
            "production_start": production_start,
            "production_end": production_end,
            "priority_rule": "ascending finished SKU",
            "by_product": by_product,
            "total_demand": sum(demand.values()),
            "total_completed": sum(completed.values()),
            "total_remaining": sum(remaining.values()),
            "complete": all(value == 0 for value in remaining.values()),
            "remaining_inventory": balances.copy(),
        },
    }
