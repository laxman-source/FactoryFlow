"""Phase 4C: dashboard controls must drive one consistent integrated plan."""

from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

from factoryflow.data import BOM


APP_PATH = Path(__file__).parent.parent / "app.py"
LAMP = "FG-LAMP-01"
CHARGER = "FG-CHARGER-02"


def dashboard():
    app = AppTest.from_file(APP_PATH, default_timeout=20).run()
    assert not app.exception
    return app


def table(app, column):
    return next(frame.value for frame in app.dataframe if column in frame.value.columns)


def metric(app, label):
    return next(item.value for item in app.metric if item.label == label)


def product_table(app):
    return table(app, "Why unfinished").set_index("Product SKU")


def daily_table(app):
    return table(app, "Simulated units buildable")


def component_table(app):
    return table(app, "Opening usable stock")


def test_default_integrated_results_and_day_by_day_build_sequence():
    app = dashboard()
    assert any(header.value == "Integrated Production Planning" for header in app.header)
    assert any("no production is recorded" in caption.value for caption in app.caption)
    assert any("assumes materials are available" in caption.value for caption in app.caption)
    assert (metric(app, "Total planned finished units"), metric(app, "Simulated buildable units"),
            metric(app, "Unfinished units"), metric(app, "Simulated completion")) == (
        "300", "260", "40", "86.67%"
    )
    products = product_table(app)
    assert (products.loc[LAMP, "Simulated buildable"], products.loc[LAMP, "Unfinished"]) == (160, 40)
    assert (products.loc[CHARGER, "Simulated buildable"], products.loc[CHARGER, "Unfinished"]) == (100, 0)
    assert "Material availability" in products.loc[LAMP, "Why unfinished"]
    daily = daily_table(app).pivot(index="Date", columns="Product SKU", values="Simulated units buildable")
    assert list(daily[LAMP]) == [80, 70, 10, 0]
    assert list(daily[CHARGER]) == [60, 40, 0, 0]
    assert metric(app, "Capacity unused for materials") == "90"
    assert any("not an optimised" in caption.value for caption in app.caption)


def test_changed_demand_updates_mrp_capacity_and_integrated_sections():
    app = dashboard()
    app.number_input(key="qty_lamp").set_value(100)
    app.number_input(key="qty_charger").set_value(50).run()
    assert not app.exception
    assert metric(app, "Simulated buildable units") == "150"
    assert metric(app, "Unfinished units") == "0"
    assert product_table(app).loc[LAMP, "Simulated buildable"] == 100
    capacity = table(app, "Capacity shortage").set_index("Production line")
    assert capacity.loc["Smart desk lamp line", "Units planned"] == 100
    mrp = table(app, "Gross need").set_index("Component SKU")
    assert mrp.loc["SCR-120", "Gross need"] == 500


def test_shorter_window_reduces_builds_and_capacity_together():
    app = dashboard()
    app.date_input(key="target_completion").set_value(date(2026, 12, 2)).run()
    assert not app.exception
    assert (metric(app, "Simulated buildable units"), metric(app, "Unfinished units")) == ("250", "50")
    daily = daily_table(app)
    assert set(daily["Date"]) == {date(2026, 12, 1), date(2026, 12, 2)}
    assert set(table(app, "Opening usable stock")["Date"]) == {
        date(2026, 12, 1), date(2026, 12, 2)
    }
    capacity = table(app, "Capacity shortage").set_index("Production line")
    assert capacity.loc["Smart desk lamp line", "Available capacity"] == 160


def test_overtime_and_downtime_flow_into_integrated_builds():
    app = dashboard()
    app.number_input(key="qty_lamp").set_value(100)
    app.number_input(key="qty_charger").set_value(0)
    app.date_input(key="target_completion").set_value(date(2026, 12, 1))
    app.number_input(key="lamp_overtime").set_value(20).run()
    assert not app.exception
    assert metric(app, "Simulated buildable units") == "100"
    assert table(app, "Capacity shortage").set_index("Production line").loc[
        "Smart desk lamp line", "Available capacity"] == 100
    app.text_area(key="lamp_downtime").set_value("2026-12-01").run()
    assert not app.exception
    assert metric(app, "Simulated buildable units") == "0"
    lamp = daily_table(app).set_index("Product SKU").loc[LAMP]
    assert lamp["Available capacity"] == 0
    assert lamp["Constraint reason"] == "Machine downtime"
    assert "Machine downtime" in product_table(app).loc[LAMP, "Why unfinished"]


def test_late_led_receipt_does_not_cover_earlier_production():
    app = dashboard()
    app.number_input(key="qty_lamp").set_value(150)
    app.number_input(key="qty_charger").set_value(0)
    app.number_input(key="lamp_overtime").set_value(100)
    app.date_input(key="production_date").set_value(date(2026, 11, 25))
    app.date_input(key="target_completion").set_value(date(2026, 11, 26)).run()
    assert not app.exception
    assert (metric(app, "Simulated buildable units"), metric(app, "Unfinished units")) == ("120", "30")
    led = component_table(app).query("`Component SKU` == 'LED-100'")
    assert list(led["Confirmed receipts"]) == [0, 0]
    assert list(led["Simulated component use"]) == [120, 0]


def test_shared_screws_are_consumed_once_under_priority_rule():
    app = dashboard()
    app.radio(key="scenario").set_value("Extra opening stock").run()
    app.number_input(key="qty_lamp").set_value(300).run()
    assert not app.exception
    products = product_table(app)
    assert (products.loc[CHARGER, "Simulated buildable"], products.loc[LAMP, "Simulated buildable"]) == (100, 225)
    assert products.loc[LAMP, "Unfinished"] == 75
    screws = component_table(app).query("`Component SKU` == 'SCR-120'")
    assert screws["Simulated component use"].sum() == 1100
    assert screws.iloc[-1]["Projected usable stock"] == 0
    assert "SCR-120" in " ".join(daily_table(app)["Material constraints"])


def test_dashboard_reports_material_and_capacity_when_both_limit_demand():
    app = dashboard()
    app.number_input(key="qty_lamp").set_value(350).run()
    assert not app.exception
    reason = product_table(app).loc[LAMP, "Why unfinished"]
    assert "Material availability" in reason
    assert "Production capacity" in reason


def test_component_ledger_conserves_stock_and_matches_finished_builds():
    app = dashboard()
    daily = daily_table(app)
    components = component_table(app)
    for sku, rows in components.groupby("Component SKU", sort=False):
        rows = rows.sort_values("Date")
        assert all(
            row["Opening usable stock"] + row["Confirmed receipts"]
            - row["Simulated component use"] == row["Projected usable stock"]
            for _, row in rows.iterrows()
        )
        assert list(rows["Projected usable stock"])[:-1] == list(rows["Opening usable stock"])[1:]
        expected_consumption = sum(
            int(day["Simulated units buildable"]) * line["qty_per_unit"]
            for _, day in daily.iterrows() for line in BOM
            if day["Product SKU"] == line["finished_sku"] and sku == line["component_sku"]
        )
        assert rows["Simulated component use"].sum() == expected_consumption
        assert (rows["Projected usable stock"] >= 0).all()


def test_zero_demand_uses_no_components_and_has_zero_completion_rate():
    app = dashboard()
    app.number_input(key="qty_lamp").set_value(0)
    app.number_input(key="qty_charger").set_value(0).run()
    assert not app.exception
    assert (metric(app, "Total planned finished units"), metric(app, "Simulated completion")) == (
        "0", "0.00%"
    )
    assert component_table(app)["Simulated component use"].sum() == 0


def test_supplier_delay_changes_mrp_lead_time_not_confirmed_receipts():
    app = dashboard()
    default_receipts = component_table(app)["Confirmed receipts"].sum()
    app.radio(key="scenario").set_value("Longer supplier lead times").run()
    assert not app.exception
    assert metric(app, "Simulated buildable units") == "260"
    assert component_table(app)["Confirmed receipts"].sum() == default_receipts
    assert any("confirmed receipt dates" in caption.value for caption in app.caption)
