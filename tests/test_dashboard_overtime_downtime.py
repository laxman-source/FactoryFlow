"""Stage 3B checks for interactive overtime and full-day downtime."""

from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


APP_PATH = Path(__file__).parent.parent / "app.py"


def dashboard():
    app = AppTest.from_file(APP_PATH, default_timeout=10).run()
    assert not app.exception
    return app


def table_with(app, column):
    return next(frame.value for frame in app.dataframe if column in frame.value.columns)


def lamp_row(app):
    return table_with(app, "Capacity shortage").set_index("Production line").loc[
        "Smart desk lamp line"
    ]


def test_precise_lamp_scenario_with_and_without_overtime():
    app = dashboard()
    app.number_input(key="qty_lamp").set_value(250)
    app.number_input(key="lamp_overtime").set_value(20)
    app.text_area(key="lamp_downtime").set_value("2026-12-02")
    app.run()

    assert not app.exception
    lamp = lamp_row(app)
    assert (lamp["Units per day"], lamp["Overtime units/day"]) == (80, 20)
    assert (lamp["Downtime days"], lamp["Operating days"]) == (1, 3)
    assert (lamp["Available capacity"], lamp["Capacity shortage"]) == (300, 0)
    assert lamp["Projected completion"] == date(2026, 12, 4)

    daily = table_with(app, "Normal rate")
    lamp_daily = daily[daily["Production line"] == "Smart desk lamp line"]
    assert list(lamp_daily["Total capacity"]) == [100, 0, 100, 100]
    assert lamp_daily.iloc[1]["Full downtime"] == "Yes"
    assert any("materials are short" in warning.value for warning in app.warning)

    app.number_input(key="lamp_overtime").set_value(0).run()
    assert not app.exception
    lamp = lamp_row(app)
    assert (lamp["Available capacity"], lamp["Capacity shortage"]) == (240, 10)
    assert lamp["Projected completion"] == date(2026, 12, 7)
    assert any("short 10 units" in error.value for error in app.error)
    daily = table_with(app, "Normal rate")
    lamp_daily = daily[daily["Production line"] == "Smart desk lamp line"]
    assert list(lamp_daily["Total capacity"])[-3:] == [0, 0, 80]
    assert lamp_daily.iloc[-1]["Timing"] == "After target"


def test_multiple_downtime_dates_after_target_delay_late_finish():
    app = dashboard()
    app.number_input(key="qty_lamp").set_value(250)
    app.text_area(key="lamp_downtime").set_value("2026-12-02\n2026-12-07")
    app.run()

    assert not app.exception
    lamp = lamp_row(app)
    assert (lamp["Available capacity"], lamp["Capacity shortage"]) == (240, 10)
    assert lamp["Projected completion"] == date(2026, 12, 8)
    daily = table_with(app, "Normal rate")
    late_downtime = daily[
        (daily["Production line"] == "Smart desk lamp line")
        & (daily["Date"] == date(2026, 12, 7))
    ].iloc[0]
    assert (late_downtime["Full downtime"], late_downtime["Total capacity"]) == ("Yes", 0)


def test_overtime_and_downtime_are_independent_by_line():
    app = dashboard()
    app.number_input(key="qty_charger").set_value(200)
    app.number_input(key="charger_overtime").set_value(20)
    app.text_area(key="charger_downtime").set_value("2026-12-02")
    app.run()

    assert not app.exception
    rows = table_with(app, "Capacity shortage").set_index("Production line")
    assert rows.loc["Wireless charger line", "Available capacity"] == 240
    assert rows.loc["Wireless charger line", "Projected completion"] == date(2026, 12, 4)
    assert rows.loc["Smart desk lamp line", "Available capacity"] == 320
    assert rows.loc["Smart desk lamp line", "Projected completion"] == date(2026, 12, 3)


@pytest.mark.parametrize("dates", ["2026-12-99", "2026-12-02\n2026-12-02"])
def test_bad_downtime_input_shows_error_without_losing_material_results(dates):
    app = dashboard()
    app.text_area(key="lamp_downtime").set_value(dates).run()

    assert not app.exception
    assert any("Cannot calculate capacity" in error.value for error in app.error)
    assert len(table_with(app, "Component SKU")) == 7
    assert not any("Capacity shortage" in frame.value.columns for frame in app.dataframe)


def test_zero_demand_has_no_completion_date_with_capacity_options():
    app = dashboard()
    app.number_input(key="qty_lamp").set_value(0)
    app.number_input(key="qty_charger").set_value(0)
    app.number_input(key="lamp_overtime").set_value(20)
    app.text_area(key="lamp_downtime").set_value("2026-12-02")
    app.run()

    assert not app.exception
    capacity = table_with(app, "Capacity shortage")
    assert capacity["Projected completion"].isna().all()
    assert list(capacity["Capacity shortage"]) == [0, 0]
    assert any("No production is scheduled" in info.value for info in app.info)


def test_daily_table_shows_weekends_and_downtime_as_zero():
    app = dashboard()
    app.number_input(key="qty_lamp").set_value(1)
    app.date_input(key="production_date").set_value(date(2026, 11, 28))
    app.date_input(key="target_completion").set_value(date(2026, 11, 30))
    app.number_input(key="lamp_overtime").set_value(20)
    app.text_area(key="lamp_downtime").set_value("2026-11-30")
    app.run()

    assert not app.exception
    assert lamp_row(app)["Projected completion"] == date(2026, 12, 1)
    daily = table_with(app, "Normal rate")
    lamp_daily = daily[daily["Production line"] == "Smart desk lamp line"]
    assert list(lamp_daily["Total capacity"]) == [0, 0, 0, 100]


def test_reset_simulation_restores_all_controls():
    app = dashboard()
    app.radio(key="scenario").set_value("Demand surge").run()
    app.date_input(key="target_completion").set_value(date(2026, 12, 8))
    app.number_input(key="qty_lamp").set_value(250)
    app.number_input(key="lamp_overtime").set_value(20)
    app.text_area(key="lamp_downtime").set_value("2026-12-02")
    app.run()
    app.button(key="reset_simulation").click().run()

    assert not app.exception
    assert app.radio(key="scenario").value == "Base plan"
    assert app.number_input(key="qty_lamp").value == 200
    assert app.number_input(key="qty_charger").value == 100
    assert app.number_input(key="lamp_overtime").value == 0
    assert app.number_input(key="charger_overtime").value == 0
    assert app.text_area(key="lamp_downtime").value == ""
    assert app.text_area(key="charger_downtime").value == ""
    assert app.date_input(key="target_completion").value == date(2026, 12, 4)
    assert lamp_row(app)["Available capacity"] == 320
