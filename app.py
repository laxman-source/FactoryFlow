"""Run with: python -m streamlit run app.py"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from factoryflow.capacity import PRODUCTION_LINES, calculate_capacity_plan
from factoryflow.data import (
    BOM,
    DEFAULT_DEMAND,
    DEMO_AS_OF,
    DEMO_PRODUCTION_DATE,
    INVENTORY,
    PRODUCTS,
    RECEIPTS,
)
from factoryflow.planning import calculate_plan


def parse_downtime_dates(text, line_name):
    """Read one ISO calendar date per nonblank line for a production line."""
    dates = []
    for raw in text.splitlines():
        value = raw.strip()
        if not value:
            continue
        try:
            day = date.fromisoformat(value)
        except ValueError:
            raise ValueError(f"{line_name}: use one downtime date per line in YYYY-MM-DD form") from None
        if day.isoformat() != value:
            raise ValueError(f"{line_name}: use one downtime date per line in YYYY-MM-DD form")
        dates.append(day)
    return dates


def set_scenario_demand():
    surge = st.session_state["scenario"] == "Demand surge"
    st.session_state["qty_lamp"] = 350 if surge else DEFAULT_DEMAND["FG-LAMP-01"]
    st.session_state["qty_charger"] = 150 if surge else DEFAULT_DEMAND["FG-CHARGER-02"]


def reset_simulation():
    st.session_state["scenario"] = "Base plan"
    st.session_state["qty_lamp"] = DEFAULT_DEMAND["FG-LAMP-01"]
    st.session_state["qty_charger"] = DEFAULT_DEMAND["FG-CHARGER-02"]
    st.session_state["as_of"] = DEMO_AS_OF
    st.session_state["production_date"] = DEMO_PRODUCTION_DATE
    st.session_state["target_completion"] = date(2026, 12, 4)
    st.session_state["lamp_overtime"] = 0
    st.session_state["charger_overtime"] = 0
    st.session_state["lamp_downtime"] = ""
    st.session_state["charger_downtime"] = ""


st.set_page_config(page_title="FactoryFlow | MRP Simulator", page_icon="🏭", layout="wide")

st.session_state.setdefault("scenario", "Base plan")
st.session_state.setdefault("qty_lamp", DEFAULT_DEMAND["FG-LAMP-01"])
st.session_state.setdefault("qty_charger", DEFAULT_DEMAND["FG-CHARGER-02"])
st.session_state.setdefault("as_of", DEMO_AS_OF)
st.session_state.setdefault("production_date", DEMO_PRODUCTION_DATE)
st.session_state.setdefault("target_completion", date(2026, 12, 4))
st.session_state.setdefault("lamp_overtime", 0)
st.session_state.setdefault("charger_overtime", 0)
st.session_state.setdefault("lamp_downtime", "")
st.session_state.setdefault("charger_downtime", "")


st.title("🏭 FactoryFlow")
st.caption("Manufacturing planning simulator · Phase 2 Stage 3B · 100% fictional factory data")

st.info(
    "**Your job as a supply planner:** Check component supply and production line capacity "
    "for the planned demand. This demo is not connected to any ERP."
)

with st.sidebar:
    st.header("Planning controls")
    scenario = st.radio(
        "Try a scenario",
        ["Base plan", "Demand surge", "Supplier delays", "Extra stock arrives"],
        key="scenario", on_change=set_scenario_demand,
    )
    st.divider()
    qty_lamp = st.number_input(
        "Smart desk lamps", min_value=0, max_value=10000,
        step=25, key="qty_lamp",
    )
    qty_charger = st.number_input(
        "Wireless chargers", min_value=0, max_value=10000,
        step=25, key="qty_charger",
    )
    as_of = st.date_input("Planning snapshot", key="as_of")
    production_date = st.date_input("Production start", key="production_date")
    target_completion = st.date_input(
        "Target completion", key="target_completion"
    )
    st.caption("The default dates are fixed so the demo produces repeatable results.")
    with st.expander("Capacity options"):
        st.caption(
            "Overtime adds units on operating weekdays. Enter one full downtime date per line "
            "in YYYY-MM-DD form. A down line makes zero units, including overtime."
        )
        lamp_overtime = st.number_input(
            "Lamp overtime units per working day", min_value=0, max_value=10000,
            step=10, key="lamp_overtime",
        )
        lamp_downtime_text = st.text_area(
            "Lamp full downtime dates", key="lamp_downtime",
            placeholder="2026-12-02\n2026-12-07",
            help="Enter one date per line. Blank means no downtime. Dates after the target can delay a late finish.",
        )
        charger_overtime = st.number_input(
            "Charger overtime units per working day", min_value=0, max_value=10000,
            step=10, key="charger_overtime",
        )
        charger_downtime_text = st.text_area(
            "Charger full downtime dates", key="charger_downtime",
            placeholder="2026-12-03\n2026-12-08",
            help="Enter one date per line. Blank means no downtime. Dates after the target can delay a late finish.",
        )
    st.button("Reset simulation", key="reset_simulation", on_click=reset_simulation)

inventory = [row.copy() for row in INVENTORY]
if scenario == "Extra stock arrives":
    extra = {"LED-100": 150, "ADP-130": 100, "SCR-120": 200}
    for row in inventory:
        row["on_hand"] += extra.get(row["sku"], 0)

additional_lead = 15 if scenario == "Supplier delays" else 0
demand = {"FG-LAMP-01": int(qty_lamp), "FG-CHARGER-02": int(qty_charger)}
try:
    plan = calculate_plan(
        demand=demand,
        bom=BOM,
        inventory=inventory,
        receipts=RECEIPTS,
        as_of=as_of,
        production_date=production_date,
        extra_lead_days=additional_lead,
    )
except ValueError as exc:
    st.error(f"Cannot calculate plan: {exc}")
    st.stop()

shortages = [row for row in plan if row["net_shortage"] > 0]
late_risks = [row for row in shortages if row["status"] == "At risk: expedite"]
late_receipts = [row for row in plan if row["incoming_late"] > 0]

st.header("Material planning")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Finished units planned", int(qty_lamp) + int(qty_charger))
col2.metric("Component SKUs", len(plan))
col3.metric("Components short", len(shortages))
col4.metric("Late ordering risks", len(late_risks))

if not shortages:
    st.success("Materials covered for this single-date plan (based on the assumed stock and receipt data).")
else:
    st.warning(f"{len(shortages)} component(s) need purchasing. This does not assess factory capacity.")

st.subheader("MRP results")
visible_columns = {
    "sku": "Component SKU",
    "name": "Component",
    "gross_required": "Gross need",
    "usable_stock": "Usable stock",
    "incoming_on_time": "Incoming on time",
    "net_shortage": "Shortage",
    "suggested_order_qty": "Order suggestion",
    "latest_order_date": "Order by",
    "status": "Assessment",
}
results_df = pd.DataFrame(plan)
show_df = results_df[list(visible_columns)].rename(columns=visible_columns)
st.dataframe(show_df, width="stretch", hide_index=True, alt="Material requirements and purchase suggestions")
st.caption("Order suggestions round shortages up to full supplier packs. 'Order by' is the latest theoretical release date, not an approved purchase order.")

st.subheader("Recommended purchasing actions")
if shortages:
    for item in shortages:
        date_text = item["latest_order_date"].isoformat()
        label = f"{item['name']}: order {item['suggested_order_qty']} units (short {item['net_shortage']}) — release by {date_text}"
        if item["status"] == "At risk: expedite":
            st.error(f"⚠️ {label}. Lead time cannot meet the planned date from this snapshot.")
        else:
            st.write(f"• {label}")
else:
    st.write("No new purchases are needed for this simulation.")

if late_receipts:
    st.caption("Note: Some receipts arrive AFTER production start and are excluded from usable incoming supply.")

with st.expander("Understand the MRP calculation"):
    st.markdown(
        """
- **MPS (Master Production Schedule):** What finished products are planned, in what quantities, and when.
- **BOM (Bill of Materials):** What component quantities are needed for ONE finished unit.
- **Gross requirement:** Production quantity × BOM quantity, added across products that share components.
- **Usable stock:** On-hand minus reserved and safety stock (minimum zero).
- **Incoming on time:** Confirmed simulated receipts after the snapshot and on/before production start.
- **Net shortage:** Maximum of zero and gross requirement minus usable stock and incoming on time.
- **Suggested purchase:** Round the net shortage UP to full supplier pack quantities.
- **Latest order date:** Planned production date minus the assumed supplier lead time.

**Simplifications:** One-level BOM, one common production date, no production routing, no
scrap/yield losses, no purchasing approval workflow, and no real supplier commitments.
        """
    )

with st.expander("Inspect fictional data: finished products, BOM, stock, receipts"):
    st.write("Finished products")
    st.dataframe(pd.DataFrame(PRODUCTS), hide_index=True, width="stretch")
    st.write("Bill of Materials")
    st.dataframe(pd.DataFrame(BOM), hide_index=True, width="stretch")
    st.write("Inventory (including reserved quantities and safety stock)")
    st.dataframe(pd.DataFrame(inventory), hide_index=True, width="stretch")
    st.write("Incoming stock (note the due dates)")
    st.dataframe(pd.DataFrame(RECEIPTS), hide_index=True, width="stretch")

st.header("Production capacity")
st.caption(
    "Two fictional, dedicated lines: smart desk lamps make 80 units per working day; "
    "wireless chargers make 60. Weekends are excluded. Set overtime and downtime in Capacity options."
)
try:
    overtime_by_sku = {
        "FG-LAMP-01": int(lamp_overtime),
        "FG-CHARGER-02": int(charger_overtime),
    }
    downtime_by_sku = {
        "FG-LAMP-01": parse_downtime_dates(lamp_downtime_text, "Lamp line"),
        "FG-CHARGER-02": parse_downtime_dates(charger_downtime_text, "Charger line"),
    }
    capacity_plan = calculate_capacity_plan(
        demand=demand,
        lines=PRODUCTION_LINES,
        production_start=production_date,
        target_completion=target_completion,
        overtime_by_sku=overtime_by_sku,
        downtime_by_sku=downtime_by_sku,
    )
except ValueError as exc:
    st.error(f"Cannot calculate capacity: {exc}")
else:
    capacity_shortages = [row for row in capacity_plan if row["capacity_shortage"] > 0]
    missed_deadlines = [
        row for row in capacity_plan
        if row["projected_completion"] is not None
        and row["projected_completion"] > target_completion
    ]
    with st.container(horizontal=True):
        st.metric("Production lines", len(capacity_plan), border=True)
        st.metric("Working days in window", capacity_plan[0]["window_working_days"], border=True)
        st.metric(
            "Capacity-short units",
            sum(row["capacity_shortage"] for row in capacity_plan),
            border=True,
        )
        st.metric("Lines past target", len(missed_deadlines), border=True)

    if capacity_shortages:
        st.warning(f"{len(capacity_shortages)} production line(s) lack capacity by the target date.")
        for row in capacity_shortages:
            projected_text = (
                row["projected_completion"].isoformat()
                if row["projected_completion"] is not None else "unavailable"
            )
            st.error(
                f"{row['line_name']}: short {row['capacity_shortage']} units by "
                f"{target_completion.isoformat()}; projected finish is "
                f"{projected_text}."
            )
    elif shortages:
        st.warning(
            "Line capacity fits the window, but materials are short. "
            "Check Material planning before treating production as ready."
        )
    elif not any(row["demand"] for row in capacity_plan):
        st.info("No production is scheduled for zero demand.")
    else:
        st.success("Line capacity fits the window and the material plan shows no shortages.")

    capacity_columns = {
        "line_name": "Production line",
        "demand": "Units planned",
        "daily_capacity": "Units per day",
        "overtime_units_per_day": "Overtime units/day",
        "operating_daily_capacity": "Operating units/day",
        "required_working_days": "Working days needed",
        "window_working_days": "Working days available",
        "downtime_days_in_window": "Downtime days",
        "operating_working_days": "Operating days",
        "available_capacity": "Available capacity",
        "capacity_shortage": "Capacity shortage",
        "first_production_date": "First production day",
        "target_completion": "Target completion",
        "projected_completion": "Projected completion",
        "capacity_status": "Capacity assessment",
    }
    capacity_df = pd.DataFrame(capacity_plan)
    st.dataframe(
        capacity_df[list(capacity_columns)].rename(columns=capacity_columns),
        width="stretch",
        hide_index=True,
        alt="Production capacity and projected completion by line",
    )
    st.caption(
        "Working days available counts weekdays before downtime; operating days excludes full downtime. "
        "Capacity is calculated separately from material supply. "
        "A line with zero demand has no projected completion date."
    )

    st.subheader("Daily capacity")
    latest_finish = max(
        (row["projected_completion"] for row in capacity_plan
         if row["projected_completion"] is not None),
        default=target_completion,
    )
    display_end = max(target_completion, latest_finish)
    display_days = min((display_end - production_date).days + 1, 366)
    daily_rows = []
    downtime_sets = {sku: set(days) for sku, days in downtime_by_sku.items()}
    for offset in range(display_days):
        day = production_date + timedelta(days=offset)
        day_plan = calculate_capacity_plan(
            demand={},
            lines=PRODUCTION_LINES,
            production_start=day,
            target_completion=day,
            overtime_by_sku=overtime_by_sku,
            downtime_by_sku=downtime_by_sku,
        )
        for row in day_plan:
            daily_rows.append({
                "Date": day,
                "Day": day.strftime("%A"),
                "Production line": row["line_name"],
                "Normal rate": row["daily_capacity"],
                "Overtime rate": row["overtime_units_per_day"],
                "Full downtime": "Yes" if day in downtime_sets[row["finished_sku"]] else "No",
                "Total capacity": row["available_capacity"],
                "Timing": "After target" if day > target_completion else "In window",
            })
    st.dataframe(
        pd.DataFrame(daily_rows), width="stretch", hide_index=True,
        alt="Daily normal and overtime rates, downtime, and total line capacity",
    )
    st.caption(
        "Normal and overtime rates apply only on operating weekdays. "
        "Total capacity is zero on weekends or full downtime dates. "
        "The table includes late projected dates and shows up to 366 calendar days; "
        "the summary uses the full selected window."
    )

with st.expander("Understand the capacity calculation"):
    st.markdown(
        """
- **Production window:** Production start through target completion, including both dates.
- **Working days:** Monday through Friday only; weekends add no capacity.
- **Overtime:** Extra units added to a line's normal daily capacity on operating weekdays.
- **Full downtime:** A selected line makes no units on that date, even with overtime. Weekend dates already have zero capacity.
- **Working days needed:** Units planned divided by normal plus overtime units per operating day, rounded up.
- **Available capacity:** Operating weekdays in the window multiplied by normal plus overtime units per day.
- **Capacity shortage:** Units planned minus available capacity, with a minimum of zero.
- **Projected completion:** The last operating day needed after skipping weekends and the line's downtime dates, including dates after the target.

This simple line calculation does not account for material shortages, holidays,
partial downtime, or other production constraints. Check the separate Material planning results.
        """
    )

st.divider()
st.caption("FactoryFlow Phase 2 Stage 3B · Built for portfolio learning · Fictional numbers only · No ERP integration")
