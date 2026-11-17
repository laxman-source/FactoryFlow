"""Read-only Streamlit presentation of the existing MPS simulation engines."""

import pandas as pd
import streamlit as st

from factoryflow.mps import calculate_mps
from factoryflow.mps_dashboard_scenarios import (
    SCENARIO_NAMES, SCENARIO_NOTES, scenario_inputs,
)
from factoryflow.mps_feasibility import calculate_mps_feasibility


def _table(rows, alt):
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", alt=alt)


def render_mps_dashboard():
    """Show fictional dated plans without posting stock or choosing allocations."""
    st.divider()
    st.header("MPS simulation")
    st.caption(
        "SIMULATION ONLY · Proposed production and projected finished goods are "
        "provisional. Actual production and physical finished-goods receipts are not tracked."
    )
    with st.sidebar:
        st.header("MPS controls")
        selected = st.selectbox(
            "Fictional MPS scenario", list(SCENARIO_NAMES),
            format_func=lambda code: SCENARIO_NAMES[code],
            key="mps_scenario",
        )
    st.info(SCENARIO_NOTES[selected])
    inputs = scenario_inputs(selected)

    try:
        mps = calculate_mps(
            inputs["finished_skus"], inputs["fg_opening"],
            inputs["firm_orders"], inputs["forecasts"], inputs["proposals"],
            inputs["as_of"], inputs["planning_end"],
        )
    except ValueError as exc:
        st.error(f"MPS input review required: {exc}")
        return

    st.subheader("Dated demand")
    _table([
        {
            "Planning date": row["planning_date"].isoformat(),
            "Finished SKU": row["finished_sku"],
            "Firm customer orders": row["firm_orders"],
            "Forecast": row["forecast"],
            "Forecast consumed": row["forecast_consumed"],
            "Effective demand": row["effective_demand"],
        }
        for row in mps
    ], "Daily orders, forecast consumption, and effective demand once per finished SKU")
    st.caption(
        "Provisional same-date consumption: effective demand is orders plus "
        "forecast less the smaller of those two quantities for the same SKU and date."
    )

    st.subheader("Proposed production plan")
    _table([
        {
            "Planning date": row["planning_date"].isoformat(),
            "Finished SKU": row["finished_sku"],
            "Production start": (
                row["production_start"].isoformat()
                if row["production_start"] else "—"
            ),
            "Planned completion": (
                row["planning_date"].isoformat()
                if row["production_start"] else "—"
            ),
            "Proposed MPS units": row["proposed_mps_completion"],
            "Provisional projected FG balance": row["projected_fg_balance"],
            "Outstanding unmet demand": row["unmet_demand"],
        }
        for row in mps
    ], "Proposed dated completions and provisional finished-goods balances")
    st.caption(
        "Projected FG includes proposed completions. A negative balance is "
        "backlog in this planning projection, not negative physical stock. "
        "No proposed completion is a confirmed finished-goods receipt."
    )

    try:
        feasible = calculate_mps_feasibility(
            inputs["proposals"], inputs["base_bom"],
            inputs["component_inventory"], inputs["receipts"],
            inputs["as_of"], inputs["planning_end"],
            proposed_revisions=inputs["proposed_revisions"],
            ecns=inputs["ecns"], lots=inputs["lots"], lines=inputs["lines"],
        )
    except ValueError as exc:
        st.subheader("Planning exceptions")
        st.error(f"ECN, revision, or WIP review required: {exc}")
        st.caption(
            "Dated material and build feasibility results are withheld until "
            "the existing planning rules can resolve this scenario."
        )
        return

    nominal = feasible["nominal_material_plan"]
    st.subheader("Dated material requirements")
    _table([
        {
            "Requirement date": row["requirement_date"].isoformat(),
            "Finished SKU": row["finished_sku"],
            "BOM revision": row["bom_revision"],
            "Component": row["component_sku"],
            "Gross component requirement": row["gross_required"],
        }
        for row in nominal["material_requirements"]
    ], "Revision-aware gross components required by proposed production")
    _table([
        {
            "Requirement date": row["date"].isoformat(),
            "Component": row["component_sku"],
            "Gross component requirement": row["gross_required"],
            "Confirmed receipts": row["confirmed_receipts"],
            "Nominal covered": row["nominal_covered"],
            "Nominal shortage": row["material_shortage"],
            "Outstanding requirement": row["outstanding_requirement"],
        }
        for row in nominal["component_ledger"]
        if row["gross_required"] or row["confirmed_receipts"]
        or row["material_shortage"]
    ], "Shared component ledger with confirmed receipts and nominal shortages")
    st.caption(
        "Nominal coverage counts components against proposed requirements; "
        "it does not prove whole-unit builds or authorize material issue."
    )

    st.subheader("Production feasibility")
    summary = feasible["summary"]
    columns = st.columns(4)
    for column, label, key in zip(
        columns,
        ("Proposed MPS units", "Simulated builds (resolved only)",
         "Known unbuilt units", "Unresolved units"),
        ("total_proposed_mps_units", "total_simulated_buildable_units",
         "total_known_unbuilt_units", "total_unresolved_units"),
    ):
        column.metric(label, summary[key], border=True)
    _table([
        {
            "Production start": row["production_start"].isoformat(),
            "Planned completion": row["completion_date"].isoformat(),
            "Finished SKU": row["finished_sku"],
            "BOM revision": row["bom_revision"],
            "Proposed MPS units": row["proposed_mps_units"],
            "Simulated buildable units": (
                row["simulated_buildable_units"]
                if row["simulated_buildable_units"] is not None
                else "Unresolved"
            ),
            "Known unbuilt units": row["known_unbuilt_units"],
            "Unresolved units": row["unresolved_units"],
            "Daily available capacity": row["available_capacity"],
            "Simulated capacity consumed": row["simulated_capacity_used"],
            "Status": row["status"],
        }
        for row in feasible["feasibility_rows"]
    ], "Proposed units compared with simulated whole-unit material and capacity feasibility")
    st.caption(
        "Simulated builds use complete component sets and daily line capacity. "
        "They are neither actual production nor physical finished-goods stock. "
        "Unresolved units are excluded from known unbuilt units."
    )

    st.subheader("Simulated component use")
    conditional = [
        row for row in feasible["simulated_consumption_ledger"]
        if row["balance_status"] != "resolved"
    ]
    _table([
        {
            "Date": row["date"].isoformat(),
            "Component": row["component_sku"],
            "Opening usable": (
                row["opening_usable"] if row["balance_status"] == "resolved"
                else "Conditional"
            ),
            "Confirmed receipts": row["confirmed_receipts"],
            "Simulated use": row["simulated_use"],
            "Simulated closing usable": (
                row["simulated_closing_usable"]
                if row["balance_status"] == "resolved" else "Conditional"
            ),
            "Balance status": row["balance_status"],
        }
        for row in feasible["simulated_consumption_ledger"]
        if row["simulated_use"] or row["confirmed_receipts"]
        or row["balance_status"] != "resolved"
    ], "Whole-unit component consumption with conditional balances withheld")
    st.caption(
        "This simulated-consumption ledger is separate from the nominal "
        "requirements ledger. Conditional balances are not confirmed available inventory."
    )

    st.subheader("Planning exceptions")
    issues = False
    if nominal["shortages"]:
        issues = True
        for row in nominal["shortages"]:
            st.warning(
                f"Nominal material shortage: {row['component_sku']} on "
                f"{row['requirement_date'].isoformat()} needs "
                f"{row['material_shortage']} more units for the proposed plan."
            )
    for row in feasible["feasibility_rows"]:
        if row["capacity_unbuilt_units"]:
            issues = True
            st.warning(
                f"Daily capacity restriction: {row['finished_sku']} on "
                f"{row['production_start'].isoformat()} has "
                f"{row['available_capacity']} capacity units; "
                f"{row['capacity_unbuilt_units']} proposed units exceed that limit."
            )
        if row["material_unbuilt_units"]:
            issues = True
            st.warning(
                f"Complete-set material restriction: {row['finished_sku']} on "
                f"{row['production_start'].isoformat()} leaves "
                f"{row['material_unbuilt_units']} proposed units unbuilt."
            )
    for conflict in feasible["shared_component_conflicts"]:
        issues = True
        claims = ", ".join(
            f"{sku}: {qty}" for sku, qty
            in sorted(conflict["competing_requirements"].items())
        )
        st.error(
            f"Shared-component allocation unresolved: "
            f"{conflict['component_sku']} on {conflict['date'].isoformat()} "
            f"has {conflict['available_quantity']} available; competing "
            f"SKUs and component claims are {claims}. A planner must choose allocation."
        )
    if conditional:
        issues = True
        affected = sorted({row["component_sku"] for row in conditional})
        st.warning(
            "Conditional downstream component balances: "
            + ", ".join(affected)
            + ". The unresolved allocation prevents a confirmed usable balance."
        )
    if selected == "revision":
        st.info(
            "Approved ECN MPS-ECN-01: Revision B applies to lamp production "
            "starts from 2026-12-02. WIP disposition is not inferred."
        )
    if not issues:
        st.info("No material, capacity, allocation, or revision exception in this scenario.")
