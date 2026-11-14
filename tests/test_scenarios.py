"""Independent expected results for the four Phase 1 dashboard scenarios."""

from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


# Per component: gross need, usable stock, on-time incoming, net shortage,
# supplier-pack order quantity, latest release date, and assessment.
EXPECTED = {
    "Base plan": {
        "LED-100": (200, 120, 40, 40, 40, date(2026, 11, 24), "Order now"),
        "LAM-HSG-110": (200, 240, 0, 0, 0, None, "Covered"),
        "SCR-120": (1000, 900, 0, 100, 200, date(2026, 11, 26), "Order now"),
        "ADP-130": (200, 150, 0, 50, 50, date(2026, 11, 19), "Order now"),
        "PCB-200": (100, 90, 20, 0, 0, None, "Covered"),
        "CHG-HSG-210": (100, 110, 0, 0, 0, None, "Covered"),
        "USB-220": (100, 60, 50, 0, 0, None, "Covered"),
    },
    "Demand surge": {
        "LED-100": (350, 120, 40, 190, 200, date(2026, 11, 24), "Order now"),
        "LAM-HSG-110": (350, 240, 0, 110, 110, date(2026, 11, 26), "Order now"),
        "SCR-120": (1700, 900, 0, 800, 800, date(2026, 11, 26), "Order now"),
        "ADP-130": (350, 150, 0, 200, 200, date(2026, 11, 19), "Order now"),
        "PCB-200": (150, 90, 20, 40, 40, date(2026, 11, 21), "Order now"),
        "CHG-HSG-210": (150, 110, 0, 40, 40, date(2026, 11, 25), "Order now"),
        "USB-220": (150, 60, 50, 40, 40, date(2026, 11, 25), "Order now"),
    },
    "Longer supplier lead times": {
        "LED-100": (200, 120, 40, 40, 40, date(2026, 11, 9), "At risk: expedite"),
        "LAM-HSG-110": (200, 240, 0, 0, 0, None, "Covered"),
        "SCR-120": (1000, 900, 0, 100, 200, date(2026, 11, 11), "At risk: expedite"),
        "ADP-130": (200, 150, 0, 50, 50, date(2026, 11, 4), "At risk: expedite"),
        "PCB-200": (100, 90, 20, 0, 0, None, "Covered"),
        "CHG-HSG-210": (100, 110, 0, 0, 0, None, "Covered"),
        "USB-220": (100, 60, 50, 0, 0, None, "Covered"),
    },
    "Extra opening stock": {
        "LED-100": (200, 270, 40, 0, 0, None, "Covered"),
        "LAM-HSG-110": (200, 240, 0, 0, 0, None, "Covered"),
        "SCR-120": (1000, 1100, 0, 0, 0, None, "Covered"),
        "ADP-130": (200, 250, 0, 0, 0, None, "Covered"),
        "PCB-200": (100, 90, 20, 0, 0, None, "Covered"),
        "CHG-HSG-210": (100, 110, 0, 0, 0, None, "Covered"),
        "USB-220": (100, 60, 50, 0, 0, None, "Covered"),
    },
}


@pytest.mark.parametrize("scenario", EXPECTED)
def test_dashboard_scenario_results(scenario):
    app = AppTest.from_file(Path(__file__).parent.parent / "app.py", default_timeout=10).run()
    if scenario != "Base plan":
        app.radio[0].set_value(scenario).run()

    assert not app.exception
    actual = app.dataframe[0].value.set_index("Component SKU")
    assert set(actual.index) == set(EXPECTED[scenario])

    columns = (
        "Gross need", "Usable stock", "Incoming on time", "Shortage",
        "Order suggestion", "Order by", "Assessment",
    )
    for sku, expected in EXPECTED[scenario].items():
        assert tuple(actual.loc[sku, list(columns)]) == expected, (scenario, sku)
