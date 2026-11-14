# FactoryFlow Phase 5A — Engineering Change Notice design

**Status:** Design only. No ECN code, dashboard change, inventory transaction, or supplier order is part of Phase 5A. All products, parts, quantities, people, and dates below are fictional.

**Verified starting point:** Phase 4D, recovery tag `phase4d-integrated-verified`; 124 existing tests passed during this design review.

## 1. Change being designed

| Field | Fictional value |
|---|---|
| ECN | `ECN-001` |
| Product | `FG-LAMP-01` — Smart Desk Lamp |
| Current BOM | Revision A, one `LED-100` per lamp |
| Proposed BOM | Revision B, one `LED-101` per lamp |
| Other lamp BOM lines | Unchanged: one housing, four screws, one adapter per lamp |
| Proposed first day for Revision B | 2026-12-03 |

`LED-100` and `LED-101` are distinct SKUs. A unit of one is never counted as a unit of the other. The proposed date has no planning effect while `ECN-001` is in draft or cancelled.

## 2. Existing system and integration points

- `factoryflow/data.py` holds one unversioned BOM list, inventory by component SKU, and dated receipts. It has no ECN status, BOM revision, hold stock, or WIP record.
- `factoryflow/planning.py` multiplies demand by one BOM for one production-start date. It protects reserved and safety stock, counts only confirmed on-time receipts, rounds shortages to supplier packs, and calculates a theoretical release date. One call cannot correctly represent Revision A on December 2 and Revision B on December 3.
- `factoryflow/material_timeline.py` keeps a separate daily balance for each component SKU. Confirmed receipts enter on their due date before that day's use. It accepts component requirements already calculated by its caller; it does not choose a BOM revision.
- `factoryflow/production_schedule.py` currently builds one component-usage map before iterating over production dates. It applies dedicated-line capacity, charger-first shared-stock priority, complete-BOM consumption, and carries unfinished demand within the selected window. Replacing its single BOM input with Revision B for a whole window would wrongly change pre-effective production.
- `factoryflow/capacity.py` has no BOM dependency. Capacity-only finish dates remain separate from material-constrained results.
- `app.py` passes the unversioned demo BOM into MRP and the integrated scheduler. A later ECN view must label revision-aware results clearly without changing the no-ECN default.

The current demo has `LED-100` stock and a confirmed 40-unit `LED-100` receipt due November 27, but **no `LED-101` inventory master or receipt**. A future ECN plan must add an explicit fictional `LED-101` master, even if its opening on-hand quantity is zero; otherwise approval or simulation should fail clearly. Existing `LED-100` quantities do not fill that gap.

**Compatibility risk:** Running MRP once per revision or running the current scheduler twice is not enough. Both approaches can count the same shared inventory or line capacity twice, and separate runs lose unfinished demand and stock carried between dates. A future integration needs one daily schedule and one stock ledger with a BOM lookup for each product and day. The 124 Phase 4D tests remain the no-ECN regression gate.

## 3. Business workflow and approval rules

1. **Draft:** Engineering records the proposed replacement, Revision B lines, proposed date, reason, and affected product. Planners may preview an impact report, clearly marked *unapproved*. The active BOM and production plan stay on Revision A.
2. **Impact review:** Engineering checks the full BOM; supply planning checks both SKU balances, open `LED-100` receipts, `LED-101` lead time and pack size, shortages, and a disposition proposal. Production control identifies released orders and WIP that may cross the date. These checks do not perform stock transactions.
3. **Approve:** An authorized engineering approver records approval, a final effective date, and the revision. Reject approval if the new BOM is incomplete, a required component has no inventory master, the date is invalid, or another approved revision would be active on the same product/date. Record who approved and when. The effective date must be later than the approval calendar date in the first date-only version; a same-day change needs a later design with a shift cutoff and timestamp.
4. **Before effect:** Approval locks the change definition but does not use Revision B early. A pre-effective cancellation returns future planning to Revision A and retains an audit record. No silent revision or inventory change occurs.
5. **On and after effect:** New, unstarted production dated 2026-12-03 or later uses Revision B. Production dated before then uses Revision A. The order-creation date does not choose the BOM. Unfinished units are evaluated again on the day the simulation could build them. If real execution is ever integrated, its recorded production date must govern actual revision traceability.
6. **Released order or WIP:** An order already pinned to Revision A is **not silently switched**. Any portion that would be built on or after the effective date is put in a manual-review state until production control records an approved split, deviation, rework instruction, or other disposition. Do not assume parts already issued to WIP were returned or reworked. New Revision B lots may proceed if otherwise ready.
7. **After effect:** Do not cancel an already effective change retroactively. A correction requires a new approved, dated superseding ECN; keep the history of the earlier revision and any production attributed to it.

Allowed state transitions for this first design are `draft → approved`, `draft → cancelled`, and `approved → cancelled` only before the effective date. A cancelled notice never becomes active again; a replacement needs a new reference. A late approval cannot backdate the effective day: revise the date and repeat conflict and impact checks. If approval or revision selection is uncertain, block affected planning output and request manual resolution.

## 4. Proposed records

| Record | Minimum fields and purpose |
|---|---|
| `BOMRevision` | `(finished_sku, revision)` key; immutable positive whole-number component lines; `created_from_ecn`. Revision A remains preserved after B is approved. |
| `ECN` | Unique reference, product, from/to revision, status, proposed and approved effective dates, approval date/time and approver ID/role, cancellation date/reason, disposition plan, WIP review reference. |
| `ECNChangeLine` | Old component and quantity per unit; replacement component and quantity per unit. For `ECN-001`: `LED-100 × 1 → LED-101 × 1`. Validate the complete Revision B BOM, not only this delta. |
| `InventoryItem` | Separate rows for `LED-100` and `LED-101`, including on-hand, reserved, safety, lead days, pack size, and an explicit ECN/quality hold quantity or status. A held quantity cannot be offered as usable stock. |
| `Receipt` | Receipt reference, component SKU, quantity, due date, and confirmed flag. Changing an ECN does not rewrite receipt SKU or due date. |
| `ProductionOrder/Lot` | Order/lot ID, product, quantity, creation date, released/pinned revision, WIP status, parts already issued, review decision. New day-level lots can receive the active revision; pinned lots need review at a change boundary. |
| `PlanTraceRow` | Run ID, product, order/lot ID, simulated production date, selected BOM revision, ECN reference, simulated units, component quantities, and reason if blocked. Preserve these fields in summaries and exports. |

Keep revision definitions separate from their activation dates. A draft Revision B may exist for review without shortening the active Revision A interval. After approval, resolve exactly one active revision for each `(product, production date)` using half-open intervals: Revision A through 2026-12-02; Revision B from 2026-12-03 until a later approved change. Reject gaps and overlaps rather than selecting whichever record was entered last.

## 5. Material, purchasing, and old-stock rules

- For each scheduled production date, multiply that day's intended units by the **resolved** BOM revision. Before December 3, lamps require `LED-100`; from December 3, new unstarted lamps require `LED-101`. Other BOM components continue to be required on both sides of the date.
- Keep a separate daily balance for each LED SKU. A receipt for `LED-100` stays `LED-100`, even if it arrives after the effective date. An unconfirmed receipt is excluded. A purchasing suggestion creates no confirmed receipt.
- Show dated `LED-101` shortages and the first day they block Revision B. Use its own fictional lead days and pack size for purchase advice. Calculate a latest theoretical release date from the **first need date**, not the order-creation date. A late release is an expedite risk, not a promised delivery. Do not hide a December 3 shortage merely because a receipt arrives on December 4.
- A Revision A surplus cannot cover a Revision B shortage. There is no automatic substitution, conversion, or netting of `LED-100` against `LED-101`.
- **Use-up:** Allow old stock only for authorized Revision A production before the effective date, unless a separately approved dated deviation explicitly changes that rule. A use-up policy must not silently postpone Revision B.
- **Hold:** Keep physical old stock in its own SKU balance but remove the held quantity from usable stock. Record who authorized the hold and when.
- **Return:** Flag stock and open old-SKU deliveries for supplier discussion. Reduce stock only after a separately recorded, authorized return transaction; do not assume the supplier accepts it.
- **Scrap:** Require explicit approval and a recorded quantity/date before reducing on-hand. An ECN proposal or approval alone never scraps stock.
- Existing confirmed `LED-100` deliveries due after December 3 remain old-SKU receipts. Flag them for manual cancellation, reschedule, return, or hold review. Do not edit their confirmation or silently convert them to `LED-101`.

The first ECN version should produce **planning advice**, not procurement or inventory postings. Where the current inventory model lacks a hold field, a future adapter must represent hold stock explicitly before calling the legacy usable-stock formula; it must not overwrite the stored on-hand figure.

## 6. Independently calculated examples

These examples use a small **fictional test fixture**, separate from the dashboard defaults, so the date boundary is visible. Snapshot: 2026-11-30. One lamp needs one LED board; all other lamp parts are sufficient. Lamp capacity is two units per weekday, no overtime or downtime. Eight unstarted lamps are requested across December 1–4, two potential builds per day. Starting usable stock is `LED-100 = 8` and `LED-101 = 4` unless a row says otherwise. Revision B replaces one `LED-100` with one `LED-101` per lamp. For purchase examples, `LED-101` has fictional lead time **7 calendar days** and pack size **5**. Approval, where used, occurs December 2 for a December 3 effective date. There is no WIP in A–G.

| Case | Changed input | Expected simulated builds and closing LED balances |
|---|---|---|
| **A. Draft** | `ECN-001` remains draft through Dec 4. | Rev A builds `2 + 2 + 2 + 2 = 8`; Rev B builds 0. `LED-100: 8 − 8 = 0`; `LED-101: 4`. Proposed date has no effect. |
| **B. Approved, before effect** | Approved Dec 2; evaluate a four-lamp order dated Dec 1–2 only. | Four Rev A lamps, zero Rev B. `LED-100: 8 − 4 = 4`; `LED-101: 4`. Approval alone does not activate B early. |
| **C. Spans effective date** | Approved Dec 2; eight unstarted lamps, Dec 1–4. | Dec 1–2: four Rev A lamps use four `LED-100`. Dec 3–4: four Rev B lamps use four `LED-101`. Eight complete; `LED-100: 4`, `LED-101: 0`. Each day/lot records its revision. |
| **D. New-part shortage** | As C, but starting `LED-101 = 1`. | Four Rev A plus one Rev B = **5 complete, 3 unfinished**. `LED-100: 4`, `LED-101: 0`. The three-unit new-part shortage suggests one five-unit supplier pack. First need Dec 3 minus seven calendar days gives Nov 26, already past at the Nov 30 snapshot; mark expedite risk, not a receipt. |
| **E. Excess old stock** | As C, but starting `LED-100 = 12`; an authorized hold of the old-stock remainder begins Dec 3. | Four Rev A plus four Rev B = eight complete. `LED-100: 12 − 4 = 8` physically on hand, all eight held and unavailable; `LED-101: 0`. No old board is used in B and no stock is automatically scrapped. |
| **F. New-part receipt late for first B day** | As C, but starting `LED-101 = 0`; four confirmed `LED-101` arrive Dec 4. | Dec 1–2: four Rev A. Dec 3: zero Rev B. Dec 4: capacity permits two Rev B. **6 complete, 2 unfinished**; `LED-100: 4`, `LED-101: 4 − 2 = 2`. The receipt cannot repair Dec 3 output. |
| **G. Cancelled** | ECN cancelled Dec 2 before effect. | Rev A remains active on all four days: eight Rev A complete; `LED-100: 0`, `LED-101: 4`. Cancellation leaves an audit record. |
| **H. Conflicting approvals** | `ECN-001` activates Rev B on Dec 3, and another fictional approved ECN also activates a different lamp revision that day. | Two candidates exist for Dec 3. Reject the revision calendar and publish **no final schedule or stock consumption** for the conflicting plan. Do not choose B, the other revision, or A by default. After resolution, recalculate from the unchanged input snapshot. |

Case C assumes each day's two units are new, unstarted lots. If a released Revision A lot instead crosses December 3, its post-effective portion is held for WIP review; Case C must not be used to imply that it was automatically reworked or changed to B. Case F also shows why a whole-window material total is insufficient: four new boards eventually arrive, but only two can be built in the remaining operating day.

## 7. Future integration architecture

1. **Validate and resolve:** Load immutable BOM revisions and ECN history. Check approval, date order, complete BOM lines, component masters, cancellation, and unique active revision for every product/date. Keep the no-ECN path mapped to the current static BOM.
2. **Classify production:** Separate new unstarted daily lots from orders pinned to a revision or containing WIP. Resolve the active revision by each simulated production date for new lots. Hold affected pinned/WIP lots pending manual decision; never silently change their parts.
3. **Generate dated needs:** Create a `(date, finished SKU, revision, component SKU, quantity)` requirement stream. Use it for time-phased shortage reporting and purchase advice. Do not call the current one-bucket MRP once for the entire mixed-revision window or add per-revision MRP stock balances together.
4. **Schedule once:** Extend or wrap the integrated daily loop so it looks up that day's BOM per product while retaining one shared component ledger, the existing charger-first rule, line capacity, protected stock, receipt timing, atomic whole-unit use, and unfinished-demand carryover.
5. **Trace and reconcile:** Attach revision and ECN IDs to each simulated build row and component-use row. Reconcile `opening usable + confirmed receipts − simulated use = closing usable` separately for every component SKU. Sum builds by product, date, and revision. Report holds and unresolved conflicts separately from material and capacity shortages.
6. **Present results:** If a future dashboard is added, label all output as simulated. Show capacity-only finish estimates separately from material-constrained ECN results. Clearly show old-stock disposition and `LED-101` shortage/release risk without treating suggestions as deliveries.

Keep the existing no-ECN functions and their output contract stable where possible. An ECN-aware adapter or new versioned scheduler is safer than changing the meaning of the current `bom` argument. No implementation choice is made in Phase 5A.

## 8. Automated test plan for a later implementation

- Assert A–H against the exact independent quantities and closing balances above, including the December 3 boundary and the late December 4 receipt.
- Assert draft, cancelled, unapproved, late-approved, invalid BOM, missing inventory master, and overlapping approved revisions never change active production silently.
- Assert order creation before the effect does not force old BOM use for **new** production after the effect, while a pinned released order or WIP crossing it is held for manual review.
- Assert `LED-100` and `LED-101` remain separate through requirements, receipts, stock holds, purchase advice, consumption, and closing balances. No substitution, automatic scrap, or invented confirmed receipt is allowed.
- Assert exact date/revision/ECN trace rows, including a split across December 2–3, and conservation of every component for every day.
- Assert returns and scrap affect stock only when an authorized dated transaction is explicitly modeled. Open old-SKU receipts remain old SKU until separately changed.
- Rerun all 124 Phase 4D tests unchanged. With no ECN supplied, compare MRP, capacity, daily builds, shared-stock allocation, component use, balances, and dashboard values against the verified baseline.

## 9. Implementation risks and decisions to settle

| Risk | Required control before coding |
|---|---|
| Mixed-revision order crosses the effect | Decide lot split and released/WIP hold procedure; retain order and revision trace. |
| Approval on the effective day | Use the conservative later-date rule above until approval and shift times are modeled. |
| Old-stock use-up conflicts with new design | Require a separately approved deviation or a revised effective date; never make use-up an implicit substitution. |
| Holds are absent from current stock schema | Add explicit held quantity/status in an adapter or new model; preserve on-hand and protected-stock accounting. |
| Current one-date MRP hides mid-window timing | Use dated requirements and first-shortage dates; do not claim an end-window receipt covered earlier production. |
| Two approved changes claim one date | Reject approval or planning until a unique effective revision is established. |
| Existing receipts name old SKU | Keep their SKU and confirmation as recorded; report supplier/disposition action separately. |

**Phase 5A exit:** This document defines the proposed rules and test oracle. It does not approve `ECN-001`, activate Revision B, or alter any verified planning calculation.
