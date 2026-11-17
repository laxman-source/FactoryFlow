"""Simulation-only, daily finished-goods Master Production Schedule foundation.

Provisional policy: firm orders consume forecast only in the same SKU/date
bucket. Effective demand is orders + forecast - min(orders, forecast).
A proposed completion is counted on its completion date, but this first model
requires production start and completion on the same day. Proposed output is
not confirmed production or physical finished-goods inventory.

The signed projected balance carries surplus or backlog between dates:
prior projected balance + proposed completions - effective demand.
Unmet demand is the nonnegative outstanding balance, not extra demand to
subtract again on the following date.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta


def _code(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonblank string")


def _day(value, label):
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValueError(f"{label} must be a calendar date")


def _quantity(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a non-negative whole number")


@dataclass(frozen=True)
class FinishedGoodsOpening:
    finished_sku: str
    qty: int

    def __post_init__(self):
        _code(self.finished_sku, "Finished-product SKU")
        _quantity(self.qty, "Opening finished-goods quantity")


@dataclass(frozen=True)
class FirmCustomerOrder:
    order_id: str
    finished_sku: str
    due_date: date
    qty: int

    def __post_init__(self):
        _code(self.order_id, "Customer order ID")
        _code(self.finished_sku, "Finished-product SKU")
        _day(self.due_date, "Customer order due date")
        _quantity(self.qty, "Customer order quantity")


@dataclass(frozen=True)
class DemandForecast:
    finished_sku: str
    planning_date: date
    qty: int

    def __post_init__(self):
        _code(self.finished_sku, "Finished-product SKU")
        _day(self.planning_date, "Forecast planning date")
        _quantity(self.qty, "Forecast quantity")


@dataclass(frozen=True)
class ProposedMPSCompletion:
    finished_sku: str
    production_start: date
    completion_date: date
    qty: int

    def __post_init__(self):
        _code(self.finished_sku, "Finished-product SKU")
        _day(self.production_start, "Production start")
        _day(self.completion_date, "Proposed completion date")
        _quantity(self.qty, "Proposed MPS completion quantity")
        if self.production_start > self.completion_date:
            raise ValueError("Production start cannot follow completion date")


def calculate_mps(
    finished_skus, opening_inventory, firm_orders, forecasts,
    proposed_completions, as_of, planning_end,
):
    """Return one deterministic daily projection row per finished SKU.

    All dated records must fall within the inclusive as_of/planning_end horizon.
    Opening inventory is a physical snapshot supplied by the caller. Subsequent
    balances are projections because MPS completions have not occurred.
    Negative projected balances remain visible and their absolute value is
    reported as outstanding unmet demand. No orders, production, purchases,
    ATP, ECN decisions, or rescheduling are posted or inferred.
    """
    _day(as_of, "Planning snapshot")
    _day(planning_end, "Planning end")
    if planning_end < as_of:
        raise ValueError("Planning end cannot precede the snapshot")
    for label, records in (
        ("Finished SKUs", finished_skus),
        ("Opening inventory", opening_inventory),
        ("Firm orders", firm_orders),
        ("Forecasts", forecasts),
        ("Proposed completions", proposed_completions),
    ):
        if not isinstance(records, (list, tuple)):
            raise ValueError(f"{label} must be a list or tuple")

    skus = set()
    for sku in finished_skus:
        _code(sku, "Finished-product SKU")
        if sku in skus:
            raise ValueError(f"Duplicate finished-product SKU: {sku}")
        skus.add(sku)
    if not skus:
        raise ValueError("At least one finished-product SKU is required")

    def check_sku(sku):
        if sku not in skus:
            raise ValueError(f"Unknown finished-product SKU: {sku}")

    def check_date(day, label):
        if not as_of <= day <= planning_end:
            raise ValueError(f"{label} must be within the planning horizon")

    opening = {}
    for item in opening_inventory:
        if not isinstance(item, FinishedGoodsOpening):
            raise ValueError("Opening inventory must contain FinishedGoodsOpening records")
        check_sku(item.finished_sku)
        if item.finished_sku in opening:
            raise ValueError(f"Duplicate opening inventory for {item.finished_sku}")
        opening[item.finished_sku] = item.qty
    if set(opening) != skus:
        raise ValueError("Opening inventory must cover every finished-product SKU")

    orders_by_bucket = defaultdict(int)
    order_ids = set()
    for order in firm_orders:
        if not isinstance(order, FirmCustomerOrder):
            raise ValueError("Firm orders must contain FirmCustomerOrder records")
        check_sku(order.finished_sku)
        check_date(order.due_date, "Customer order due date")
        if order.order_id in order_ids:
            raise ValueError(f"Duplicate customer order ID: {order.order_id}")
        order_ids.add(order.order_id)
        orders_by_bucket[order.due_date, order.finished_sku] += order.qty

    forecast_by_bucket = {}
    for forecast in forecasts:
        if not isinstance(forecast, DemandForecast):
            raise ValueError("Forecasts must contain DemandForecast records")
        check_sku(forecast.finished_sku)
        check_date(forecast.planning_date, "Forecast planning date")
        key = forecast.planning_date, forecast.finished_sku
        if key in forecast_by_bucket:
            raise ValueError(f"Duplicate forecast bucket: {key}")
        forecast_by_bucket[key] = forecast.qty

    mps_by_bucket = {}
    for proposal in proposed_completions:
        if not isinstance(proposal, ProposedMPSCompletion):
            raise ValueError("Proposed completions must contain ProposedMPSCompletion records")
        check_sku(proposal.finished_sku)
        check_date(proposal.production_start, "Production start")
        check_date(proposal.completion_date, "Proposed completion date")
        if proposal.production_start != proposal.completion_date:
            raise ValueError("This simulation requires same-day production start and completion")
        key = proposal.completion_date, proposal.finished_sku
        if key in mps_by_bucket:
            raise ValueError(f"Duplicate proposed MPS completion bucket: {key}")
        mps_by_bucket[key] = proposal

    projected = opening.copy()
    rows = []
    for offset in range((planning_end - as_of).days + 1):
        day = as_of + timedelta(days=offset)
        for sku in sorted(skus):
            key = day, sku
            orders = orders_by_bucket[key]
            forecast = forecast_by_bucket.get(key, 0)
            consumed_forecast = min(orders, forecast)
            effective_demand = orders + forecast - consumed_forecast
            proposal = mps_by_bucket.get(key)
            mps_qty = proposal.qty if proposal else 0
            opening_balance = projected[sku]
            closing = opening_balance + mps_qty - effective_demand
            rows.append({
                "planning_date": day,
                "finished_sku": sku,
                "opening_projected_balance": opening_balance,
                "firm_orders": orders,
                "forecast": forecast,
                "forecast_consumed": consumed_forecast,
                "effective_demand": effective_demand,
                "production_start": proposal.production_start if proposal else None,
                "proposed_mps_completion": mps_qty,
                "projected_fg_balance": closing,
                "unmet_demand": max(0, -closing),
            })
            projected[sku] = closing
    return rows
