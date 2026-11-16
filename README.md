# FactoryFlow — manufacturing planning simulator (Phase 5C dashboard)

FactoryFlow is a local learning project with fictional smart desk lamp and wireless charger data. It combines material planning, line capacity, and dated component supply to estimate what could be built. Phase 5C adds a separate ECN simulation view to the Streamlit dashboard while preserving the verified no-ECN planning views. The app records no factory activity, creates no purchase orders, and connects to no ERP or external API.

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

## Phase 5B: ECN planning engine

`factoryflow/ecn.py` defines immutable BOM revisions, ECN change lines, status transitions, production lots, and authorized stock holds. `approve_ecn` accepts only a draft with a complete replacement BOM, a valid component master, an approver, a disposition plan, and an effective date later than the approval date. A draft or cancelled ECN never activates its proposed revision. An approved notice can be cancelled only before it takes effect; an effective change needs a new, dated superseding ECN. The full business design and independently calculated examples are in [`docs/ECN_DESIGN.md`](docs/ECN_DESIGN.md).

`factoryflow/ecn_planning.py` exposes `calculate_ecn_plan`. It preserves the existing BOM as Revision A and selects an approved revision by **simulated production date**, not order-creation date. For `ECN-001`, new lamp production before December 3, 2026 uses `LED-100`; new production on or after that date uses Revision B and `LED-101`. Each LED SKU has its own stock balance. Confirmed receipts arrive before same-day use; unconfirmed receipts and purchase suggestions never become available material. Charger-first shared-component allocation and dedicated-line capacity still apply across one continuous daily schedule.

The result includes daily simulated builds, a date/order/revision trace, dated component requirements, stock balances, and pack-rounded purchase advice based on the first shortage date. This advice identifies a risk to the dated plan; it is not a supplier promise or a confirmed delivery. Unfinished work carries forward within the selected window. Released lots pinned to an old revision are held for manual review when the active revision changes. WIP is also held; the engine never assumes it has been reworked or that issued components were returned. An authorized dated hold removes stock from usable supply while retaining it as physical on-hand. Use-up, return, and scrap choices are reported for review and do not automatically post an inventory transaction.

The base fictional data has no `LED-101` inventory master. The ECN simulation view supplies one explicitly, even when opening stock is zero. The main planning views remain no-ECN. The old `calculate_plan`, `calculate_material_timeline`, `calculate_capacity_plan`, and `calculate_production_schedule` APIs remain available unchanged; the no-ECN ECN-engine path is tested against the Phase 4D production result.

## Phase 5C: ECN simulation dashboard

Open **ECN simulation** below the existing planning views. The main MRP, capacity, and integrated production sections retain their no-ECN behavior. ECN controls appear after the original planning controls in the sidebar. Every ECN value is fictional and local; the screen is marked **SIMULATION ONLY**.

- **Factory plan:** Choose a simulated draft, approved, or cancelled ECN; proposed and fictional approval dates; an old-stock disposition proposal; explicit LED-101 opening stock; and dated LED-101 receipts with a confirmed flag. The default LED-101 master has zero opening units, a seven-calendar-day lead time, and a five-unit pack size. You can mark the demo LED-100 receipt unconfirmed, enter an authorized old-stock hold, or inspect new, released Revision A, WIP, and competing-lot states.
- **Scenario explorer:** Select design cases A–H from `docs/ECN_DESIGN.md`. A–G show actual engine-calculated daily builds, revisions, separate LED stock, shortages, and closing balances. H deliberately rejects conflicting approved revisions and publishes no ECN schedule or stock consumption.
- **Impact comparison:** The Revision A baseline and selected ECN run use the same fictional demand, stock, dated receipts, capacity, lot state, and authorized holds. One table groups simulated builds by BOM revision; a separate table shows outstanding demand once per product, without assigning unbuilt units to a revision. The remaining tables show nominal dated component shortages, daily output, production-date/revision trace, LED-100 and LED-101 balances, the shared component, purchase advice, and manual-review exceptions. The ECN stock table shows snapshot reservations, protected safety stock, and authorized holds separately; physical stock can include all three, so its difference from usable stock is not safety stock alone. A completion date appears only when all units are simulated as built inside the selected window. The separate capacity-only estimate still assumes materials are available.

Suggested purchase quantities are nominal dated planning advice. They do not create confirmed receipts or cover every possible backlog carried beyond the selected window; simulated completion dates are not guaranteed. FactoryFlow does not purchase stock automatically. A WIP or pinned-revision conflict stays open for manual review. The UI does not approve an ECN, issue a purchase order, release WIP, or post a return or scrap transaction. Use-up does not postpone Revision B. For a rejected approval, hold, or missing lot dispatch rule, the ECN view shows the engine error and withholds a final adjusted schedule.

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
| `factoryflow/ecn.py` | ECN records, approval/cancellation safeguards, and BOM revision selection |
| `factoryflow/ecn_planning.py` | Revision-aware daily production, stock, and purchase-advice simulation |
| `factoryflow/ecn_scenarios.py` | Fictional input records for design scenarios A-H |
| `docs/ECN_DESIGN.md` | Phase 5A business rules and independent scenario calculations |
| [docs/FACTORYFLOW_DEVELOPMENT_HISTORY.md](docs/FACTORYFLOW_DEVELOPMENT_HISTORY.md) | Documented development history covering Phase 1 through Phase 6B.3 |
| `tests/` | Automated business-logic and dashboard checks, including ECN UI scenarios |

## Known limits

- The BOM has one level. ECN revisions are dated in the Python engine, but there are no subassemblies, automatic alternatives, or component substitutions.
- MRP uses one common component-need date. Its single-date shortage can differ from a daily schedule that uses receipts later in the production window.
- Receipts are available before production on their due date; time of day, supplier reliability, and quality inspection are not modeled. Pack rounding has no minimum-order rules.
- Capacity uses dedicated lines, weekdays, constant daily rates, and full-day downtime. There are no holidays, shifts, partial outages, setup/changeover time, labor limits, or shared machines.
- Builds assume complete component sets and 100% yield. Scrap, rework, and partial assembly are not modeled. The original no-ECN views have no order-level lot controls; the ECN section offers fictional lot-state examples.
- The ECN engine recognizes released lots and WIP for manual review, but cannot resolve WIP, post returns or scrap, release holds, or execute an approved deviation. If two ready lots of one product compete on a day, the engine stops until production control supplies a dispatch decision; it does not invent a lot priority.
- ECN purchase advice uses nominal dated requirements and protects authorized future holds. It is not a second production schedule, so shortage quantities can differ from unfinished units.
- The ECN engine uses the approval status supplied for a simulation. The inventory snapshot date is not a historical approval cutoff; the engine does not reconstruct which approvals were known on that date.
- Capacity-only finish dates do not account for materials. The integrated simulation ends at the selected target date and makes no completion promise beyond it.
- All numbers are fictional. The app does not record actual production, reserve stock, place orders, or update any external system.

Before using this as more than a learning prototype, validate the rules against real operating policies and data. Phase 5C adds a simulation dashboard, but no NPI workflow, shop-floor execution, or external integration.
