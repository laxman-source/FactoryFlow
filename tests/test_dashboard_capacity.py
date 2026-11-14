"""Check the Streamlit controls and both planning sections together."""

from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).parent.parent / "app.py"


def dashboard():
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    assert not app.exception
    return app


def table_with(app, column):
    return next(frame.value for frame in app.dataframe if column in frame.value.columns)


def test_default_capacity_is_separate_from_material_shortages():
    app = dashboard()
    materials = table_with(app, "Component SKU").set_index("Component SKU")
    capacity = table_with(app, "Production line").set_index("Production line")

    assert {sku for sku, row in materials.iterrows() if row["Shortage"] > 0} == {
        "LED-100", "SCR-120", "ADP-130"
    }
    assert capacity.loc["Smart desk lamp line", "Units per day"] == 80
    assert capacity.loc["Wireless charger line", "Units per day"] == 60
    assert list(capacity["Working days needed"]) == [3, 2]
    assert list(capacity["Working days available"]) == [4, 4]
    assert list(capacity["Available capacity"]) == [320, 240]
    assert list(capacity["Capacity shortage"]) == [0, 0]
    assert list(capacity["Capacity-only finish estimate"]) == [date(2026, 12, 3), date(2026, 12, 2)]
    assert any("materials are short" in warning.value for warning in app.warning)
    assert not app.success


def test_adjusted_demand_highlights_capacity_shortage_and_late_finish():
    app = dashboard()
    app.number_input[0].set_value(350)
    app.number_input[1].set_value(150)
    app.run()

    assert not app.exception
    capacity = table_with(app, "Production line").set_index("Production line")
    lamp = capacity.loc["Smart desk lamp line"]
    charger = capacity.loc["Wireless charger line"]
    assert (lamp["Working days needed"], lamp["Capacity shortage"]) == (5, 30)
    assert lamp["Capacity-only finish estimate"] == date(2026, 12, 7)
    assert charger["Capacity shortage"] == 0
    assert next(metric.value for metric in app.metric if metric.label == "Lines past target") == "1"
    assert any("short 30 units" in error.value for error in app.error)


def test_completion_date_changes_available_capacity():
    app = dashboard()
    app.date_input(key="target_completion").set_value(date(2026, 12, 1)).run()

    assert not app.exception
    capacity = table_with(app, "Production line")
    assert list(capacity["Working days available"]) == [1, 1]
    assert list(capacity["Capacity shortage"]) == [120, 40]
    assert next(metric.value for metric in app.metric if metric.label == "Lines past target") == "2"


def test_weekend_start_uses_monday_as_first_production_day():
    app = dashboard()
    app.date_input[1].set_value(date(2026, 11, 28))  # Saturday
    app.date_input(key="target_completion").set_value(date(2026, 11, 30))
    app.run()

    assert not app.exception
    capacity = table_with(app, "Production line")
    assert list(capacity["First production day"]) == [date(2026, 11, 30)] * 2
    assert list(capacity["Working days available"]) == [1, 1]
    assert list(capacity["Available capacity"]) == [80, 60]
    assert list(capacity["Capacity shortage"]) == [120, 40]


def test_zero_demand_has_no_projected_finish_or_capacity_shortage():
    app = dashboard()
    app.number_input[0].set_value(0)
    app.number_input[1].set_value(0)
    app.run()

    assert not app.exception
    capacity = table_with(app, "Production line")
    assert list(capacity["Working days needed"]) == [0, 0]
    assert list(capacity["Capacity shortage"]) == [0, 0]
    assert capacity["Capacity-only finish estimate"].isna().all()
    assert any("No production is scheduled" in info.value for info in app.info)


def test_invalid_completion_date_shows_error_but_preserves_material_results():
    app = dashboard()
    app.date_input(key="target_completion").set_value(date(2026, 11, 30)).run()

    assert not app.exception
    assert any("Cannot calculate capacity" in error.value for error in app.error)
    assert len(table_with(app, "Component SKU")) == 7
    assert not any("Production line" in frame.value.columns for frame in app.dataframe)


def test_production_start_before_snapshot_shows_material_date_error():
    app = dashboard()
    app.date_input[1].set_value(date(2026, 11, 13)).run()

    assert not app.exception
    assert any("Cannot calculate plan" in error.value for error in app.error)
