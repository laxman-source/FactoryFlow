# Phase 6B.3 — Manufacturing practitioner review package

**Purpose:** Ask experienced EMS practitioners to review five unresolved planning decisions using fictional FactoryFlow examples. This is an interview guide and empty decision record, not a policy approval or a claim of industry validation.

**Sources:** [Phase 6A manufacturing validation](PHASE6_MANUFACTURING_VALIDATION.md), [Phase 6B.1 acceptance specification](PHASE6B_ACCEPTANCE_SPEC.md), and [Phase 6B.2 acceptance results](PHASE6B_ACCEPTANCE_RESULTS.md). The quantities below come from their M01, M06, M09, M10, and M13 / AC-01, AC-06, AC-09, AC-10, and AC-13 fictional cases. They are examples for discussion, not real company orders or supplier terms.

## A. FactoryFlow in two minutes

FactoryFlow is a **SIMULATION ONLY** planning prototype. It calculates direct one-level material needs, protected usable stock, dated confirmed receipts, weekday line capacity, overtime and full-day downtime, and whole-unit material-constrained builds. It can simulate an approved engineering change by production date, keep old and new component stock separate, and flag WIP or incompatible revisions for manual review. Suggested purchases are planning advice; they create neither purchase orders nor confirmed receipts. Simulated builds and stock use are **not** actual production or inventory postings.

The Phase 6B.2 suite passed **202 automated tests**. Twelve fictional acceptance cases (AC-02–AC-13) matched independently stated current-simulator results. AC-01, the multi-level BOM case, remains blocked. Tests establish software behavior for those examples. No EMS practitioner has validated these rules for a real factory, and no interview or approval has yet occurred.

The prototype does not support multi-level BOM explosion, an approved choice between two ready lots of the same product, supplier minimum order quantities (MOQ), partial WIP and issued-part records, actual production or stock transactions, or a dated recovery purchase plan for material-delayed units crossing an ECN date. Its capacity-only completion dates and nominal purchase advice are not delivery commitments.

## How to run the discussion

Plan **20–30 minutes**: 2 minutes for the introduction, about 4 minutes per scenario, and 3–5 minutes to confirm open items. Show only the fictional case cards below. Use the 15 questions in section C; a practitioner may decline or mark a rule company-specific. Record their role and relevant experience, not personal or confidential company details. Ask for the *type* of ERP/MES/quality record needed; do not copy live transactions or private supplier terms into this document. Record only authorized, fictional or suitably sanitized evidence references in section D.

For every answer, separate (1) what FactoryFlow currently simulates, (2) what the practitioner would do in their own process, and (3) what a responsible authority has formally approved. A practitioner preference is useful evidence, but it does not by itself authorize a universal manufacturing rule or a code change.

## B. Five fictional EMS decision scenarios

### S1 — Which ready lamp lot runs first? (M09 / AC-09)

**Factory situation.** On **December 1, 2026**, fictional lamp orders `L1` and `L2` each need **2 units**. Both are ready. One line can make **3 units** that day; it has **4 usable `MAT` components**, one per lamp. The case supplies no due-date ranking, customer class, dispatch authority, or tie-break. FactoryFlow currently stops with a lot-contention error and publishes no final lot allocation or consumption.

**Planner decision.** Decide which lot, if any, receives the first three capacity slots, whether a lot may be split, and what happens when no priority is authorized. Possible approaches to discuss are an approved due-date/commitment sequence, an approved manual dispatch, or a hold until the priority is recorded. Each needs its own tie-break and override control. **No choice is implied by the 3-unit capacity figure.**

**Interview prompts:** Q1–Q3 in section C cover the rule and reason, exception authority, and order/dispatch evidence.

### S2 — What parts are needed below a power module? (M01 / AC-01)

**Factory situation.** Five fictional lamps each need one `SUB-PWR`; each module contains two `CAP-10`. The conditional structural gross is **5 modules** and, **if all five modules are made**, **10 capacitors**. Module stock, make/buy status, routing, yield, lead times, receipts and revision dates are deliberately missing. FactoryFlow only explodes one BOM level. It cannot state a net capacitor purchase, release date or feasible lamp count from this record.

**Planner decision.** Establish whether the module is bought, made and stocked, or treated as a phantom assembly whose child parts are planned directly. Then define how module stock, work in process, scrap/yield, timing and revisions affect child demand. The structural 10 is **not** an approved net purchase quantity. Options are discussion prompts, not interchangeable calculations.

**Interview prompts:** Q4–Q6 in section C cover the rule and reason, approval authority, and controlled BOM/routing evidence.

### S3 — What happens to old-revision WIP at an ECN boundary? (M06 / AC-06)

**Factory situation.** A fictional **4-unit** lamp lot was created **November 30, 2026**, marked WIP, and pinned to BOM **Revision A**. `ECN-001` is supplied as approved **December 2**, with Revision B effective **December 3**. The line could make **2 units each day, December 3–4**. Fictional opening stock is `LED-100=8` and `LED-101=4`, plus enough other direct parts. FactoryFlow holds all **4 units for manual review**, simulates **0 additional builds** and **0 new component use**. It has no record of parts already issued or work actually completed.

**Planner decision.** Decide whether the lot stays on hold, receives a controlled deviation to continue A, is split, or is reworked to B. A decision also needs issued-part, acceptance, scrap and traceability treatment. No WIP is silently switched, released, reworked or scrapped by this prototype.

**Interview prompts:** Q7–Q9 in section C cover the WIP rule and reason, exception authority, and traveler/issue evidence.

### S4 — How should a supplier MOQ affect purchase advice? (M10 / AC-10)

**Factory situation.** Eleven fictional lamps each need one `MAT` by **December 10, 2026**. On **December 1**, usable stock is **3**, so the shortage is **8**. FactoryFlow knows a pack size of **5** and a **7-calendar-day** lead time; it suggests **10** units and a theoretical release date of **December 3**. A hypothetical supplier MOQ of **12** is stated outside the application. FactoryFlow has no MOQ field and has not placed an order.

**Planner decision.** Establish whether MOQ and pack multiples both apply, whether partial packs or a waiver are allowed, and what supplier calendar or inspection time changes the release date. For example, **15** follows if both a 12-unit minimum and full packs of 5 are mandatory; **12** would require an allowed partial pack; **10** would require an MOQ exception. None is assumed to be a valid order without supplier terms and buyer authority.

**Interview prompts:** Q10–Q12 in section C cover MOQ/pack reasoning, exception authority, and supplier/receipt evidence.

### S5 — How should delayed lamps be replanned after the ECN date? (M13 / AC-13)

**Factory situation.** The fictional December 1–4 window calls for **200 lamps** and **100 chargers**. Lamp Revision B becomes effective **December 3**. There is **no opening or confirmed `LED-101` supply**. The tested simulation builds **150 Revision A lamps** and **100 chargers**, leaving **50 lamps unfinished**; it builds **0 Revision B lamps**. Capacity-first *nominal* advice shows a **40-unit `LED-101` shortage** for planned B slots. Those 40 are not the full material need of the 50-unit carried backlog. If all 50 later become new B production, their structural LED-101 need would be 50 before future stock, receipts or scheduling decisions.

**Planner decision.** Decide whether the 50 units are replanned as new B work, held for revision review, or handled under a documented pinned-revision exception. Specify the future production dates, lot states, line capacity, receipt status, other component coverage and purchase-advice scope. Do not turn the 40-unit nominal signal or the conditional 50-unit structural need into an automatic purchase or promised completion date.

**Interview prompts:** Q13–Q15 in section C cover the recovery rule and reason, exception authority, and dated planning evidence.

## C. Interview questionnaire — 15 questions

Use the scenario cards in order. The three questions for each card cover the rule, decision authority and evidence. Capture a short answer or “unknown”; avoid asking for live confidential data.

| Scenario | Questions to ask |
|---|---|
| S1 — lot dispatch | **Q1.** Which ready-lot priority and tie-break would you use for L1/L2, and why? **Q2.** Who may choose or override the first lot, including a partial-lot split? **Q3.** Which order, due-date and dispatch records would support that choice? |
| S2 — multi-level BOM | **Q4.** Is `SUB-PWR` bought, stocked, made or phantom, and why should its child parts be netted and dated that way? **Q5.** Who approves the BOM treatment or an exception? **Q6.** Which BOM, routing, stock, yield, lead-time and revision records would prove the result? |
| S3 — ECN and WIP | **Q7.** What should happen to pinned-A WIP when B takes effect, and why? **Q8.** Who can authorize a hold release, A deviation, split or B rework? **Q9.** Which traveler, issued-part, inspection and ECN records must be reviewed? |
| S4 — supplier MOQ | **Q10.** How and why do MOQ 12 and pack 5 combine for this shortage, and when are exceptions allowed? **Q11.** Who can approve a waiver, partial pack or alternate source? **Q12.** Which supplier terms, calendar, quote, PO and receipt-confirmation records are authoritative? |
| S5 — revision-crossing backlog | **Q13.** How should the 50 delayed lamps be revised and dated, and why? **Q14.** Who approves any pinned-A exception, recovery priority or changed commitment? **Q15.** Which ECN, lot, stock, confirmed-receipt, line and customer records support a recovery plan? |

## D. Decision register — blank for practitioner review

**Recording convention:** “Proposed policy” names the question to resolve; it is **unapproved**. Suggested roles are interview targets, not people who have participated or signed off. Record an evidence reference only if disclosure is authorized and the material is fictional or properly sanitized. Do not paste actual transactions, supplier prices, customer names, credentials or proprietary procedures here. Use “Not reviewed” and “Blocked” until the required review and approval gates are met.

### DR-01 — Same-product lot dispatch

| Field | Entry |
|---|---|
| Proposed policy to assess | Define ready-lot ranking, tie-break, partial-lot handling, override trail, and fail-closed behavior when priority is absent. **Unapproved.** |
| Practitioner answer and rationale | **To record.** |
| Suggested practitioner role | Production control / manufacturing planner; actual role and relevant dispatch experience: **to record**. |
| Interview date | **Not scheduled / to record.** |
| Evidence provided | **None yet.** Request a sanitized dispatch SOP, order-priority fields, override record and fictional scarcity example. |
| Company-specific or potentially general? | **Undetermined.** Ask which parts depend on customer contracts or local scheduling practice. |
| Approval authority | **To establish** with production control and business owner. |
| Approval record | **None.** |
| Conflicting opinions | **Not reviewed.** Record each view and source separately. |
| Validation status | **Not reviewed.** Current software only verifies the safe error in AC-09. |
| Implementation readiness | **Blocked** pending authorized rule, input contract, independent positive/negative examples and sign-off. |

### DR-02 — Multi-level BOM requirements

| Field | Entry |
|---|---|
| Proposed policy to assess | Define make/buy/phantom classification, subassembly-stock netting, lower-level explosion, yield, date offset and revision inheritance. **Unapproved.** |
| Practitioner answer and rationale | **To record.** |
| Suggested practitioner role | Manufacturing engineering and materials planning; actual role and relevant BOM/MRP experience: **to record**. |
| Interview date | **Not scheduled / to record.** |
| Evidence provided | **None yet.** Request controlled fictional two-level BOM, routing, stock, timing and hand-calculated gross/net cases. |
| Company-specific or potentially general? | **Undetermined.** Ask which BOM conventions and lead times are site- or product-specific. |
| Approval authority | **To establish** with engineering and planning owners. |
| Approval record | **None.** |
| Conflicting opinions | **Not reviewed.** Record make/buy and netting disagreements explicitly. |
| Validation status | **Not reviewed.** AC-01 is blocked, with conditional structural gross only. |
| Implementation readiness | **Blocked** until complete inputs, independent net/date oracle, negative cases and authorized policy exist. |

### DR-03 — ECN treatment of WIP

| Field | Entry |
|---|---|
| Proposed policy to assess | Define hold, deviation, split, rework/release, issued-part reconciliation and revision trace for WIP at the effective event. **Unapproved.** |
| Practitioner answer and rationale | **To record.** |
| Suggested practitioner role | Engineering change coordinator, production and quality; actual roles and WIP/ECN experience: **to record**. |
| Interview date | **Not scheduled / to record.** |
| Evidence provided | **None yet.** Request a sanitized traveler-state model, part-issue ledger, change instruction and fictional approved/denied cases. |
| Company-specific or potentially general? | **Undetermined.** Ask whether customer or regulatory controls change the path. |
| Approval authority | **To establish** across engineering, quality and production. |
| Approval record | **None.** |
| Conflicting opinions | **Not reviewed.** Capture any disagreement about effective event or rework ownership. |
| Validation status | **Not reviewed.** AC-06 tests only the simulator's manual-review hold. |
| Implementation readiness | **Blocked** until WIP states, issued stock, approval trail and independently balanced examples are defined. |

### DR-04 — Supplier MOQ and pack precedence

| Field | Entry |
|---|---|
| Proposed policy to assess | Define MOQ units/value, full-pack precedence, allowed exceptions, calendar and usable-receipt meaning. **Unapproved.** |
| Practitioner answer and rationale | **To record.** |
| Suggested practitioner role | Buyer / supplier manager and receiving or quality representative; actual roles and relevant experience: **to record**. |
| Interview date | **Not scheduled / to record.** |
| Evidence provided | **None yet.** Request authorized fictional supplier terms, exception approval path and hand-calculated order examples. |
| Company-specific or potentially general? | **Undetermined.** Ask what varies by supplier and part. |
| Approval authority | **To establish** with buying and, where needed, quality/receiving owners. |
| Approval record | **None.** |
| Conflicting opinions | **Not reviewed.** Record any discrepancy between contract and local buying practice. |
| Validation status | **Not reviewed.** AC-10 tests pack-only advice, not an MOQ-valid order. |
| Implementation readiness | **Blocked** until terms and exception precedence are approved and tested independently. |

### DR-05 — Revision-crossing backlog recovery

| Field | Entry |
|---|---|
| Proposed policy to assess | Define a separate dated, revision-aware recovery plan for unfinished units, with lot state, future supply/capacity and advice scope. **Unapproved.** |
| Practitioner answer and rationale | **To record.** |
| Suggested practitioner role | Materials/production planning, engineering and customer-program owner; actual roles and recovery experience: **to record**. |
| Interview date | **Not scheduled / to record.** |
| Evidence provided | **None yet.** Request controlled ECN/lot/receipt records and independent nominal-versus-recovery calculations. |
| Company-specific or potentially general? | **Undetermined.** Ask what depends on customer commitment or change authorization. |
| Approval authority | **To establish** with planning, engineering and customer-commitment owners. |
| Approval record | **None.** |
| Conflicting opinions | **Not reviewed.** Keep pinned-A versus new-B views separate. |
| Validation status | **Not reviewed.** AC-13 verifies existing 250/50 output and nominal 40-unit advice only. |
| Implementation readiness | **Blocked** until recovery dates, revision rule, receipt status, priority and independently calculated purchase scope are approved. |

## E. Evaluation rubric and validation method

| Finding label | When to use it | What remains to be done |
|---|---|---|
| **Supported by practitioner evidence** | A relevant practitioner explains a specific rule, its scope and reason, and identifies an authorized, fictional or sanitized controlling record or worked example. Record role, experience, interview date and evidence reference. | Check the document owner, version, exception path and approval authority. This label **does not itself mean approved** or ready to implement. |
| **Requires further clarification** | A rule, quantity, timing, stock status or authority is missing, conditional or not supported by enough evidence. | Record the precise question and owner; keep implementation blocked. |
| **Conflicting evidence** | Practitioners or records support different policies, effective events or calculations. | Preserve each view and evidence source; seek an authorized resolution. Do not average or silently select one. |
| **Not reviewed** | No practitioner discussion or usable evidence has been recorded. This is the starting state of all five register items. | Arrange review; do not infer sign-off from FactoryFlow tests. |

After each interview, update the relevant register entry with the answer and evidence reference. Verify any proposed arithmetic independently using complete fictional inputs, including a positive and a rejection/exception case. Identify whether the policy is local to one company or could be generalized only after comparing controlled evidence; do not assume broad applicability from one interview. A rule becomes **implementation-ready only after** its authorized owner approves a versioned policy and scope, required inputs and statuses are defined, contradictions are resolved, independent expected results exist, and the Phase 6B.1 policy/oracle/architecture gates are met. Automated regression and later human review remain separate gates. Until then, the five proposed extensions remain blocked.

**Current review outcome:** No interviews conducted, no practitioner evidence entered, no policy approved, and no industry validation claimed.
