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
from factoryflow.material_timeline import calculate_material_timeline
from factoryflow.production_schedule import calculate_production_schedule
from factoryflow.ecn import (
    BOMRevision, ECN, ECNChangeLine, ProductionLot, StockHold,
    approve_ecn, cancel_ecn,
)
from factoryflow.ecn_planning import calculate_ecn_plan
from factoryflow.ecn_scenarios import SCENARIO_NAMES, SCENARIO_NOTES, scenario_inputs


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
st.caption("Manufacturing planning simulator · Phase 5C · 100% fictional factory data")

st.info(
    "**Your job as a supply planner:** Check component supply and production line capacity "
    "for the planned demand. This demo is not connected to any ERP."
)

with st.sidebar:
    st.header("Planning controls")
    scenario = st.radio(
        "Try a scenario",
        ["Base plan", "Demand surge", "Longer supplier lead times", "Extra opening stock"],
        key="scenario", on_change=set_scenario_demand,
    )
    st.caption(
        "Longer lead times change purchase advice, not confirmed receipts. "
        "Extra opening stock is available at the planning snapshot."
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
if scenario == "Extra opening stock":
    extra = {"LED-100": 150, "ADP-130": 100, "SCR-120": 200}
    for row in inventory:
        row["on_hand"] += extra.get(row["sku"], 0)

additional_lead = 15 if scenario == "Longer supplier lead times" else 0
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
capacity_plan = None
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
                f"{target_completion.isoformat()}; capacity-only finish estimate is "
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
        st.success(
            "Capacity-only calculation fits the window and single-date MRP shows no shortages. "
            "Check the integrated simulation for material-constrained output."
        )

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
        "projected_completion": "Capacity-only finish estimate",
        "capacity_status": "Capacity assessment",
    }
    capacity_df = pd.DataFrame(capacity_plan)
    st.dataframe(
        capacity_df[list(capacity_columns)].rename(columns=capacity_columns),
        width="stretch",
        hide_index=True,
        alt="Capacity-only calculation and finish estimate by line",
    )
    st.caption(
        "Working days available counts weekdays before downtime; operating days excludes full downtime. "
        "The capacity-only finish estimate assumes materials are available; it is not the "
        "material-constrained result shown in the integrated simulation. "
        "A line with zero demand has no projected completion date."
    )

    st.subheader("Daily capacity-only estimate")
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
- **Capacity-only finish estimate:** The last operating day needed after skipping weekends and the line's downtime dates, including dates after the target, assuming all required materials are available.

This simple line calculation does not account for material shortages, holidays,
partial downtime, or other production constraints. Check the integrated simulation
for material-constrained output.
        """
    )

st.header("Integrated Production Planning")
st.caption(
    "This view combines confirmed component supply with each line's available capacity "
    "from production start through target completion. It estimates units buildable "
    "inside that window; unfinished units have no assumed future completion date. "
    "All output and component use below are simulated; no production is recorded."
)
if capacity_plan is None:
    st.info("Enter a valid production window and downtime dates to see the integrated plan.")
else:
    try:
        integrated = calculate_production_schedule(
            demand=demand,
            bom=BOM,
            inventory=inventory,
            receipts=RECEIPTS,
            as_of=as_of,
            production_start=production_date,
            production_end=target_completion,
            lines=PRODUCTION_LINES,
            overtime_by_sku=overtime_by_sku,
            downtime_by_sku=downtime_by_sku,
        )
        # Replay only components used by completed units. Phase 4A applies the
        # same receipt timing and opening usable-stock rules for the display.
        actual_component_needs = [
            {"date": row["date"], "component_sku": sku, "qty": quantity}
            for row in integrated["daily_schedule"]
            for sku, quantity in row["components_consumed"].items()
        ]
        material_ledger = calculate_material_timeline(
            inventory, RECEIPTS, actual_component_needs, as_of, target_completion,
        )
    except ValueError as exc:
        st.error(f"Cannot calculate integrated plan: {exc}")
    else:
        result = integrated["summary"]
        completion_pct = (
            100 * result["total_completed"] / result["total_demand"]
            if result["total_demand"] else 0
        )
        with st.container(horizontal=True):
            st.metric("Total planned finished units", result["total_demand"], border=True)
            st.metric("Simulated buildable units", result["total_completed"], border=True)
            st.metric("Unfinished units", result["total_remaining"], border=True)
            st.metric("Simulated completion", f"{completion_pct:.2f}%", border=True)

        st.caption(
            "Shared parts go first to the product with the alphabetically earlier finished SKU "
            "(chargers before lamps). This fixed demonstration rule is not an optimised "
            "production priority. MRP order suggestions are not counted as receipts."
        )
        if scenario == "Longer supplier lead times":
            st.caption(
                "Longer supplier lead times change MRP release advice only. The confirmed "
                "receipt dates shown here remain unchanged."
            )

        st.subheader("Simulated output versus unfinished demand by product")
        product_rows = []
        for product in result["by_product"]:
            sku = product["finished_sku"]
            reasons = []
            if "material" in product["remaining_reasons"]:
                reasons.append("Material availability")
            if "capacity" in product["remaining_reasons"]:
                reasons.append("Production capacity")
            if product["remaining_units"] and any(
                row["finished_sku"] == sku and row["line_state"] == "Downtime"
                and row["planned_remaining_demand"] > 0
                for row in integrated["daily_schedule"]
            ):
                reasons.append("Machine downtime reduced capacity")
            product_rows.append({
                "Product SKU": sku,
                "Demand": product["demand"],
                "Simulated buildable": product["completed_units"],
                "Unfinished": product["remaining_units"],
                "Why unfinished": "; ".join(reasons) if reasons else "Complete",
            })
        st.dataframe(
            pd.DataFrame(product_rows), width="stretch", hide_index=True,
            alt="Simulated buildable and unfinished units with modeled constraints by product",
        )

        st.subheader("Simulated daily production")
        line_names = {line["finished_sku"]: line["name"] for line in PRODUCTION_LINES}
        daily_rows = []
        unused_for_materials = 0
        for row in integrated["daily_schedule"]:
            material_limited = "material" in row["constraints"]
            unused = (
                min(row["planned_remaining_demand"], row["available_capacity"])
                - row["actual_buildable_units"]
                if material_limited else 0
            )
            unused_for_materials += unused
            if row["planned_remaining_demand"] == 0:
                reason = "No demand remaining"
            elif row["line_state"] == "Downtime":
                reason = "Machine downtime"
            elif row["line_state"] == "Weekend":
                reason = "Weekend: no production"
            elif len(row["constraints"]) == 2:
                reason = "Material and capacity"
            elif material_limited:
                reason = "Material availability"
            elif "capacity" in row["constraints"]:
                reason = "Production capacity"
            else:
                reason = "None"
            critical = (
                ", ".join(
                    f"{sku} ({row['available_components'][sku]} usable)"
                    for sku in row["critical_components"]
                ) if material_limited else "None"
            )
            daily_rows.append({
                "Date": row["date"],
                "Product SKU": row["finished_sku"],
                "Production line": line_names[row["finished_sku"]],
                "Available capacity": row["available_capacity"],
                "Simulated units buildable": row["actual_buildable_units"],
                "Remaining demand": row["unfinished_demand"],
                "Material constraints": critical,
                "Constraint reason": reason,
                "Capacity unused for materials": unused,
            })
        st.dataframe(
            pd.DataFrame(daily_rows), width="stretch", hide_index=True,
            alt="Daily simulated buildable units, remaining demand, and limiting components",
        )
        st.metric("Capacity unused for materials", unused_for_materials, border=True)
        st.caption(
            "Unused capacity counts units that a line could have built that day if its "
            "required components had been available. Weekend and downtime capacity is zero."
        )

        st.subheader("Simulated component use and projected usable stock")
        component_rows = [
            {
                "Date": row["date"],
                "Component SKU": row["component_sku"],
                "Opening usable stock": row["opening_balance"],
                "Confirmed receipts": row["receipts"],
                "Simulated component use": row["consumption"],
                "Projected usable stock": row["closing_balance"],
            }
            for row in material_ledger
            if production_date <= row["date"] <= target_completion
        ]
        st.dataframe(
            pd.DataFrame(component_rows), width="stretch", hide_index=True,
            alt="Daily component receipts, simulated use, and projected usable stock",
        )
        st.caption(
            "Usable stock excludes reserved and safety stock. Confirmed receipts are added "
            "before same-day production; receipts before production start are included "
            "in the first day's opening balance. Simulated component use includes parts "
            "only for finished units the model could build."
        )

st.divider()
st.header("ECN simulation")
st.warning(
    "SIMULATION ONLY — this section records no approval, production, purchase, "
    "inventory posting, scrap, return, or WIP release."
)
st.caption(
    "ECN-001 replaces one LED-100 with one LED-101 in each smart desk lamp. "
    "Revision A remains the baseline; Revision B is selected by simulated production date "
    "only when the change is approved."
)

with st.sidebar:
    st.divider()
    st.header("ECN controls")
    ecn_view = st.segmented_control(
        "ECN view", ["Factory plan", "Scenario explorer"],
        default="Factory plan", key="ecn_view",
    )
ecn_inputs = None
ecn_note = None
lot_mode = "New unstarted lot"
if ecn_view == "Scenario explorer":
    with st.sidebar:
        ecn_code = st.selectbox(
            "Design scenario A–H", list(SCENARIO_NAMES),
            format_func=lambda code: SCENARIO_NAMES[code], key="ecn_scenario",
        )
    ecn_inputs = scenario_inputs(ecn_code)
    ecn_note = SCENARIO_NOTES[ecn_code]
    st.info(ecn_note)
    st.caption(
        "These fixed fictional examples use two lamp units of daily capacity and "
        "the independently calculated inputs in docs/ECN_DESIGN.md. "
        "They do not use the main dashboard sidebar demand."
    )
elif capacity_plan is None:
    st.info("Enter valid production dates and downtime before simulating the factory ECN plan.")
else:
    st.subheader("Factory ECN inputs")
    st.caption(
        "Use the sidebar ECN controls for a local example only. LED-101 has an explicit "
        "fictional master: seven calendar-day lead time and five-unit supplier packs."
    )
    with st.sidebar:
        with st.container(border=True):
            ecn_state = st.selectbox(
                "Simulated ECN status", ["Approved", "Draft", "Cancelled"],
                key="ecn_status",
            )
            ecn_effective = st.date_input(
                "Proposed effective date", value=date(2026, 12, 3),
                key="ecn_effective",
            )
            ecn_approval = st.date_input(
                "Fictional approval date", value=date(2026, 12, 2),
                key="ecn_approval",
            )
            disposition = st.selectbox(
                "Old LED-100 disposition proposal",
                ["hold", "use-up", "return", "scrap"], key="ecn_disposition",
            )
            new_opening = st.number_input(
                "LED-101 opening on-hand units", min_value=0, max_value=100000,
                value=0, key="ecn_new_opening",
            )
            new_receipt_qty = st.number_input(
                "LED-101 dated receipt units", min_value=0, max_value=100000,
                value=0, key="ecn_new_receipt_qty",
            )
            new_receipt_date = st.date_input(
                "LED-101 receipt due date", value=date(2026, 12, 4),
                key="ecn_new_receipt_date",
            )
            new_receipt_confirmed = st.checkbox(
                "LED-101 receipt confirmed", value=False,
                key="ecn_new_receipt_confirmed",
            )
            old_receipt_confirmed = st.checkbox(
                "Demo LED-100 receipt confirmed", value=True,
                key="ecn_old_receipt_confirmed",
            )
            old_hold_qty = st.number_input(
                "Authorized LED-100 hold units at effect",
                min_value=0, max_value=100000, value=0,
                disabled=ecn_state != "Approved", key="ecn_old_hold",
            )
            lot_mode = st.selectbox(
                "Lamp lot state to simulate",
                ["New unstarted lot", "Released on Revision A",
                 "WIP on Revision A", "Two ready lots without dispatch rule"],
                key="ecn_lot_mode",
            )

    try:
        ecn_inventory = [item.copy() for item in inventory]
        ecn_inventory.append({
            "sku": "LED-101", "name": "Replacement LED board (fictional)",
            "on_hand": int(new_opening), "reserved": 0, "safety_stock": 0,
            "lead_days": 7, "pack_size": 5,
        })
        ecn_receipts = [
            {**item, "confirmed": (
                bool(old_receipt_confirmed)
                if item["component_sku"] == "LED-100"
                else item.get("confirmed", True)
            )}
            for item in RECEIPTS
        ]
        if new_receipt_qty:
            ecn_receipts.append({
                "component_sku": "LED-101", "qty": int(new_receipt_qty),
                "due_date": new_receipt_date,
                "confirmed": bool(new_receipt_confirmed),
            })
        revision_b = BOMRevision(
            "FG-LAMP-01", "B",
            tuple(
                ("LED-101" if line["component_sku"] == "LED-100"
                 else line["component_sku"], line["qty_per_unit"])
                for line in BOM if line["finished_sku"] == "FG-LAMP-01"
            ),
        )
        draft_notice = ECN(
            "ECN-001", "FG-LAMP-01", "A", "B", ecn_effective,
            (ECNChangeLine("LED-100", "LED-101", 1, 1),), disposition,
        )
        if ecn_state == "Draft":
            notice = draft_notice
        else:
            approved_notice = approve_ecn(
                draft_notice, approval_date=ecn_approval,
                effective_date=ecn_effective,
                approved_by="Fictional engineering approver",
                base_bom=BOM, proposed_revisions=[revision_b],
                inventory=ecn_inventory,
            )
            notice = (
                approved_notice if ecn_state == "Approved"
                else cancel_ecn(
                    approved_notice, cancellation_date=ecn_approval,
                    reason="Fictional pre-effective cancellation",
                )
            )
        holds = []
        if ecn_state == "Approved" and old_hold_qty:
            holds.append(StockHold(
                "LED-100", int(old_hold_qty), ecn_effective,
                "Fictional stock controller", ecn_approval,
            ))
        lots = None
        if lot_mode != "New unstarted lot":
            lamp_qty = demand["FG-LAMP-01"]
            lots = [ProductionLot(
                "SIM-CHARGER", "FG-CHARGER-02",
                demand["FG-CHARGER-02"], as_of,
            )]
            if lot_mode == "Two ready lots without dispatch rule":
                if lamp_qty < 2:
                    raise ValueError(
                        "Two ready lamp lots require at least two lamp units."
                    )
                lots.extend([
                    ProductionLot("SIM-LAMP-1", "FG-LAMP-01",
                                  lamp_qty // 2, as_of),
                    ProductionLot("SIM-LAMP-2", "FG-LAMP-01",
                                  lamp_qty - lamp_qty // 2, as_of),
                ])
            else:
                state = (
                    "released" if lot_mode == "Released on Revision A"
                    else "wip"
                )
                lots.append(ProductionLot(
                    "SIM-LAMP", "FG-LAMP-01", lamp_qty, as_of,
                    state, "A",
                ))
        ecn_inputs = {
            "demand": demand, "base_bom": BOM,
            "inventory": ecn_inventory, "receipts": ecn_receipts,
            "as_of": as_of, "production_start": production_date,
            "production_end": target_completion,
            "proposed_revisions": [revision_b], "ecns": [notice],
            "stock_holds": holds, "lots": lots, "lines": PRODUCTION_LINES,
            "overtime_by_sku": overtime_by_sku,
            "downtime_by_sku": downtime_by_sku,
        }
    except ValueError as exc:
        st.error(f"ECN input rejected: {exc}")

if ecn_inputs is not None:
    notice = ecn_inputs["ecns"][0]
    st.subheader("ECN overview")
    with st.container(horizontal=True):
        st.metric("Simulated ECN state", notice.status.title(), border=True)
        st.metric("Revision change", "A → B", border=True)
        st.metric(
            "Proposed effective date",
            notice.proposed_effective_date.isoformat(), border=True,
        )
        st.metric(
            "Approved effective date",
            notice.effective_date.isoformat()
            if notice.status == "approved" else "Inactive",
            border=True,
        )
    st.caption(
        "Draft and cancelled notices leave Revision A active. "
        "An approved notice selects Revision B on its effective production date. "
        "Approval is scenario data, not a transaction in FactoryFlow."
    )

    baseline_inputs = {**ecn_inputs, "ecns": ()}
    if lot_mode == "Two ready lots without dispatch rule":
        baseline_inputs["lots"] = None
    baseline_plan = None
    ecn_plan = None
    try:
        baseline_plan = calculate_ecn_plan(**baseline_inputs)
        ecn_plan = calculate_ecn_plan(**ecn_inputs)
    except ValueError as exc:
        st.error(f"ECN plan rejected: {exc}")
        st.warning(
            "No final ECN schedule or component consumption is published "
            "for this invalid plan."
        )

    if ecn_plan is not None:
        baseline_summary = baseline_plan["summary"]
        ecn_summary = ecn_plan["summary"]
        impact = (
            ecn_summary["total_completed"] - baseline_summary["total_completed"]
        )
        with st.container(horizontal=True):
            st.metric(
                "Baseline simulated builds",
                baseline_summary["total_completed"], border=True,
            )
            st.metric(
                "ECN simulated builds",
                ecn_summary["total_completed"], border=True,
            )
            st.metric("ECN build change vs baseline", impact, border=True)
            st.metric(
                "ECN unfinished units",
                ecn_summary["total_remaining"], border=True,
            )
        st.caption(
            "Both plans use the same fictional demand, stock, receipts, capacity "
            "and lot state. The baseline keeps Revision A. "
            "An authorized stock hold, when selected, applies to both plans."
        )

        st.subheader("ECN impact comparison")
        comparison = []
        for label, current in (
            ("Revision A baseline", baseline_plan),
            ("Selected ECN state", ecn_plan),
        ):
            summary = current["summary"]
            built_dates = [
                row["date"] for row in current["revision_trace"]
                if row["simulated_units"] > 0
            ]
            completed_by = (
                max(built_dates).isoformat()
                if summary["complete"] and built_dates
                else "No demand" if summary["total_demand"] == 0
                else "Not reached in window"
            )
            comparison.append({
                "Plan": label,
                "Simulated builds": summary["total_completed"],
                "Unfinished": summary["total_remaining"],
                "Dated nominal component shortage": sum(
                    row["dated_shortage"]
                    for row in current["purchase_advice"]
                ),
                "Fully completed by": completed_by,
            })
        st.dataframe(
            pd.DataFrame(comparison), hide_index=True, width="stretch",
            alt="Baseline and ECN simulated builds, shortages and supported completion dates",
        )
        st.caption(
            "The date appears only when all demand was simulated as built "
            "within the selected window. Dated shortages come from planned "
            "component requirements before material-constrained scheduling; "
            "purchase advice does not create a receipt. Capacity-only finish "
            "estimates remain in the separate Production capacity section."
        )

        st.subheader("Production planning by BOM revision")
        revision_rows = []
        for product in ecn_summary["by_product"]:
            for revision in ("A", "B"):
                if revision == "B" and product["finished_sku"] != "FG-LAMP-01":
                    continue
                revision_rows.append({
                    "Product SKU": product["finished_sku"],
                    "BOM revision": revision,
                    "Simulated builds": product["completed_by_revision"].get(
                        revision, 0
                    ),
                    "Unfinished product demand": product["remaining_units"],
                    "Manual-review units": product["review_required_units"],
                })
        st.dataframe(
            pd.DataFrame(revision_rows), hide_index=True, width="stretch",
            alt="Simulated finished units by product and BOM revision",
        )
        daily_rows = [{
            "Date": row["date"],
            "Product SKU": row["finished_sku"],
            "Active BOM revision": row["bom_revision"],
            "Line state": row["line_state"],
            "Available capacity": row["available_capacity"],
            "Demand remaining at day start": row["planned_remaining_demand"],
            "Simulated buildable units": row["actual_buildable_units"],
            "Unfinished after day": row["unfinished_demand"],
            "WIP review units": row["blocked_wip_units"],
            "Pinned-revision review units": row["blocked_revision_units"],
            "Constraints": ", ".join(row["constraints"]) or "None",
        } for row in ecn_plan["daily_schedule"]]
        st.dataframe(
            pd.DataFrame(daily_rows), hide_index=True, width="stretch",
            alt="Daily ECN production capacity, simulated builds and unfinished demand",
        )

        st.subheader("Production-date and revision trace")
        trace_rows = [{
            "Date": row["date"], "Order or lot": row["order_id"],
            "Product SKU": row["finished_sku"],
            "Active revision": row["active_revision"],
            "Built revision": row["bom_revision"] or "Blocked",
            "ECN reference": row["ecn_reference"] or "None",
            "Simulated units": row["simulated_units"],
            "Review reason": row["block_reason"] or "None",
        } for row in ecn_plan["revision_trace"]]
        st.dataframe(
            pd.DataFrame(trace_rows), hide_index=True, width="stretch",
            alt="Simulated production dates, lots, ECN references and BOM revisions",
        )

        st.subheader("Material availability and shortages")
        st.caption(
            "LED-100 and LED-101 are separate stock records. SCR-120 is the "
            "shared factory component; scenario fixtures use SCR for lamps only."
        )
        stock_rows = [{
            "Date": row["date"], "Component SKU": row["component_sku"],
            "Opening usable": row["opening_usable"],
            "Confirmed receipts": row["confirmed_receipts"],
            "Authorized hold": row["authorized_hold"],
            "Simulated use": row["simulated_use"],
            "Closing usable": row["closing_usable"],
            "Closing physical": row["closing_physical"],
            "Closing held": row["closing_held"],
        } for row in ecn_plan["stock_ledger"]
            if row["date"] >= ecn_inputs["production_start"]
            and row["component_sku"] in {
                "LED-100", "LED-101", "SCR-120", "SCR"
            }]
        st.dataframe(
            pd.DataFrame(stock_rows), hide_index=True, width="stretch",
            alt="Separate LED and shared-component daily stock balances",
        )
        receipt_rows = [{
            "Component SKU": row["component_sku"],
            "Quantity": row["qty"], "Due date": row["due_date"],
            "Confirmation": (
                "Confirmed" if row.get("confirmed", True) else "Unconfirmed"
            ),
        } for row in ecn_inputs["receipts"]]
        if receipt_rows:
            st.dataframe(
                pd.DataFrame(receipt_rows), hide_index=True, width="stretch",
                alt="Fictional dated receipts and their confirmation status",
            )
        else:
            st.info("No dated supplier receipts in this scenario fixture.")
        st.caption(
            "Only confirmed receipts enter usable stock on their due date. "
            "Unconfirmed receipts and purchase suggestions are excluded."
        )
        shortage_rows = [{
            "Date": row["date"],
            "Component SKU": row["component_sku"],
            "Nominal requirement": row["requirement"],
            "Simulated coverage": row["simulated_coverage"],
            "Unmet dated need": row["unmet_need"],
        } for row in ecn_plan["requirement_ledger"]
            if row["unmet_need"] > 0]
        if shortage_rows:
            st.dataframe(
                pd.DataFrame(shortage_rows), hide_index=True,
                width="stretch",
                alt="Dated component needs unmet before material-constrained scheduling",
            )
        else:
            st.info("No dated component shortages in the nominal plan.")
        if ecn_plan["purchase_advice"]:
            st.dataframe(
                pd.DataFrame(ecn_plan["purchase_advice"]).rename(columns={
                    "component_sku": "Component SKU",
                    "dated_shortage": "Dated shortage",
                    "first_shortage_date": "First shortage date",
                    "suggested_order_qty": "Suggested purchase units",
                    "lead_days": "Supplier lead days",
                    "latest_order_date": "Theoretical release date",
                    "status": "Advice status",
                }), hide_index=True, width="stretch",
                alt="Fictional supplier pack advice based on first dated shortage",
            )

        st.subheader("Exception management")
        review_rows = [
            row for row in trace_rows if row["Review reason"] != "None"
        ]
        if review_rows:
            st.dataframe(
                pd.DataFrame(review_rows), hide_index=True, width="stretch",
                alt="WIP and pinned-revision lots requiring manual review",
            )
        else:
            st.info("No WIP or pinned-revision lot needs review in this run.")
        held_rows = [
            row for row in stock_rows
            if row["Authorized hold"] or row["Closing held"]
        ]
        if held_rows:
            st.dataframe(
                pd.DataFrame(held_rows), hide_index=True, width="stretch",
                alt="Authorized stock holds and retained physical inventory",
            )
        if ecn_plan["disposition_review"]:
            st.dataframe(
                pd.DataFrame(ecn_plan["disposition_review"]).rename(columns={
                    "component_sku": "Old component SKU",
                    "disposition": "Disposition proposal",
                    "physical_on_hand": "Physical on hand",
                    "held_qty": "Held units",
                    "remaining_usable": "Remaining usable",
                    "manual_action_required": "Manual action required",
                    "automatic_stock_change": "Automatic stock change",
                }), hide_index=True, width="stretch",
                alt="Old-component disposition review without automatic stock posting",
            )
        if ecn_plan["old_receipt_review"]:
            st.dataframe(
                pd.DataFrame(ecn_plan["old_receipt_review"]),
                hide_index=True, width="stretch",
                alt="Old-component confirmed receipts needing supplier review",
            )
        st.caption(
            "Use-up does not delay Revision B. Hold keeps physical stock but "
            "removes usable units. Return and scrap remain proposals requiring "
            "separate authorization and posting. WIP is never assumed reworked; "
            "an undefined dispatch rule blocks the plan."
        )
    elif baseline_plan is not None:
        st.metric(
            "Valid Revision A baseline simulated builds",
            baseline_plan["summary"]["total_completed"], border=True,
        )
        st.caption(
            "The ECN-adjusted plan is invalid. No ECN production or stock "
            "results are shown until the conflict or dispatch rule is resolved."
        )

st.divider()
st.caption(
    "FactoryFlow Phase 5C · Fictional planning simulation only · "
    "No actual production, approval, purchasing or inventory posting"
)
