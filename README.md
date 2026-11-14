# FactoryFlow — manufacturing planning simulator (Phase 4D)

FactoryFlow is a local learning project with fictional smart desk lamp and wireless charger data. It combines material planning, line capacity, and dated component supply to estimate what could be built in a selected production window. It records no factory activity, creates no purchase orders, and connects to no ERP or external API.

## What the application calculates

### Material Requirements Planning (MRP)

The Master Production Schedule (MPS) is the requested finished-product quantity on one shared production start date. A one-level Bill of Materials (BOM) multiplies that demand by the component quantity per finished unit. Needs for a shared component are added together.

For each component:

```text
usable opening stock = max(0, on hand - reserved - safety stock)
net shortage = max(0, gross requirement - usable opening stock - confirmed receipts on time)
suggested purchase = shortage rounded up to a full supplier pack
latest theoretical order release = production start - supplier lead days
```

MRP counts a receipt as on time only when its due date is **after** the planning snapshot and **on or before** the production start. Receipts dated on or before the snapshot are assumed already included in on-hand stock. A missing `confirmed` field means confirmed, as in the demo data; `confirmed=False` is excluded from both on-time and late incoming totals. Supplier lead times use calendar days. The suggested purchase is advice, not a receipt or placed order.

The default MPS is 200 lamps and 100 chargers, with a November 14, 2026 snapshot and December 1 production start. These require 1,000 screws: `200 × 4 + 100 × 2`. Of 1,000 on hand, 100 are protected as safety stock, leaving 900 usable. The 100-screw shortage rounds to a 200-screw purchase suggestion because screws come in packs of 200.

### Production capacity, overtime, and downtime

The lamp line can make 80 units per operating weekday; the charger line can make 60. The capacity-only calculation counts weekdays in the inclusive production window and subtracts full downtime days for each line. Overtime adds the entered number of units per operating weekday. A down line has zero capacity, including overtime. Weekends have zero capacity. The **capacity-only finish estimate assumes all materials are available**; it is separate from the integrated result.

### Time-phased material availability

The daily material timeline starts with usable opening stock. Confirmed receipts enter stock on their stated calendar date, before that day's component use. Unconfirmed receipts do not enter stock. The ledger combines requirements from all products for a shared component, limits use to available stock, and carries the nonnegative closing balance to the next day. An unmet requirement remains on its original date; a later receipt cannot retroactively meet it. Weekend receipts enter stock even though the lines do not operate.

The standalone timeline takes **daily component requirements** as input; it does not decide which finished products to build. See `factoryflow/material_timeline.py` and its tests for that interface.

### Integrated production scheduling

The scheduler uses the same usable-stock and confirmed-receipt rules, plus daily line capacity and the BOM. It builds whole finished units only when every required component is available. It deducts components only for those simulated units, carries unfinished demand to the next day in the selected window, and never lets a balance go negative. Shared stock goes first to the alphabetically earlier finished SKU: chargers before lamps. This is a fixed demonstration priority, not an optimized production rule.

With the default December 1–4, 2026 window and no overtime or downtime, the integrated simulation can build **100 chargers and 160 lamps: 260 of 300 units, or 86.67%**. It leaves 40 lamps unfinished. The dashboard shows simulated daily output, component use, and projected usable stock. It does not claim that production occurred or predict when demand left unfinished after the window will be completed.

## Dashboard scenarios

- **Base plan:** Default demand and fictional supply.
- **Demand surge:** Raises demand to 350 lamps and 150 chargers.
- **Longer supplier lead times:** Adds 15 calendar days to MRP lead-time advice. It does **not** move confirmed receipt dates or directly change the integrated production result.
- **Extra opening stock:** Adds fictional on-hand stock at the planning snapshot. It is not a dated receipt arriving during production.

Demand, snapshot and production dates, target completion, overtime, and full downtime dates can also be changed in the sidebar. Reset simulation restores the defaults. All controls affect local calculations only.

## Run and test on Windows

Install Python 3.11 or newer, open PowerShell in this folder, and run:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run app.py
```

If the `py` launcher is unavailable, use `python -m venv .venv`. Open the local URL printed by Streamlit. Stop the server with `Ctrl+C`. Calling the virtual environment's Python directly avoids PowerShell activation-policy issues.

## Project files

| Path | Purpose |
|---|---|
| `app.py` | Streamlit controls and planning views |
| `factoryflow/data.py` | Fictional products, BOM, stock, receipts, and default demand |
| `factoryflow/planning.py` | Single-date MRP and purchase advice |
| `factoryflow/capacity.py` | Capacity-only calculation, overtime, and downtime |
| `factoryflow/material_timeline.py` | Daily component availability ledger |
| `factoryflow/production_schedule.py` | Material-constrained daily finished-unit simulation |
| `tests/` | Automated business-logic and dashboard checks |

## Known limits

- The BOM has one level. There are no subassemblies, alternatives, substitutions, revision dates, or Engineering Change Notices (ECNs).
- MRP uses one common component-need date. Its single-date shortage can differ from a daily schedule that uses receipts later in the production window.
- Receipts are available before production on their due date; time of day, supplier reliability, and quality inspection are not modeled. Pack rounding has no minimum-order rules.
- Capacity uses dedicated lines, weekdays, constant daily rates, and full-day downtime. There are no holidays, shifts, partial outages, setup/changeover time, labor limits, or shared machines.
- Builds assume complete component sets and 100% yield. There is no scrap, rework, partial assembly, work in progress, or order-level allocation.
- Capacity-only finish dates do not account for materials. The integrated simulation ends at the selected target date and makes no completion promise beyond it.
- All numbers are fictional. The app does not record actual production, reserve stock, place orders, or update any external system.

Before using this as more than a learning prototype, validate the rules against real operating policies and data. No ECN or NPI workflow is included in Phase 4D.
