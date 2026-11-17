"""Fictional two-product inputs for the provisional MPS foundation.

These records are examples, not customer commitments or confirmed production.
Component inventory in factoryflow.data is deliberately separate from this
finished-goods opening snapshot.
"""

from datetime import date

from factoryflow.mps import (
    DemandForecast, FinishedGoodsOpening, FirmCustomerOrder,
    ProposedMPSCompletion,
)

DEMO_MPS_AS_OF = date(2026, 12, 1)
DEMO_MPS_END = date(2026, 12, 3)
DEMO_FINISHED_SKUS = ("FG-LAMP-01", "FG-CHARGER-02")
DEMO_FG_OPENING = (
    FinishedGoodsOpening("FG-LAMP-01", 20),
    FinishedGoodsOpening("FG-CHARGER-02", 10),
)
DEMO_FIRM_ORDERS = (
    FirmCustomerOrder("FICTIONAL-L1", "FG-LAMP-01", date(2026, 12, 1), 25),
    FirmCustomerOrder("FICTIONAL-L2", "FG-LAMP-01", date(2026, 12, 2), 10),
    FirmCustomerOrder("FICTIONAL-C1", "FG-CHARGER-02", date(2026, 12, 1), 8),
)
DEMO_FORECASTS = (
    DemandForecast("FG-LAMP-01", date(2026, 12, 1), 30),
    DemandForecast("FG-LAMP-01", date(2026, 12, 2), 5),
    DemandForecast("FG-CHARGER-02", date(2026, 12, 1), 12),
    DemandForecast("FG-CHARGER-02", date(2026, 12, 3), 6),
)
DEMO_MPS_COMPLETIONS = (
    ProposedMPSCompletion("FG-LAMP-01", date(2026, 12, 1), date(2026, 12, 1), 20),
    ProposedMPSCompletion("FG-LAMP-01", date(2026, 12, 2), date(2026, 12, 2), 10),
    ProposedMPSCompletion("FG-CHARGER-02", date(2026, 12, 1), date(2026, 12, 1), 5),
    ProposedMPSCompletion("FG-CHARGER-02", date(2026, 12, 3), date(2026, 12, 3), 6),
)
