"""Phase 5C Streamlit regression checks against the Phase 5A design oracle."""

from datetime import date
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from factoryflow import data


APP = Path(__file__).parent.parent / "app.py"


def dashboard():
    app = AppTest.from_file(APP, default_timeout=30).run()
    assert not app.exception
    return app


def scenario(code):
    app = dashboard()
    app.get_by_key("ecn_view").set_value("Scenario explorer").run()
    app.selectbox(key="ecn_scenario").select(code).run()
    assert not app.exception
    return app


def table(app, column):
    return next(frame.value for frame in app.dataframe
                if column in frame.value.columns)


def metric(app, label):
    return next(item.value for item in app.metric if item.label == label)


@pytest.mark.parametrize(
    "code,builds,revisions,old_usable,new_usable,total,unfinished",
    [
        ("A", [2, 2, 2, 2], ["A"] * 4, 0, 4, 8, 0),
        ("B", [2, 2], ["A", "A"], 4, 4, 4, 0),
        ("C", [2, 2, 2, 2], ["A", "A", "B", "B"], 4, 0, 8, 0),
        ("D", [2, 2, 1, 0], ["A", "A", "B", "B"], 4, 0, 5, 3),
        ("E", [2, 2, 2, 2], ["A", "A", "B", "B"], 0, 0, 8, 0),
        ("F", [2, 2, 0, 2], ["A", "A", "B", "B"], 4, 2, 6, 2),
        ("G", [2, 2, 2, 2], ["A"] * 4, 0, 4, 8, 0),
    ],
)
def test_documented_scenarios_show_engine_builds_revisions_and_stock(
    code, builds, revisions, old_usable, new_usable, total, unfinished,
):
    app = scenario(code)
    daily = table(app, "Active BOM revision")
    assert daily["Simulated buildable units"].tolist() == builds
    assert daily["Active BOM revision"].tolist() == revisions
    assert [str(day)[:10] for day in daily["Date"]] == (
        [f"2026-12-0{day}" for day in range(1, len(builds) + 1)]
    )
    assert int(metric(app, "ECN simulated builds")) == total
    assert int(metric(app, "ECN unfinished units")) == unfinished
    outstanding = table(app, "Outstanding demand")
    assert len(outstanding) == 1
    assert outstanding.iloc[0]["Outstanding demand"] == unfinished

    stock = table(app, "Closing physical")
    closing = stock.groupby("Component SKU").last()
    assert closing.loc["LED-100", "Closing usable"] == old_usable
    assert closing.loc["LED-101", "Closing usable"] == new_usable
    assert (stock["Closing usable"] >= 0).all()
    assert (
        stock["Opening usable"] + stock["Confirmed receipts"]
        - stock["Authorized hold"] - stock["Simulated use"]
        == stock["Closing usable"]
    ).all()

    revision = table(app, "BOM revision")
    assert revision.loc[revision["BOM revision"] == "A",
                        "Simulated builds"].sum() == sum(
        qty for qty, rev in zip(builds, revisions) if rev == "A"
    )
    assert revision.loc[revision["BOM revision"] == "B",
                        "Simulated builds"].sum() == sum(
        qty for qty, rev in zip(builds, revisions) if rev == "B"
    )
    trace = table(app, "Active revision")
    assert trace["Active revision"].tolist() == revisions
    assert trace["Simulated units"].tolist() == builds


def test_new_part_shortage_and_late_receipt_are_explained_without_invented_supply():
    shortage = scenario("D")
    advice = table(shortage, "Dated shortage").set_index("Component SKU")
    assert advice.loc["LED-101", "Dated shortage"] == 3
    assert advice.loc["LED-101", "Suggested purchase units"] == 5
    assert advice.loc["LED-101", "Theoretical release date"] == date(2026, 11, 26)
    assert table(shortage, "Fully completed by").iloc[1]["Fully completed by"] == (
        "Not reached in window"
    )

    late = scenario("F")
    receipt = table(late, "Confirmation")
    assert receipt[["Component SKU", "Quantity", "Confirmation"]].values.tolist() == [
        ["LED-101", 4, "Confirmed"]
    ]
    stock = table(late, "Closing physical")
    led = stock.loc[stock["Component SKU"] == "LED-101"]
    assert led["Confirmed receipts"].tolist() == [0, 0, 0, 4]
    assert led["Simulated use"].tolist() == [0, 0, 0, 2]


def test_excess_old_stock_is_held_physically_not_scrapped():
    app = scenario("E")
    old = table(app, "Closing physical")
    old = old.loc[old["Component SKU"] == "LED-100"].iloc[-1]
    assert (old["Closing physical"], old["Closing held"],
            old["Closing usable"]) == (8, 8, 0)
    assert (old["Reserved at snapshot"], old["Protected safety stock"]) == (0, 0)
    disposition = table(app, "Automatic stock change")
    assert disposition.iloc[0]["Automatic stock change"] == False


def test_conflicting_approved_revisions_publish_no_final_ecn_schedule():
    app = scenario("H")
    assert any("Conflicting approved ECNs" in item.value for item in app.error)
    assert any("No final ECN schedule" in item.value for item in app.warning)
    assert metric(app, "Valid Revision A baseline simulated builds") == "8"
    assert not any(item.label == "ECN simulated builds" for item in app.metric)
    assert not any("Active BOM revision" in frame.value.columns
                   for frame in app.dataframe)


def test_factory_plan_preserves_no_ecn_view_and_shared_component_priority():
    app = dashboard()
    assert any("SIMULATION ONLY" in item.value for item in app.warning)
    assert metric(app, "Simulated buildable units") == "260"
    assert metric(app, "Baseline simulated builds") == "260"
    assert metric(app, "ECN simulated builds") == "250"
    assert metric(app, "ECN unfinished units") == "50"

    app.number_input(key="ecn_new_opening").set_value(100).run()
    assert not app.exception
    assert metric(app, "Simulated buildable units") == "260"
    assert metric(app, "ECN simulated builds") == "270"
    revision = table(app, "BOM revision").set_index(
        ["Product SKU", "BOM revision"]
    )
    assert revision.loc[("FG-CHARGER-02", "A"), "Simulated builds"] == 100
    assert revision.loc[("FG-LAMP-01", "B"), "Simulated builds"] == 20
    stock = table(app, "Closing physical")
    screws = stock.loc[stock["Component SKU"] == "SCR-120"]
    assert screws["Simulated use"].sum() == 880
    assert screws.iloc[-1]["Closing usable"] == 20


def test_factory_backlog_is_shown_once_per_product_not_on_revision_rows():
    app = dashboard()
    revision = table(app, "BOM revision")
    assert revision.columns.tolist() == [
        "Product SKU", "BOM revision", "Simulated builds",
    ]
    assert revision.set_index(["Product SKU", "BOM revision"])[
        "Simulated builds"
    ].to_dict() == {
        ("FG-CHARGER-02", "A"): 100,
        ("FG-LAMP-01", "A"): 150,
        ("FG-LAMP-01", "B"): 0,
    }
    outstanding = table(app, "Outstanding demand").set_index("Product SKU")
    assert outstanding[["Product demand", "Simulated builds",
                        "Outstanding demand"]].to_dict("index") == {
        "FG-CHARGER-02": {
            "Product demand": 100, "Simulated builds": 100,
            "Outstanding demand": 0,
        },
        "FG-LAMP-01": {
            "Product demand": 200, "Simulated builds": 150,
            "Outstanding demand": 50,
        },
    }
    assert outstanding["Outstanding demand"].sum() == 50
    assert metric(app, "ECN simulated builds") == "250"
    assert metric(app, "ECN unfinished units") == "50"


def test_ecn_stock_table_shows_safety_stock_separately_from_holds():
    app = dashboard()
    stock = table(app, "Protected safety stock")
    screws = stock.loc[stock["Component SKU"] == "SCR-120"].set_index("Date")
    assert screws[["Opening usable", "Simulated use", "Closing usable",
                   "Closing physical", "Reserved at snapshot",
                   "Protected safety stock", "Closing held"]].to_numpy().tolist()[:2] == [
        [900, 440, 460, 560, 0, 100, 0],
        [460, 360, 100, 200, 0, 100, 0],
    ]


def test_stock_restrictions_are_sourced_from_inventory_not_balance_difference(
    monkeypatch,
):
    inventory = [item.copy() for item in data.INVENTORY]
    screws = next(item for item in inventory if item["sku"] == "SCR-120")
    screws["reserved"] = 25
    screws["safety_stock"] = 75
    monkeypatch.setattr(data, "INVENTORY", inventory)
    app = dashboard()
    stock = table(app, "Protected safety stock")
    screws = stock.loc[stock["Component SKU"] == "SCR-120"].iloc[0]
    assert (screws["Reserved at snapshot"],
            screws["Protected safety stock"]) == (25, 75)
    assert screws["Closing physical"] - screws["Closing usable"] == 100
    assert screws["Closing held"] == 0


def test_purchase_advice_caption_limits_nominal_scope_without_changing_advice():
    app = dashboard()
    captions = " ".join(item.value for item in app.caption)
    assert "nominal dated planning advice" in captions
    assert "not orders or confirmed receipts" in captions
    assert "may not cover unfinished demand carried beyond" in captions
    assert "does not purchase stock automatically" in captions
    assert "completion dates are not guaranteed" in captions
    advice = table(app, "Dated shortage").set_index("Component SKU")
    assert advice.loc["LED-101", "Suggested purchase units"] == 40


def test_unconfirmed_new_receipt_cannot_support_builds():
    app = dashboard()
    app.number_input(key="ecn_new_receipt_qty").set_value(4).run()
    assert metric(app, "ECN simulated builds") == "250"
    receipt = table(app, "Confirmation")
    assert receipt.loc[receipt["Component SKU"] == "LED-101",
                       "Confirmation"].iloc[0] == "Unconfirmed"
    led = table(app, "Closing physical")
    led = led.loc[led["Component SKU"] == "LED-101"]
    assert led["Confirmed receipts"].sum() == 0

    app.checkbox(key="ecn_new_receipt_confirmed").check().run()
    assert not app.exception
    assert metric(app, "ECN simulated builds") == "254"
    led = table(app, "Closing physical")
    led = led.loc[led["Component SKU"] == "LED-101"]
    assert led["Confirmed receipts"].sum() == 4


def test_wip_and_pinned_revision_show_manual_review_without_release():
    app = dashboard()
    app.selectbox(key="ecn_lot_mode").select("WIP on Revision A").run()
    assert not app.exception
    assert metric(app, "ECN simulated builds") == "100"
    review = table(app, "Review reason")
    assert "WIP manual review" in review["Review reason"].tolist()
    blocked_wip = review.loc[review["Review reason"] == "WIP manual review"]
    assert not blocked_wip.empty
    assert blocked_wip["Simulated units"].sum() == 0

    app.number_input(key="ecn_new_opening").set_value(50).run()
    app.selectbox(key="ecn_lot_mode").select("Released on Revision A").run()
    assert not app.exception
    review = table(app, "Review reason")
    assert "Released revision manual review" in review["Review reason"].tolist()
    assert metric(app, "ECN simulated builds") == "250"


def test_undefined_lot_dispatch_and_invalid_approval_fail_closed():
    app = dashboard()
    app.selectbox(key="ecn_lot_mode").select(
        "Two ready lots without dispatch rule"
    ).run()
    assert not app.exception
    assert any("Lot dispatch priority is undefined" in item.value
               for item in app.error)
    assert not any(item.label == "ECN simulated builds" for item in app.metric)

    app.selectbox(key="ecn_lot_mode").select("New unstarted lot").run()
    app.date_input(key="ecn_approval").set_value(date(2026, 12, 3)).run()
    assert not app.exception
    assert any("Effective date must be later" in item.value
               for item in app.error)
    assert not any(item.label == "ECN simulated builds" for item in app.metric)


def test_old_stock_disposition_proposal_never_posts_stock_change():
    app = dashboard()
    app.selectbox(key="ecn_disposition").select("scrap").run()
    assert not app.exception
    review = table(app, "Automatic stock change")
    assert review.iloc[0]["Disposition proposal"] == "scrap"
    assert review.iloc[0]["Physical on hand"] == 10
    assert review.iloc[0]["Automatic stock change"] == False

    app.selectbox(key="ecn_disposition").select("hold").run()
    app.number_input(key="ecn_old_hold").set_value(10).run()
    assert not app.exception
    review = table(app, "Automatic stock change")
    assert review.iloc[0]["Held units"] == 10
    assert review.iloc[0]["Physical on hand"] == 10
    assert review.iloc[0]["Automatic stock change"] == False
