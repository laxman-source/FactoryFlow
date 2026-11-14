"""Calendar-day component availability for fictional daily production needs.

The caller supplies component quantities already required for each date. This
module does not explode the BOM, schedule production, or create purchase orders.
All requirements for a component on a date share one stock pool.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta


def _date(value, label):
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{label} must be a date")


def _nonnegative_int(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative whole number")


def calculate_material_timeline(inventory, receipts, daily_requirements, as_of, end_date):
    """Return one row per component per calendar day, from as_of through end_date.

    Input inventory and receipts use the same fields as factoryflow.data.
    Each daily requirement is {"date": date, "component_sku": str,
    "qty": nonnegative int}; an optional "finished_sku" identifies its source.
    Requirements are component quantities, not finished-unit quantities.

    Opening usable stock = max(0, on_hand - reserved - safety_stock), calculated
    once at the snapshot. Receipts due on/before as_of are assumed included in
    on_hand. Only confirmed receipts after as_of are added on their due date;
    receipts with "confirmed": False are excluded. A missing confirmed flag
    means confirmed, matching the existing RECEIPTS demonstration data.

    On every day, receipts arrive before consumption, including weekends:
    available = opening_balance + receipts
    consumption = min(requirement, available)
    unmet_need = requirement - consumption
    closing_balance = available - consumption

    Unmet need remains on its original date; later receipts cannot cover it
    retroactively. No automatic backorder or production rescheduling occurs.
    """
    _date(as_of, "Planning snapshot")
    _date(end_date, "Timeline end")
    if end_date < as_of:
        raise ValueError("Timeline end cannot be earlier than the planning snapshot")

    items = {}
    for item in inventory:
        sku = item["sku"]
        if sku in items:
            raise ValueError(f"Inventory SKUs must be unique: {sku}")
        for field in ("on_hand", "reserved", "safety_stock"):
            _nonnegative_int(item[field], f"{field} for {sku}")
        if item["reserved"] > item["on_hand"]:
            raise ValueError(f"Reserved stock cannot exceed on-hand stock for {sku}")
        items[sku] = item

    receipts_by_day = defaultdict(int)
    for receipt in receipts:
        sku = receipt["component_sku"]
        if sku not in items:
            raise ValueError(f"Receipt refers to unknown component: {sku}")
        _nonnegative_int(receipt["qty"], f"Receipt quantity for {sku}")
        _date(receipt["due_date"], f"Receipt date for {sku}")
        confirmed = receipt.get("confirmed", True)
        if not isinstance(confirmed, bool):
            raise ValueError(f"Receipt confirmation for {sku} must be a boolean")
        if confirmed and as_of < receipt["due_date"] <= end_date:
            receipts_by_day[receipt["due_date"], sku] += receipt["qty"]

    requirements_by_day = defaultdict(int)
    for requirement in daily_requirements:
        sku = requirement["component_sku"]
        if sku not in items:
            raise ValueError(f"Requirement refers to unknown component: {sku}")
        day = requirement["date"]
        _date(day, f"Requirement date for {sku}")
        if not as_of <= day <= end_date:
            raise ValueError(f"Requirement date for {sku} must be within the timeline")
        _nonnegative_int(requirement["qty"], f"Requirement quantity for {sku}")
        requirements_by_day[day, sku] += requirement["qty"]

    balances = {
        sku: max(0, item["on_hand"] - item["reserved"] - item["safety_stock"])
        for sku, item in items.items()
    }
    results = []
    for offset in range((end_date - as_of).days + 1):
        day = as_of + timedelta(days=offset)
        for sku, item in items.items():
            opening = balances[sku]
            received = receipts_by_day[day, sku]
            required = requirements_by_day[day, sku]
            consumed = min(required, opening + received)
            closing = opening + received - consumed
            results.append({
                "date": day,
                "component_sku": sku,
                "name": item["name"],
                "opening_balance": opening,
                "receipts": received,
                "requirement": required,
                "consumption": consumed,
                "unmet_need": required - consumed,
                "closing_balance": closing,
            })
            balances[sku] = closing
    return results
