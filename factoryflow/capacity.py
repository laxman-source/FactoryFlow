"""Weekday production capacity planning with fictional factory lines.

This calculation considers line capacity only. Material availability remains
the separate Phase 1 MRP calculation in factoryflow.planning.
"""

from collections.abc import Mapping
from datetime import date, datetime, timedelta


PRODUCTION_LINES = [
    {"finished_sku": "FG-LAMP-01", "name": "Smart desk lamp line", "daily_capacity": 80},
    {"finished_sku": "FG-CHARGER-02", "name": "Wireless charger line", "daily_capacity": 60},
]


def _next_working_day(day):
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return day


def _next_operating_day(day, downtime_dates):
    day = _next_working_day(day)
    while day in downtime_dates:
        day = _next_working_day(day + timedelta(days=1))
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


def _completion_date(first_day, required_days, downtime_dates):
    if required_days == 0:
        return None
    day = first_day
    for _ in range(required_days - 1):
        day = _next_operating_day(day + timedelta(days=1), downtime_dates)
    return day


def calculate_capacity_plan(
    demand, lines, production_start, target_completion, *,
    overtime_by_sku=None, downtime_by_sku=None,
):
    """Return a capacity result for each dedicated finished-product line.

    The window includes both dates. Weekends contribute no production.
    Optional overtime_by_sku maps a finished SKU to extra units per operating
    weekday. Optional downtime_by_sku maps a finished SKU to a list or tuple
    of full-day dates; downtime overrides normal and overtime production.
    Required days = ceiling(demand / (normal daily capacity + overtime)).
    Available units = operating weekdays in window x that daily capacity.
    Capacity shortage = maximum of zero and demand minus available units.
    Projected completion skips weekends and the line's full downtime days,
    including downtime after the target date if production runs late.
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
    if overtime_by_sku is None:
        overtime_by_sku = {}
    if not isinstance(overtime_by_sku, Mapping):
        raise ValueError("Overtime must be a mapping from production line SKU to extra units")
    if downtime_by_sku is None:
        downtime_by_sku = {}
    if not isinstance(downtime_by_sku, Mapping):
        raise ValueError("Downtime must be a mapping from production line SKU to dates")

    for sku, extra_units in overtime_by_sku.items():
        if sku not in line_skus:
            raise ValueError(f"Overtime refers to unknown production line: {sku}")
        if isinstance(extra_units, bool) or not isinstance(extra_units, int) or extra_units < 0:
            raise ValueError(f"Overtime for {sku} must be a non-negative whole number")

    downtime_dates_by_sku = {}
    for sku, dates in downtime_by_sku.items():
        if sku not in line_skus:
            raise ValueError(f"Downtime refers to unknown production line: {sku}")
        if not isinstance(dates, (list, tuple)):
            raise ValueError(f"Downtime for {sku} must be a list or tuple of dates")
        for day in dates:
            if not isinstance(day, date) or isinstance(day, datetime):
                raise ValueError(f"Downtime for {sku} must contain dates")
        if len(dates) != len(set(dates)):
            raise ValueError(f"Duplicate downtime dates for {sku}")
        downtime_dates_by_sku[sku] = set(dates)

    for sku, quantity in demand.items():
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
            raise ValueError(f"Demand for {sku} must be a non-negative whole number")
        if sku not in line_skus:
            raise ValueError(f"No production line defined for finished product {sku}")

    working_days = _working_days_in_window(production_start, target_completion)
    results = []
    for line in lines:
        sku = line["finished_sku"]
        daily_capacity = line["daily_capacity"]
        if isinstance(daily_capacity, bool) or not isinstance(daily_capacity, int) or daily_capacity <= 0:
            raise ValueError(f"Daily capacity for {sku} must be a positive whole number")

        quantity = demand.get(sku, 0)
        overtime = overtime_by_sku.get(sku, 0)
        operating_daily_capacity = daily_capacity + overtime
        downtime_dates = downtime_dates_by_sku.get(sku, set())
        downtime_days_in_window = sum(
            production_start <= day <= target_completion and day.weekday() < 5
            for day in downtime_dates
        )
        operating_working_days = working_days - downtime_days_in_window
        required_days = (quantity + operating_daily_capacity - 1) // operating_daily_capacity
        available_capacity = operating_working_days * operating_daily_capacity
        capacity_shortage = max(0, quantity - available_capacity)
        first_day = _next_operating_day(production_start, downtime_dates) if quantity else None
        projected_completion = _completion_date(first_day, required_days, downtime_dates)
        results.append({
            "finished_sku": sku,
            "line_name": line["name"],
            "demand": quantity,
            "daily_capacity": daily_capacity,
            "overtime_units_per_day": overtime,
            "operating_daily_capacity": operating_daily_capacity,
            "production_start": production_start,
            "first_production_date": first_day,
            "target_completion": target_completion,
            "projected_completion": projected_completion,
            "required_working_days": required_days,
            "window_working_days": working_days,
            "downtime_days_in_window": downtime_days_in_window,
            "operating_working_days": operating_working_days,
            "available_capacity": available_capacity,
            "capacity_shortage": capacity_shortage,
            "capacity_status": "Potentially late" if capacity_shortage else "Within capacity",
        })
    return results
