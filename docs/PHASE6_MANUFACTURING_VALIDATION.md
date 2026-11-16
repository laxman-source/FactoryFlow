# Phase 6A — Manufacturing reality audit and validation design

**Audit baseline:** `feature/phase6a-manufacturing-validation` at `bcf6c903fa5e71af9697b49fd22f5fd37e494634`; 189 automated tests passed. All examples below use fictional parts, orders, stock and dates. This is a design audit, not shop-floor or industry validation.

## Executive summary

FactoryFlow can simulate a useful, bounded planning problem: one-level component needs, protected stock, confirmed dated receipts, dedicated weekday line capacity, whole-unit material-constrained builds, and approved date-effective BOM revisions. Its one shared stock ledger avoids consuming a component twice. The ECN path reports old-stock and WIP exceptions but does not execute their resolution.

It cannot yet model a multi-level assembly, a governed dispatch choice between ready orders for the same product, supplier minimum order quantities (MOQ), partial WIP and issued material, or actual production and inventory transactions. ECN purchase advice uses a capacity-first **nominal** requirement stream; a material-delayed unit that crosses an effective date can need a different component from the one in that advice. This is a material risk if anyone treats the simulator as an executable EMS plan. The Streamlit view labels its output as simulation only (`app.py:557-559`, `app.py:1060-1062`). Passing tests establish conformance to the implemented rules, not suitability for a real factory.

## Assessment method and source evidence

**SUPPORTED** means the stated, limited behavior is implemented and tested. **PARTIALLY SUPPORTED** means an EMS process has a simplified representation or a fail-closed exception. **NOT SUPPORTED** means the needed model or transaction does not exist in the inspected code. **NOT VERIFIED** means this audit lacks sufficient evidence; it must not be inferred from a passing neighboring test. These labels describe the present application, not a vendor or factory policy.

The inspected implementation is `factoryflow/data.py`, `planning.py`, `material_timeline.py`, `capacity.py`, `production_schedule.py`, `ecn.py`, `ecn_planning.py`, `ecn_scenarios.py`, and `app.py`. The 189-test suite includes the corresponding `tests/test_*.py` files and Streamlit `AppTest` checks. The code locations below are evidence for each classification; a negative classification reflects the absence of that required record or operation in the listed module's input and result contract.

### A. Material Requirements Planning

| Capability | Assessment | Actual behavior and source evidence |
|---|---|---|
| One-level BOM | SUPPORTED | MRP multiplies each finished-product demand by direct component usage and sums shared needs (`planning.py:36-44`); the demonstration BOM is explicitly one level (`data.py:17-27`). |
| Multi-level BOM | NOT SUPPORTED | BOM lines contain `finished_sku`, `component_sku`, and `qty_per_unit`; neither the MRP loop nor the daily scheduler recursively explodes a component that is itself an assembly (`data.py:18-27`, `planning.py:36-44`, `production_schedule.py:58-68`). |
| Component availability | SUPPORTED | The timeline carries a separate daily usable balance by SKU and adds confirmed receipts before same-day use (`material_timeline.py:61-108`). |
| Material shortages | SUPPORTED | One-date MRP calculates gross less usable less on-time confirmed receipts; the ECN requirement ledger reports dated unmet nominal need (`planning.py:84-107`, `ecn_planning.py:122-161`). These are different scopes from the actual-build backlog. |
| Shared-component consumption | SUPPORTED | The integrated schedulers use one balance per component across products and deduct parts only for whole simulated builds (`production_schedule.py:90-127`, `ecn_planning.py:278-355`). |
| Safety stock and reserved inventory | SUPPORTED | Opening usable is `max(0, on_hand - reserved - safety_stock)`; an ECN hold is a separate dated deduction (`material_timeline.py:86-101`, `ecn_planning.py:288-300`). |
| Confirmed versus unconfirmed receipts | SUPPORTED | Only confirmed receipts after the snapshot and within the horizon enter the timeline (`material_timeline.py:61-72`); the schedulers consume that same supply stream (`production_schedule.py:74-82`, `ecn_planning.py:241-251`). |

### B. Production planning

| Capability | Assessment | Actual behavior and source evidence |
|---|---|---|
| Production capacity | PARTIALLY SUPPORTED | Dedicated product lines have fixed daily rates and weekday calendars (`capacity.py:11-14`, `capacity.py:112-151`). There is no shared machine, shift, labor, setup, holiday, or yield model in these inputs. Capacity-only completion excludes materials (`capacity.py:51-68`). |
| Downtime | PARTIALLY SUPPORTED | A list of full calendar dates removes that line's weekday capacity; partial-day outages are not an input (`capacity.py:86-110`, `capacity.py:124-130`). |
| Overtime | PARTIALLY SUPPORTED | An integer adds units on each operating weekday, but no shift duration, approval, labor, or fatigue constraint is represented (`capacity.py:74-84`, `capacity.py:119-130`). |
| Material-constrained scheduling | SUPPORTED | Whole daily builds are limited by demand, line capacity, and every direct BOM component; unfinished units carry within the selected window (`production_schedule.py:101-127`, `ecn_planning.py:303-355`). No completion is promised after the window. |
| Competing production orders | PARTIALLY SUPPORTED | ECN `ProductionLot` records have IDs, quantities and states, but two ready lots of one product on one day cause an error until dispatch is decided (`ecn.py:162-181`, `ecn_planning.py:19-42`, `ecn_planning.py:73-82`). The legacy scheduler has product demand only (`production_schedule.py:84-90`). |
| Production priority rules | PARTIALLY SUPPORTED | Products run in ascending SKU order, giving chargers first claim on shared stock; there is no configurable customer/order priority (`production_schedule.py:90-127`, `ecn_planning.py:263-267`, `ecn_planning.py:303-323`). |

### C. Engineering change management

| Capability | Assessment | Actual behavior and source evidence |
|---|---|---|
| Draft, approved and cancelled ECNs | SUPPORTED | Immutable `ECN` records validate states and dates; `approve_ecn` and `cancel_ecn` enforce the permitted transitions (`ecn.py:76-141`, `ecn.py:284-314`). This is simulated status input, not an approval transaction. |
| Effective-date revision changes | SUPPORTED | Approved revisions resolve by simulated production date; invalid overlapping/disconnected calendars fail (`ecn.py:257-281`, `ecn.py:316-325`, `ecn_planning.py:264-270`). |
| Revision-specific inventory | PARTIALLY SUPPORTED | `LED-100` and `LED-101` are separate component SKU balances (`ecn_planning.py:278-280`, `ecn_planning.py:399-409`). There is no finished-goods inventory by BOM revision or genealogy record (`ecn_planning.py:474-495`). |
| Existing WIP | PARTIALLY SUPPORTED | A lot can be marked `wip` with a quantity and pinned revision, and is held for review. Stage of completion, issued components, rework and release are not recorded (`ecn.py:162-181`, `ecn_planning.py:329-360`). |
| Pinned-revision conflicts | SUPPORTED | A released lot whose pinned revision differs from the active date's revision is blocked for manual review (`ecn_planning.py:332-338`, `ecn_planning.py:355-370`). |
| Old-stock disposition | PARTIALLY SUPPORTED | An authorized `StockHold` removes usable supply while retaining physical stock; use-up, return and scrap are proposals/review rows, with `automatic_stock_change=False` (`ecn.py:144-160`, `ecn_planning.py:440-470`). |
| Revision traceability | SUPPORTED | Simulated date, product, order, active/built revision, ECN reference, units and component use are returned in `revision_trace` (`ecn_planning.py:356-367`, `ecn_planning.py:475-480`). This is a plan trace, not a serial/lot actual-build record. |

### D. Supplier and purchasing planning

| Capability | Assessment | Actual behavior and source evidence |
|---|---|---|
| Supplier lead times | PARTIALLY SUPPORTED | Integer calendar days determine a theoretical latest release date; there is no supplier calendar, transit, confirmation or variability (`planning.py:87-107`, `ecn_planning.py:164-190`). |
| Partial deliveries | SUPPORTED | Multiple confirmed receipt rows for a SKU/date accumulate; each dated partial quantity becomes available only when due (`material_timeline.py:61-72`, `tests/test_production_schedule.py:120-157`). Receipt reliability and inspection are outside the model. |
| Late deliveries | SUPPORTED | A later confirmed receipt cannot fill an earlier day's shortage or add earlier output (`material_timeline.py:93-108`, `tests/test_ecn.py:186-194`). No probabilistic delay prediction exists. |
| Minimum order quantities | NOT SUPPORTED | The inventory master has `pack_size` but no MOQ field; suggestions only round shortage to pack multiples (`data.py:29-38`, `planning.py:87`, `ecn_planning.py:164-190`). |
| Purchasing recommendations | PARTIALLY SUPPORTED | MRP and ECN advice calculate shortage, pack-rounded quantity, and theoretical release date, but create no purchase order or confirmed receipt (`planning.py:84-107`, `ecn_planning.py:164-190`). |
| Material-constrained backlog | PARTIALLY SUPPORTED | The schedule reports unfinished units, while ECN purchase advice comes from capacity-first nominal requirements rather than the resulting carryover (`ecn_planning.py:85-120`, `ecn_planning.py:269-276`, `ecn_planning.py:411-438`). It is not a backlog procurement plan. |

### E. Production execution

| Capability | Assessment | Actual behavior and source evidence |
|---|---|---|
| Planned versus actual production | NOT SUPPORTED | `daily_schedule` and `revision_trace` contain simulated builds only; no actual production input or reconciliation is accepted (`production_schedule.py:15-29`, `ecn_planning.py:193-209`, `app.py:557-559`). |
| Work-in-progress quantities | PARTIALLY SUPPORTED | A WIP lot has an order quantity and a manual-review flag, but no completed/partially assembled/issued-part quantities (`ecn.py:162-181`, `ecn_planning.py:329-360`). |
| Production completion records | NOT SUPPORTED | Completion is an in-memory plan summary, not a posted build record or serial/lot event (`ecn_planning.py:411-438`, `ecn_planning.py:474-495`). |
| Material consumption transactions | NOT SUPPORTED | `components_consumed` and stock ledger values are simulated deductions returned from the calculation; there is no issue or backflush posting (`ecn_planning.py:343-367`, `ecn_planning.py:399-409`). |
| Inventory adjustments | NOT SUPPORTED | Inputs are snapshots plus confirmed receipts and authorized holds. The engine explicitly reports no automatic return/scrap stock change (`ecn_planning.py:440-470`); no adjustment transaction API exists in the inspected modules. |

## Realistic fictional EMS scenario matrix

**Common oracle rules:** Unless changed below, dates are in 2026, quantities are whole units, all other direct components are plentiful, each named line is dedicated and operates on weekdays, confirmed receipts arrive before that day's build, and no production or purchase is actually posted. M08 explicitly assumes reserved, safety and held quantities are distinct physical units; a real stock-status policy still needs expert review. Hand calculations below precede comparison with the engine. A missing real-world policy is marked **expert review**, not filled with an invented output. Risk severity concerns possible operational misuse, not this fictional training run.

### M01 — Multi-level power module

- **Problem/input:** Five fictional lamps each need one `SUB-PWR`; each `SUB-PWR` needs two `CAP-10`. No subassembly stock or confirmed receipts are specified.
- **Expected behavior and hand result:** Structural gross need is `5 × 1 = 5 SUB-PWR` and, **if all five are made**, `5 × 2 = 10 CAP-10`. A net capacitor release date or feasible finished build count cannot be determined without make/buy, subassembly stock, routings, lead times, and yield decisions.
- **Current capability/limit:** **NOT SUPPORTED**. Direct BOM traversal (`planning.py:36-44`) cannot explode `SUB-PWR`; treating it as an ordinary purchased component would hide `CAP-10`.
- **Consequence/risk:** **High** — missing lower-level parts could make an apparently covered plan impossible.
- **Test/improvement:** Add a fictional two-level fixture and an expected explosion oracle only after manufacturing experts define make/buy, stock netting and timing; reject unsupported multi-level input meanwhile.

### M02 — ECN takes effect during production

- **Problem/input:** Eight lamps, two per weekday on Dec 1–4; Revision A uses one `LED-100`, Revision B one `LED-101`; approved Dec 2, effective Dec 3; old stock 8, new stock 4.
- **Expected behavior and hand result:** Dec 1–2 build `2 + 2 = 4` A units using four old boards; Dec 3–4 build `2 + 2 = 4` B units using four new boards. Eight complete; old closes at 4, new at 0. Every built date has exactly one revision.
- **Current capability/limit:** **SUPPORTED** for new unstarted lots (`ecn.py:316-325`, `ecn_planning.py:264-270`, `ecn_planning.py:303-367`); actual shop-floor trace is absent.
- **Consequence/risk:** **High** if a real released/WIP lot were silently treated as new.
- **Test/improvement:** Retain scenario C's date, revision, use and balance assertions (`tests/test_ecn.py:91-132`); expert review defines the released-lot split procedure.

### M03 — Several partial confirmed receipts

- **Problem/input:** One lamp needs one fictional board. Demand 5; line capacity 2 on Dec 1–3; opening usable 0; confirmed board receipts 1, 2 and 2 on those dates; no other limit.
- **Expected behavior and hand result:** Daily builds are `min(2,1)=1`, `min(2,2)=2`, and `min(2,2)=2`; total 5, remaining 0, closing board stock 0. An otherwise identical unconfirmed receipt must add zero.
- **Current capability/limit:** **SUPPORTED** through dated receipt accumulation and daily builds (`material_timeline.py:61-72`, `production_schedule.py:93-127`). There is no supplier confirmation workflow.
- **Consequence/risk:** **Medium** if an expected but unconfirmed shipment is mistaken for supply.
- **Test/improvement:** Check each receipt date, build and stock conservation; include an unconfirmed partial. Existing shared-part regression exercises three partial receipts (`tests/test_production_schedule.py:120-157`).

### M04 — Delivery arrives after the first need

- **Problem/input:** Four lamps need one board each; capacity two per day Dec 1–2; opening board stock 0; four confirmed boards arrive Dec 2.
- **Expected behavior and hand result:** Dec 1 builds 0. Dec 2 builds 2, leaving two units unfinished and two boards in stock. Four boards arriving eventually do not restore Dec 1 capacity.
- **Current capability/limit:** **SUPPORTED** for the finite window (`material_timeline.py:93-108`, `production_schedule.py:93-127`); no later completion is promised.
- **Consequence/risk:** **Medium** — whole-window supply totals can mask a dated miss.
- **Test/improvement:** Assert zero early build, two late builds, two leftover boards, and two unfinished units; retain the ECN late-receipt case F (`tests/test_ecn.py:186-194`).

### M05 — Two products compete for screws

- **Problem/input:** Two chargers need two screws each; two lamps need four each. Both lines can build two on Dec 1; all other parts cover demand; only six usable screws exist.
- **Expected behavior and hand result:** Fixed charger-first priority builds two chargers using four screws. Two screws remain, too few for a lamp: zero lamps, two unfinished, closing screws 2. Total use 4, not 12 or twice the available stock.
- **Current capability/limit:** **PARTIALLY SUPPORTED**: shared stock and the fixed SKU priority work (`production_schedule.py:90-127`, `tests/test_ecn.py:344-368`), but customer priority is not configurable.
- **Consequence/risk:** **High** if the alphabetic rule disagrees with contractual priority.
- **Test/improvement:** Assert product order, component use once, nonnegative closing stock; ask production control to approve any future priority policy.

### M06 — Old-revision WIP reaches the ECN boundary

- **Problem/input:** A four-unit lamp lot is marked WIP and pinned to A; B is approved for Dec 3; Dec 3–4 capacity and new boards could otherwise cover four units.
- **Expected behavior and hand result:** Zero additional simulated builds from that WIP lot; four units require manual review and no new-board consumption is inferred. Actual work completed or parts already issued are **unknown**.
- **Current capability/limit:** **PARTIALLY SUPPORTED**: WIP is blocked (`ecn_planning.py:329-360`), but issued material, partial completion, rework and release decisions are unmodeled.
- **Consequence/risk:** **High** — assuming the WIP is reworked could double issue parts or misstate revision trace.
- **Test/improvement:** Assert no build/consumption and four review units; expert review must define WIP stage, issued-part and disposition records before execution use.

### M07 — Downtime overrides overtime

- **Problem/input:** Six lamps, normal capacity 2/day plus one overtime unit on Dec 1–2; Dec 1 has full lamp-line downtime; all materials cover six.
- **Expected behavior and hand result:** Dec 1 capacity/builds 0; Dec 2 capacity/builds `2 + 1 = 3`; three unfinished by Dec 2. The capacity-only estimate must not claim a material-constrained completion date.
- **Current capability/limit:** **PARTIALLY SUPPORTED**: full-day downtime and integer overtime work (`capacity.py:74-130`), not shift-level loss or labor availability.
- **Consequence/risk:** **Medium** — real partial outages could make the estimated capacity inaccurate.
- **Test/improvement:** Assert both day capacities, builds and balance; retain overtime/downtime regression (`tests/test_capacity_overtime_downtime.py:65-90`).

### M08 — Safety, reservation and ECN hold coexist

- **Problem/input:** A component has physical stock 10, reserved 2, safety stock 2, and an authorized hold of 2 effective Dec 1. Five units each need one; line capacity is five; no receipts.
- **Expected behavior and hand result:** Opening usable `10 − 2 − 2 = 6`; after hold, four usable. Build four, leave one unfinished; closing usable 0, physical `10 − 4 = 6`, held 2. The physical six also includes the two reserved and two protected safety units; the gap is not all safety stock.
- **Current capability/limit:** **SUPPORTED** for snapshot restrictions and dated holds (`material_timeline.py:86-101`, `ecn_planning.py:288-300`, `ecn_planning.py:399-409`); no stock-release transaction exists.
- **Consequence/risk:** **High** if protected or held parts are offered to production.
- **Test/improvement:** Assert each status separately, four component uses, no negative usable balance and the six-unit physical closing; include an unauthorized/oversized hold rejection.

### M09 — Two ready lots need a dispatch rule

- **Problem/input:** Two new lamp orders of two units each are ready Dec 1. One line can make three; parts could cover four. No order priority is supplied.
- **Expected behavior and hand result:** Aggregate possible capacity is three, but **which lot receives those three is undefined**. The engine must publish no final allocation or consumption until a human supplies a rule.
- **Current capability/limit:** **PARTIALLY SUPPORTED**: contention fails closed (`ecn_planning.py:73-82`, `tests/test_ecn.py:299-305`); there is no configurable dispatch sequence.
- **Consequence/risk:** **High** — an arbitrary order choice could violate a customer commitment.
- **Test/improvement:** Assert the explicit dispatch error and absence of a final ECN schedule; manufacturing experts define the tie-break, release and override controls.

### M10 — Lead time, packs and an unknown MOQ

- **Problem/input:** One component per unit, demand 11 due Dec 10; usable stock 3, no receipts, pack size 5, lead time 7 calendar days, snapshot Dec 1. A supplier states an MOQ of 12, but FactoryFlow has no MOQ field.
- **Expected behavior and hand result:** Within implemented pack rules, shortage is `11 − 3 = 8`, suggestion `ceil(8/5) × 5 = 10`, and theoretical release is Dec 3. **A valid MOQ-constrained order is unresolved**: whether MOQ and pack multiples combine to 15, or use another policy, requires buyer confirmation. Do not present 10 as an approved supplier order.
- **Current capability/limit:** **PARTIALLY SUPPORTED** for lead/pack advice; MOQ is **NOT SUPPORTED** (`planning.py:84-107`, `ecn_planning.py:164-190`).
- **Consequence/risk:** **High** if 10 is submitted to a supplier that will reject it.
- **Test/improvement:** Check shortage, pack advice and release date now; expert review defines MOQ, order multiples, supplier calendar and exceptions before a new rule is coded.

### M11 — Excess old stock after an ECN

- **Problem/input:** Scenario E: 12 old boards, four A lamps before Dec 3, four B lamps after, four new boards, and an authorized hold of eight old boards on Dec 3.
- **Expected behavior and hand result:** Old use 4 leaves 8 physically; all 8 are held, 0 old usable. New use 4 leaves 0. Eight lamps complete; no return or scrap transaction occurs.
- **Current capability/limit:** **PARTIALLY SUPPORTED**: hold and review outputs work (`ecn_planning.py:288-300`, `ecn_planning.py:440-470`); return, scrap and supplier disposition are not posted.
- **Consequence/risk:** **Medium** — inventory may remain stranded unless the organization performs a separate authorized disposition.
- **Test/improvement:** Retain design scenario E's balances (`tests/test_ecn.py:155-163`); expert review defines approvals and accounting for return/scrap.

### M12 — A simulated plan is not an actual build record

- **Problem/input:** Four lamps, capacity two on Dec 1–2, and complete parts for four. No shop-floor actuals are supplied.
- **Expected behavior and hand result:** The planner may simulate two plus two = four buildable units. **Actual completed units, actual consumption, yield and variance are unknown**; no valid actual-versus-plan percentage can be calculated.
- **Current capability/limit:** **NOT SUPPORTED** for execution (`production_schedule.py:15-29`, `ecn_planning.py:193-209`, `app.py:557-559`).
- **Consequence/risk:** **High** if simulated output is treated as shipped or posted inventory.
- **Test/improvement:** Assert simulation labels and absence of posting actions; expert review defines MES/ERP event, lot, quantity and reconciliation contracts before any execution integration.

### M13 — Material-delayed backlog crosses a revision date

- **Problem/input:** Default fictional 200-lamp/100-charger factory plan, Dec 1–4; ECN B effective Dec 3; no `LED-101` opening stock or confirmed new-board receipt. The lamp adapter has 150 on hand and 20 due Dec 3 (`data.py:29-48`).
- **Expected behavior and hand result:** Dec 1–2 simulate 150 A lamps and 100 chargers, leaving 50 lamps. No B lamp can build without `LED-101`: **250 total built, 50 unfinished**. Capacity-first nominal needs allocate 160 A and 40 B lamps, so the nominal `LED-101` shortage is 40. Ten intended A lamps slipped past the effect; if all 50 unfinished lamps are later built as new B production, their structural new-board need is 50, before any future receipts or new schedule are known. Do not call the 40-unit advice full backlog coverage.
- **Current capability/limit:** **PARTIALLY SUPPORTED**: actual-build backlog is tracked, but nominal purchasing does not re-explode delayed units (`ecn_planning.py:85-120`, `ecn_planning.py:269-276`, `ecn_planning.py:411-438`; dashboard scope label `app.py:983-987`).
- **Consequence/risk:** **High** — purchasing can underprepare for a revision-crossing carryover if it treats nominal advice as a total recovery order.
- **Test/improvement:** Preserve the 250/50 engine result and 40 nominal advice as distinct assertions; expert review chooses whether future scope needs a backlog replan with dated revision rules, not an automatic purchase transaction.

## Validation methodology

1. **Freeze a fictional case record:** Input demand/orders, complete direct BOM and revisions, snapshot stock by status, confirmed/unconfirmed receipts, line calendar and capacity, ECN approvals, holds, and a fixed horizon. Record assumptions and unknowns before running FactoryFlow.
2. **Create an independent oracle:** A planner calculates gross component need from BOM multiplication; opening usable from on-hand minus reserved/safety; dated receipts; whole-unit capacity; product priority; per-date revision; component use; closing usable/physical/held; and unfinished demand. Show arithmetic in the case record. Do not derive expected numbers by copying engine or dashboard output. Where rules are missing, expect an explicit stop or mark the result **expert review**.
3. **Automated exact checks:** For supported cases compare integer units, first shortage dates, revision boundaries, hold dates, status transitions, purchase-pack rounding and trace rows exactly. Reconcile every component/date as `opening usable + confirmed receipts − authorized holds − simulated use = closing usable`; compare physical closing separately and require nonnegative balances. Verify `total demand = simulated builds + unfinished demand` without counting a product backlog per revision.
4. **Feasibility checks:** For each operating day require builds no greater than remaining demand, available line capacity, or the smallest usable component-set limit. No parts are consumed for an unbuilt unit. Weekend/full-day downtime capacity is zero; a receipt after a missed day does not repair that day's output.
5. **Exception and human-review checks:** Invalid BOMs, unapproved/overlapping ECNs, unconfirmed receipts, excessive holds, WIP and ambiguous lot dispatch must fail closed or be visibly flagged. A human must decide WIP rework, old-stock disposition, lot dispatch and supplier exceptions; tests must not silently choose them.
6. **Decision explanation:** For each simulated build, retain date, product, order/lot, active and built revision, ECN reference, component use and reason for any block. Show capacity-only dates separately from finite material-constrained results. Verify that purchase advice is labeled nominal and creates no receipt.
7. **Planning-task timing:** In a future observed trial, give planners the same fictional tasks (find the first material-short day, identify a revision-crossing lot, reconcile shared stock, and explain a purchase suggestion). Record task start/end, correctness, corrections needed and explanation quality. Establish an acceptable time target with practitioners **before** using time as a pass/fail gate; this audit measured no user task times.
8. **External validation gate:** Automated tests validate the coded model only. Real EMS suitability needs authorized manufacturing, engineering, quality and buying experts to review rules and scenarios, plus approved data-handling arrangements for any later real-data exercise. No actual practitioner sign-off or confidential operational dataset was used in Phase 6A.

## Risk register and prioritized engineering gaps

| Priority | Risk and evidence | Required decision or control | Phase 6B direction |
|---|---|---|---|
| P0 / High | Multi-level requirements are invisible to direct BOM traversal (`planning.py:36-44`). | Define make/buy, subassembly stock, lead-time offset, yield and revision inheritance. | Independent multi-level oracle and fail-closed input contract before explosion code. |
| P0 / High | WIP and actual production/issued components cannot be reconciled (`ecn.py:162-181`, `ecn_planning.py:329-360`). | Production and quality define WIP stages, issued stock, rework/deviation and actual event ownership. | Design execution boundary; do not post stock from a planning simulation. |
| P0 / High | Same-product ready lots have no dispatch rule (`ecn_planning.py:73-82`). | Production control approves priority, tie-break and override audit trail. | Add tests and a rule design before implementing dispatch. |
| P0 / High | Nominal ECN advice can omit material needed by revision-crossing carryover (`ecn_planning.py:85-120`, `ecn_planning.py:269-276`). | Agree whether and how to replan backlog at a future date; separate it from original nominal advice. | Prototype an independent backlog oracle and explicit labels before changing purchasing logic. |
| P1 / High | Pack-rounded advice ignores supplier MOQ (`planning.py:87`, `ecn_planning.py:164-190`). | Buying defines MOQ versus pack multiples, partial-pack exceptions and supplier calendars. | Add validated supplier policy fields and negative fixtures after sign-off. |
| P1 / Medium | Constant weekday capacity and full-day downtime omit shifts, shared machines, changeover, labor and yield (`capacity.py:11-14`, `capacity.py:51-151`). | Operations defines the smallest useful capacity calendar and bottleneck model. | Add staged capacity validation cases rather than a wholesale rewrite. |
| P1 / Medium | Receipts are assumed usable at the due date; quality inspection and supplier reliability are absent (`material_timeline.py:61-72`). | Supply/quality define receipt confirmation and release-to-use status. | Distinguish arrival, inspection and usable release in a future design. |
| P2 / Medium | Old-stock return/scrap are advice only (`ecn_planning.py:440-470`). | Quality/finance define authorization and physical/accounting postings. | Keep disposition outside the planner until an execution owner exists. |

## Required fictional test data for Phase 6B

- A two-level assembly with make/buy decision, subassembly stock, direct and lower-level revision dates, and explicit expected component explosion.
- Two products sharing a scarce component, plus two orders for one product with an explicitly unresolved dispatch priority.
- Separate physical, reserved, safety and authorized-held quantities; multiple confirmed partial receipts, an unconfirmed receipt and one receipt after the first need.
- Draft, approved, cancelled and conflicting ECNs; a new lot, released pinned lot and WIP lot with clearly stated issued-part status.
- Supplier lead days, pack size and a proposed MOQ, with the expert-approved precedence rule recorded before expected order quantity is set.
- A production-window boundary that leaves material-constrained backlog crossing an ECN effective date; separate nominal purchase advice from any future recovery-plan oracle.
- If execution is later considered, fictional actual-build, scrap, material-issue and adjustment events with an independently reconciled starting and ending ledger. These records do **not** exist in Phase 6A.

## Questions for manufacturing expert review

1. For a subassembly, when is demand exploded into child parts, and how do existing subassembly stock, make/buy choice, yield, lead time and revision affect the net need?
2. Which authority chooses among ready orders competing for the same line or scarce component? What is the tie-break and override audit trail?
3. How are partial WIP, issued parts and an old pinned revision handled when an ECN becomes effective? Who approves a split, rework or deviation?
4. Does an ECN become effective by calendar day, shift, work order release, serial number, or another controlled event? What happens to output already started?
5. How do supplier MOQ, pack multiples, minimum value, calendar, inspection time and partial deliveries combine? Does a confirmed due date imply usable stock?
6. Should nominal ECN advice remain a first-pass risk signal, or should planners request a separate carryover replan after material constraints shift units across the change date?
7. Which inventory statuses are physically on hand yet unavailable, and who may release a hold, reservation or quality block?
8. What actual production, component issue/backflush, scrap, return and inventory adjustment records are authoritative, and who owns reconciliation?
9. Which explanation and trace fields must a planner retain for audit and customer commitments? What errors require a hard stop rather than a warning?
10. What task-time and correctness targets would constitute useful decision support for planners, and who will conduct the observed trial?

## Recommended Phase 6B execution scope

1. Obtain expert decisions for P0 policies using the fictional cases above; keep unresolved outcomes explicitly blocked. No live data or production postings are needed to establish the rules.
2. Build an independent, reviewable scenario oracle and automated acceptance fixtures for multi-level needs, WIP/lot boundaries, stock conservation and revision-crossing backlog. Preserve the 189-test Phase 5C baseline and compare no-ECN behavior.
3. Implement only the approved, narrow planning extensions after the oracle is signed off. Keep procurement advice separate from confirmed receipts and execution transactions; add user-facing explanation for each new rule.
4. Conduct a later practitioner review with authorized fictional or approved sanitized data. Record errors and task times before claiming EMS suitability.

Phase 6A changes documentation only. It does not change any calculation engine, dashboard, transaction interface, or manufacturing data.
