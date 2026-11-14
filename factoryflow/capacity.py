"""Basic weekday production capacity planning with fictional factory lines.

This calculation considers line capacity only. Material availability remains
the separate Phase 1 MRP calculation in factoryflow.planning.
"""

from datetime import date, datetime, timedelta


PRODUCTION_LINES = [
    {"finished_sku": "FG-LAMP-01", "name": "Smart desk lamp line", "daily_capacity": 80},
    {"finished_sku": "FG-CHARGER-02", "name": "Wireless charger line", "daily_capacity": 60},
]


def _next_working_day(day):
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _working_days_in_window(start, end):
    count = 0
    day = start
    while day <= end:
        if day.weekday() < 5:
            count += 1
        if day == end:
            break
        day += timedelta(days=1)
    return count


def _completion_date(first_day, required_days):
    if required_days == 0:
        return None
    day = first_day
    for _ in range(required_days - 1):
        day = _next_working_day(day + timedelta(days=1))
    return day


def calculate_capacity_plan(demand, lines, production_start, target_completion):
    """Return a capacity result for each dedicated finished-product line.

    The window includes both dates. Weekends contribute no production.
    Required days = ceiling(demand / units per working day).
    Available units = working days in window x daily capacity.
    Capacity shortage = maximum of zero and demand minus available units.
    Projected completion assumes production starts on the first weekday on or
    after production_start and runs at full daily capacity without interruptions.
    It does not imply that the required materials are available.
    """
    if not isinstance(production_start, date) or isinstance(production_start, datetime):
        raise ValueError("Production start must be a date")
    if not isinstance(target_completion, date) or isinstance(target_completion, datetime):
        raise ValueError("Target completion must be a date")
    if target_completion < production_start:
        raise ValueError("Target completion cannot be earlier than production start")

    line_skus = [line["finished_sku"] for line in lines]
    if len(line_skus) != len(set(line_skus)):
        raise ValueError("Each finished product must have one production line")
    for sku, quantity in demand.items():
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise ValueError(f"Demand for {sku} must be a non-negative whole number")
        if sku not in line_skus:
            raise ValueError(f"No production line defined for finished product {sku}")

    working_days = _working_days_in_window(production_start, target_completion)
    first_day = _next_working_day(production_start)
    results = []
    for line in lines:
        sku = line["finished_sku"]
        daily_capacity = line["daily_capacity"]
        if isinstance(daily_capacity, bool) or not isinstance(daily_capacity, int) or daily_capacity <= 0:
            raise ValueError(f"Daily capacity for {sku} must be a positive whole number")

        quantity = demand.get(sku, 0)
        required_days = (quantity + daily_capacity - 1) // daily_capacity
        available_capacity = working_days * daily_capacity
        capacity_shortage = max(0, quantity - available_capacity)
        projected_completion = _completion_date(first_day, required_days)
        results.append({
            "finished_sku": sku,
            "line_name": line["name"],
            "demand": quantity,
            "daily_capacity": daily_capacity,
            "production_start": production_start,
            "first_production_date": first_day if quantity else None,
            "target_completion": target_completion,
            "projected_completion": projected_completion,
            "required_working_days": required_days,
            "window_working_days": working_days,
            "available_capacity": available_capacity,
            "capacity_shortage": capacity_shortage,
            "capacity_status": "Potentially late" if capacity_shortage else "Within capacity",
        })
    return results
