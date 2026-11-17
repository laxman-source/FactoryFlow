"""MPS-3C UI checks use independent fictional scenario expectations."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest


APP = Path(__file__).parent.parent / "app.py"


def dashboard(code="baseline"):
    app = AppTest.from_file(APP, default_timeout=30).run()
    assert not app.exception
    if code != "baseline":
        app.selectbox(key="mps_scenario").select(code).run()
        assert not app.exception
    return app


def table(app, column, other=None):
    return next(
        element.value for element in app.dataframe
        if column in element.value.columns
        and (other is None or other in element.value.columns)
    )


def metric(app, label):
    return int(next(item.value for item in app.metric if item.label == label))


def messages(app, kind):
    return " ".join(str(item.value) for item in getattr(app, kind))


def test_demand_inputs_and_provisional_fg_projection_are_shown_once():
    app = dashboard()
    demand = table(app, "Effective demand")
    assert len(demand) == 6
    assert not demand.duplicated(["Planning date", "Finished SKU"]).any()
    first_lamp = demand.loc[
        (demand["Planning date"] == "2026-12-01")
        & (demand["Finished SKU"] == "FG-LAMP-01")
    ].iloc[0]
    assert (
        first_lamp["Firm customer orders"],
        first_lamp["Forecast"],
        first_lamp["Forecast consumed"],
        first_lamp["Effective demand"],
    ) == (25, 30, 25, 30)
    plan = table(app, "Provisional projected FG balance")
    lamp = plan.loc[
        (plan["Planning date"] == "2026-12-01")
        & (plan["Finished SKU"] == "FG-LAMP-01")
    ].iloc[0]
    assert (lamp["Production start"], lamp["Planned completion"]) == (
        "2026-12-01", "2026-12-01"
    )
    assert (lamp["Proposed MPS units"], lamp["Provisional projected FG balance"],
            lamp["Outstanding unmet demand"]) == (20, 10, 0)
    assert "No proposed completion is a confirmed finished-goods receipt" in (
        " ".join(item.value for item in app.get("caption"))
    )


def test_baseline_shows_separate_nominal_and_simulated_tables():
    app = dashboard()
    assert metric(app, "Proposed MPS units") == 41
    assert metric(app, "Simulated builds (resolved only)") == 41
    assert metric(app, "Known unbuilt units") == 0
    assert metric(app, "Unresolved units") == 0
    gross = table(app, "Gross component requirement", "BOM revision")
    screws = gross.loc[
        (gross["Requirement date"] == "2026-12-01")
        & (gross["Component"] == "SCR-120")
    ]
    assert set(screws["Finished SKU"]) == {"FG-LAMP-01", "FG-CHARGER-02"}
    assert screws["Gross component requirement"].sum() == 90
    ledger = table(app, "Nominal shortage")
    assert ledger.loc[
        (ledger["Requirement date"] == "2026-12-03")
        & (ledger["Component"] == "ADP-130"),
        "Confirmed receipts",
    ].iloc[0] == 20
    assert "Actual production" not in [item.label for item in app.metric]
    assert "Actual production and physical finished-goods receipts are not tracked" in (
        " ".join(item.value for item in app.get("caption"))
    )


def test_material_shortage_explains_proposed_vs_whole_unit_builds():
    app = dashboard("material")
    assert metric(app, "Proposed MPS units") == 41
    assert metric(app, "Simulated builds (resolved only)") == 29
    assert metric(app, "Known unbuilt units") == 12
    assert metric(app, "Unresolved units") == 0
    feasibility = table(app, "Known unbuilt units")
    first_lamp = feasibility.loc[
        (feasibility["Finished SKU"] == "FG-LAMP-01")
        & (feasibility["Production start"] == "2026-12-01")
    ].iloc[0]
    assert (first_lamp["Proposed MPS units"],
            first_lamp["Simulated buildable units"],
            first_lamp["Known unbuilt units"]) == (20, 18, 2)
    assert "Nominal material shortage: LED-100" in messages(app, "warning")
    assert "Complete-set material restriction" in messages(app, "warning")


def test_capacity_restriction_is_displayed_without_moving_dates():
    app = dashboard("capacity")
    assert metric(app, "Proposed MPS units") == 111
    assert metric(app, "Simulated builds (resolved only)") == 101
    feasibility = table(app, "Known unbuilt units")
    first_lamp = feasibility.loc[
        (feasibility["Finished SKU"] == "FG-LAMP-01")
        & (feasibility["Production start"] == "2026-12-01")
    ].iloc[0]
    assert (
        first_lamp["Proposed MPS units"],
        first_lamp["Simulated buildable units"],
        first_lamp["Known unbuilt units"],
        first_lamp["Daily available capacity"],
        first_lamp["Simulated capacity consumed"],
    ) == (90, 80, 10, 80, 80)
    assert "Daily capacity restriction" in messages(app, "warning")


def test_shared_stock_conflict_preserves_unresolved_and_hides_conditional_balance():
    app = dashboard("conflict")
    assert metric(app, "Proposed MPS units") == 41
    assert metric(app, "Known unbuilt units") == 0
    assert metric(app, "Unresolved units") == 41
    feasibility = table(app, "Known unbuilt units")
    assert feasibility["Simulated buildable units"].tolist() == ["Unresolved"] * 4
    assert feasibility["Unresolved units"].sum() == 41
    stock = table(app, "Balance status")
    conditional = stock.loc[stock["Balance status"] != "resolved"]
    assert not conditional.empty
    assert set(conditional["Opening usable"]) == {"Conditional"}
    assert set(conditional["Simulated closing usable"]) == {"Conditional"}
    assert "Shared-component allocation unresolved" in messages(app, "error")
    assert "FG-LAMP-01" in messages(app, "error")
    assert "FG-CHARGER-02" in messages(app, "error")
    assert "Conditional downstream component balances" in messages(app, "warning")


def test_approved_revision_is_labeled_on_material_and_feasibility_rows():
    app = dashboard("revision")
    gross = table(app, "Gross component requirement", "BOM revision")
    revised = gross.loc[
        (gross["Finished SKU"] == "FG-LAMP-01")
        & (gross["Requirement date"] == "2026-12-02")
    ]
    assert set(revised["BOM revision"]) == {"B"}
    assert "LED-101" in set(revised["Component"])
    assert "LED-100" not in set(revised["Component"])
    feasibility = table(app, "Known unbuilt units")
    lamp = feasibility.loc[
        (feasibility["Finished SKU"] == "FG-LAMP-01")
        & (feasibility["Production start"] == "2026-12-02")
    ].iloc[0]
    assert (lamp["BOM revision"], lamp["Simulated buildable units"],
            lamp["Known unbuilt units"]) == ("B", 8, 2)
    assert "LED-101" in messages(app, "warning")


def test_unsupported_wip_withholds_material_and_feasibility_results():
    app = dashboard("wip")
    assert "WIP disposition review required" in messages(app, "error")
    assert not any(item.label == "Simulated builds (resolved only)" for item in app.metric)
    assert not any(
        "Gross component requirement" in element.value.columns
        and "BOM revision" in element.value.columns
        for element in app.dataframe
    )
    assert table(app, "Effective demand").shape[0] == 6


def test_existing_dashboard_views_remain_visible():
    app = dashboard()
    headings = [item.value for item in app.get("header")]
    assert "Material planning" in headings
    assert "Production capacity" in headings
    assert "Integrated Production Planning" in headings
    assert "ECN simulation" in headings
    assert "MPS simulation" in headings
    assert app.selectbox(key="ecn_status")

