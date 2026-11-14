"""A testable, date-aware, ONE-BUCKET material planning calculation.

This is NOT a complete enterprise MRP engine. It assumes all finished-goods
orders need their materials on one shared production start date.
"""

from collections import defaultdict
from datetime import date, timedelta


def _nonnegative_int(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative whole number")


def calculate_plan(demand, bom, inventory, receipts, as_of, production_date, extra_lead_days=0):
    """Return one planning row for each inventoried component.

    Gross = finished-goods demand x BOM quantity per product.
    Usable stock = max(0, on_hand - reserved - safety stock).
    Eligible incoming = receipts with as_of < due_date <= production_date.
    Net shortage = max(0, gross - usable - eligible incoming).
    Suggested order = round shortage UP to supplier pack-size multiples.

    A late PO release is a risk, not a promise of on-time delivery.
    """
    if not isinstance(as_of, date) or not isinstance(production_date, date):
        raise ValueError("as_of and production_date must be dates")
    if production_date < as_of:
        raise ValueError("Production date cannot be earlier than the planning snapshot")
    _nonnegative_int(extra_lead_days, "Extra supplier lead days")

    product_codes = {line["finished_sku"] for line in bom}
    for product, quantity in demand.items():
        _nonnegative_int(quantity, f"Demand for {product}")
        if product not in product_codes:
            raise ValueError(f"No BOM defined for finished product {product}")

    gross = defaultdict(int)
    for line in bom:
        per_unit = line["qty_per_unit"]
        if isinstance(per_unit, bool) or not isinstance(per_unit, int) or per_unit <= 0:
            raise ValueError("BOM usage must be a positive whole number")
        gross[line["component_sku"]] += demand.get(line["finished_sku"], 0) * per_unit

    available_skus = [item["sku"] for item in inventory]
    if len(available_skus) != len(set(available_skus)):
        raise ValueError("Inventory SKUs must be unique")
    missing_skus = set(gross) - set(available_skus)
    if missing_skus:
        raise ValueError(f"Missing inventory records for BOM components: {', '.join(sorted(missing_skus))}")

    incoming = defaultdict(int)
    late_incoming = defaultdict(int)
    for receipt in receipts:
        sku = receipt["component_sku"]
        if sku not in available_skus:
            raise ValueError(f"Receipt refers to unknown component: {sku}")
        _nonnegative_int(receipt["qty"], f"Receipt quantity for {sku}")
        if not isinstance(receipt["due_date"], date):
            raise ValueError(f"Receipt date for {sku} must be a date")
        if as_of < receipt["due_date"] <= production_date:
            incoming[sku] += receipt["qty"]
        elif receipt["due_date"] > production_date:
            late_incoming[sku] += receipt["qty"]
        # Receipts on or before as_of are treated as already reflected in on-hand.

    results = []
    for item in inventory:
        sku = item["sku"]
        for field in ("on_hand", "reserved", "safety_stock", "lead_days"):
            _nonnegative_int(item[field], f"{field} for {sku}")
        pack = item["pack_size"]
        if isinstance(pack, bool) or not isinstance(pack, int) or pack <= 0:
            raise ValueError(f"pack_size for {sku} must be a positive whole number")
        if item["reserved"] > item["on_hand"]:
            raise ValueError(f"Reserved stock cannot exceed on-hand stock for {sku}")

        usable = max(0, item["on_hand"] - item["reserved"] - item["safety_stock"])
        requirement = gross[sku]
        shortage = max(0, requirement - usable - incoming[sku])
        suggested = ((shortage + pack - 1) // pack) * pack if shortage else 0
        lead = item["lead_days"] + extra_lead_days
        order_by = production_date - timedelta(days=lead) if shortage else None
        status = "Covered" if not shortage else ("Order now" if as_of <= order_by else "At risk: expedite")
        results.append({
            "sku": sku,
            "name": item["name"],
            "gross_required": requirement,
            "on_hand": item["on_hand"],
            "reserved": item["reserved"],
            "safety_stock": item["safety_stock"],
            "usable_stock": usable,
            "incoming_on_time": incoming[sku],
            "incoming_late": late_incoming[sku],
            "net_shortage": shortage,
            "pack_size": pack,
            "suggested_order_qty": suggested,
            "lead_days": lead,
            "latest_order_date": order_by,
            "status": status,
        })
    return results
