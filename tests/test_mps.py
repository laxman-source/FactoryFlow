"""Independent arithmetic checks for the provisional daily MPS projection."""

from datetime import date, datetime

import pytest

from factoryflow.mps import (
    DemandForecast, FinishedGoodsOpening, FirmCustomerOrder,
    ProposedMPSCompletion, calculate_mps,
)
from factoryflow.mps_data import (
    DEMO_FG_OPENING, DEMO_FINISHED_SKUS, DEMO_FIRM_ORDERS,
    DEMO_FORECASTS, DEMO_MPS_AS_OF, DEMO_MPS_COMPLETIONS, DEMO_MPS_END,
)

LAMP = "FG-LAMP-01"
CHARGER = "FG-CHARGER-02"
D1, D2, D3 = (date(2026, 12, n) for n in (1, 2, 3))


def plan(*, skus=(LAMP,), opening=None, orders=(), forecasts=(), mps=(), end=D3):
    if opening is None:
        opening = (FinishedGoodsOpening(LAMP, 0),)
    return calculate_mps(skus, opening, orders, forecasts, mps, D1, end)


def by_day(rows, sku=LAMP):
    return {row["planning_date"]: row for row in rows if row["finished_sku"] == sku}


def test_firm_orders_without_forecast():
    rows = by_day(plan(orders=(FirmCustomerOrder("O1", LAMP, D1, 4),), end=D1))
    assert (rows[D1]["firm_orders"], rows[D1]["forecast"],
            rows[D1]["forecast_consumed"], rows[D1]["effective_demand"]) == (4, 0, 0, 4)
    assert (rows[D1]["projected_fg_balance"], rows[D1]["unmet_demand"]) == (-4, 4)


def test_forecast_without_firm_orders():
    rows = by_day(plan(forecasts=(DemandForecast(LAMP, D1, 6),), end=D1))
    assert (rows[D1]["firm_orders"], rows[D1]["effective_demand"],
            rows[D1]["projected_fg_balance"]) == (0, 6, -6)


@pytest.mark.parametrize("order_qty,forecast_qty,consumed,effective", [
    (7, 10, 7, 10),
    (12, 10, 10, 12),
])
def test_same_bucket_orders_consume_forecast_once(
    order_qty, forecast_qty, consumed, effective,
):
    rows = by_day(plan(
        orders=(FirmCustomerOrder("O1", LAMP, D1, order_qty),),
        forecasts=(DemandForecast(LAMP, D1, forecast_qty),),
        end=D1,
    ))
    assert (rows[D1]["forecast_consumed"], rows[D1]["effective_demand"]) == (
        consumed, effective,
    )


def test_multiple_orders_share_one_bucket_without_duplicate_forecast():
    rows = by_day(plan(
        orders=(FirmCustomerOrder("O1", LAMP, D1, 3),
                FirmCustomerOrder("O2", LAMP, D1, 4)),
        forecasts=(DemandForecast(LAMP, D1, 10),),
        end=D1,
    ))
    assert (rows[D1]["firm_orders"], rows[D1]["forecast_consumed"],
            rows[D1]["effective_demand"]) == (7, 7, 10)


def test_orders_on_another_date_do_not_consume_prior_forecast():
    rows = by_day(plan(
        orders=(FirmCustomerOrder("O1", LAMP, D2, 4),),
        forecasts=(DemandForecast(LAMP, D1, 6),),
        end=D2,
    ))
    assert (rows[D1]["effective_demand"], rows[D1]["forecast_consumed"]) == (6, 0)
    assert (rows[D2]["effective_demand"], rows[D2]["forecast_consumed"]) == (4, 0)
    assert rows[D2]["projected_fg_balance"] == -10

def test_opening_inventory_is_consumed_before_deficit():
    rows = by_day(plan(
        opening=(FinishedGoodsOpening(LAMP, 5),),
        orders=(FirmCustomerOrder("O1", LAMP, D1, 3),
                FirmCustomerOrder("O2", LAMP, D2, 4)),
        end=D2,
    ))
    assert (rows[D1]["opening_projected_balance"], rows[D1]["projected_fg_balance"],
            rows[D1]["unmet_demand"]) == (5, 2, 0)
    assert (rows[D2]["opening_projected_balance"], rows[D2]["projected_fg_balance"],
            rows[D2]["unmet_demand"]) == (2, -2, 2)


def test_multiple_dates_carry_backlog_until_proposed_completion():
    rows = by_day(plan(
        orders=(FirmCustomerOrder("O1", LAMP, D1, 5),),
        mps=(ProposedMPSCompletion(LAMP, D2, D2, 3),
             ProposedMPSCompletion(LAMP, D3, D3, 4)),
    ))
    assert [(rows[day]["projected_fg_balance"], rows[day]["unmet_demand"])
            for day in (D1, D2, D3)] == [(-5, 5), (-2, 2), (2, 0)]
    assert rows[D2]["effective_demand"] == 0
    assert rows[D2]["production_start"] == D2
    assert rows[D2]["proposed_mps_completion"] == 3


def test_two_products_have_independent_balances_and_sorted_daily_rows():
    rows = plan(
        skus=(LAMP, CHARGER),
        opening=(FinishedGoodsOpening(LAMP, 2),
                 FinishedGoodsOpening(CHARGER, 10)),
        orders=(FirmCustomerOrder("L1", LAMP, D1, 5),
                FirmCustomerOrder("C1", CHARGER, D1, 3)),
        mps=(ProposedMPSCompletion(LAMP, D1, D1, 1),),
        end=D1,
    )
    assert [(row["finished_sku"], row["projected_fg_balance"],
             row["unmet_demand"]) for row in rows] == [
                 (CHARGER, 7, 0), (LAMP, -2, 2)]


def test_fictional_two_product_example_has_fixed_hand_calculated_results():
    rows = calculate_mps(
        DEMO_FINISHED_SKUS, DEMO_FG_OPENING, DEMO_FIRM_ORDERS,
        DEMO_FORECASTS, DEMO_MPS_COMPLETIONS, DEMO_MPS_AS_OF, DEMO_MPS_END,
    )
    assert [(row["planning_date"], row["finished_sku"],
             row["effective_demand"], row["proposed_mps_completion"],
             row["projected_fg_balance"]) for row in rows] == [
                 (D1, CHARGER, 12, 5, 3),
                 (D1, LAMP, 30, 20, 10),
                 (D2, CHARGER, 0, 0, 3),
                 (D2, LAMP, 10, 10, 10),
                 (D3, CHARGER, 6, 6, 3),
                 (D3, LAMP, 0, 0, 10),
             ]


def test_finished_goods_conservation_per_product_and_date():
    rows = plan(
        skus=(LAMP, CHARGER),
        opening=(FinishedGoodsOpening(LAMP, 2),
                 FinishedGoodsOpening(CHARGER, 1)),
        orders=(FirmCustomerOrder("L1", LAMP, D1, 5),
                FirmCustomerOrder("C1", CHARGER, D2, 3)),
        forecasts=(DemandForecast(LAMP, D1, 7),
                   DemandForecast(CHARGER, D2, 2)),
        mps=(ProposedMPSCompletion(LAMP, D2, D2, 4),
             ProposedMPSCompletion(CHARGER, D3, D3, 5)),
    )
    for sku, initial in ((LAMP, 2), (CHARGER, 1)):
        product_rows = [row for row in rows if row["finished_sku"] == sku]
        cumulative_supply = 0
        cumulative_demand = 0
        for row in product_rows:
            cumulative_supply += row["proposed_mps_completion"]
            cumulative_demand += row["effective_demand"]
            assert row["projected_fg_balance"] == (
                initial + cumulative_supply - cumulative_demand
            )
            assert row["unmet_demand"] == max(0, -row["projected_fg_balance"])


@pytest.mark.parametrize("record", [
    lambda: FinishedGoodsOpening(LAMP, -1),
    lambda: FirmCustomerOrder("O1", LAMP, D1, -1),
    lambda: DemandForecast(LAMP, D1, -1),
    lambda: ProposedMPSCompletion(LAMP, D1, D1, -1),
    lambda: FirmCustomerOrder("O1", LAMP, datetime(2026, 12, 1), 1),
    lambda: DemandForecast(LAMP, "2026-12-01", 1),
    lambda: ProposedMPSCompletion(LAMP, D2, D1, 1),
    lambda: FinishedGoodsOpening("", 1),
    lambda: FinishedGoodsOpening(LAMP, True),
])
def test_invalid_records_are_rejected(record):
    with pytest.raises(ValueError):
        record()


@pytest.mark.parametrize("override", [
    {"skus": (LAMP, LAMP)},
    {"opening": ()},
    {"opening": (FinishedGoodsOpening(LAMP, 1),
                 FinishedGoodsOpening(LAMP, 2))},
    {"orders": (FirmCustomerOrder("O1", "UNKNOWN", D1, 1),)},
    {"orders": (FirmCustomerOrder("O1", LAMP, D1, 1),
                FirmCustomerOrder("O1", LAMP, D2, 1))},
    {"orders": (FirmCustomerOrder("O1", LAMP, date(2026, 11, 30), 1),)},
    {"forecasts": (DemandForecast(LAMP, D1, 1),
                   DemandForecast(LAMP, D1, 2))},
    {"mps": (ProposedMPSCompletion(LAMP, D1, D1, 1),
             ProposedMPSCompletion(LAMP, D1, D1, 2))},
    {"mps": (ProposedMPSCompletion(LAMP, D1, D2, 1),)},
    {"end": date(2026, 11, 30)},
])
def test_invalid_plans_are_rejected(override):
    with pytest.raises(ValueError):
        plan(**override)
