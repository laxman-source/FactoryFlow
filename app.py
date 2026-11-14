"""Run with: python -m streamlit run app.py"""

from datetime import date

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

st.set_page_config(page_title="FactoryFlow | MRP Simulator", page_icon="🏭", layout="wide")
st.title("🏭 FactoryFlow")
st.caption("Manufacturing planning simulator · Phase 2 Stage 2 · 100% fictional factory data")

st.info(
    "**Your job as a supply planner:** Check component supply and production line capacity "
    "for the planned demand. This demo is not connected to any ERP."
)

with st.sidebar:
    st.header("Planning controls")
    scenario = st.radio(
        "Try a scenario",
        ["Base plan", "Demand surge", "Supplier delays", "Extra stock arrives"],
    )
    st.divider()
    qty_lamp = st.number_input(
        "Smart desk lamps", min_value=0, max_value=10000,
        value=350 if scenario == "Demand surge" else DEFAULT_DEMAND["FG-LAMP-01"], step=25,
    )
    qty_charger = st.number_input(
        "Wireless chargers", min_value=0, max_value=10000,
        value=150 if scenario == "Demand surge" else DEFAULT_DEMAND["FG-CHARGER-02"], step=25,
    )
    as_of = st.date_input("Planning snapshot", value=DEMO_AS_OF)
    production_date = st.date_input("Production start", value=DEMO_PRODUCTION_DATE)
    target_completion = st.date_input(
        "Target completion", value=date(2026, 12, 4), key="target_completion"
    )
    st.caption("The default dates are fixed so the demo produces repeatable results.")
    if st.button("Reset demand and dates"):
        st.session_state.clear()
        st.rerun()

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
    "wireless chargers make 60. Weekends are excluded."
)
try:
    capacity_plan = calculate_capacity_plan(
        demand=demand,
        lines=PRODUCTION_LINES,
        production_start=production_date,
        target_completion=target_completion,
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
            st.error(
                f"{row['line_name']}: short {row['capacity_shortage']} units by "
                f"{target_completion.isoformat()}; projected finish is "
                f"{row['projected_completion'].isoformat()}."
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
        "required_working_days": "Working days needed",
        "window_working_days": "Working days available",
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
        "Capacity is calculated separately from material supply. "
        "A line with zero demand has no projected completion date."
    )

with st.expander("Understand the capacity calculation"):
    st.markdown(
        """
- **Production window:** Production start through target completion, including both dates.
- **Working days:** Monday through Friday only; weekends add no capacity.
- **Working days needed:** Units planned divided by the line's daily capacity, rounded up.
- **Available capacity:** Working days in the window multiplied by units per day.
- **Capacity shortage:** Units planned minus available capacity, with a minimum of zero.
- **Projected completion:** The last working day needed when the line starts on the first weekday on or after production start.

This simple line calculation does not account for material shortages, holidays, overtime,
machine downtime, or other production constraints. Check the separate Material planning results.
        """
    )

st.divider()
st.caption("FactoryFlow Phase 2 Stage 2 · Built for portfolio learning · Fictional numbers only · No ERP integration")
