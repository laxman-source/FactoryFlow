# FactoryFlow development history — Phase 1 through Phase 6B.3

This is an audit of **existing Git history**, not a new release or manufacturing validation. The current commit IDs are the authoritative IDs in this repository; older references from before its email-metadata history rewrite may differ. The chronology below follows commit parentage and messages. It does not fill gaps with invented milestones.

## Audit basis and publication boundary

At the start of this audit, `FactoryFlow_PrivateHistory` was clean on `feature/phase6b2-acceptance-tests` at `ce50af6c485949fd434fc5ddc6613652e7e2ae09`. Local `git log --all` contains **19 reachable commits**. `git fsck --no-reflogs --unreachable` found **one additional unreachable commit object**, described below, so **20 commit objects were inspected**. There are **five local branches** and **seven lightweight recovery tags**.

The private GitHub repository `laxman-source/FactoryFlow` was checked through its live [branch refs](https://api.github.com/repos/laxman-source/FactoryFlow/git/refs/heads) and [tag refs](https://api.github.com/repos/laxman-source/FactoryFlow/git/refs/tags) on **2026-11-16**. It advertises `master` at `bcf6c903fa5e71af9697b49fd22f5fd37e494634` and `feature/phase6b2-acceptance-tests` at `ce50af6c485949fd434fc5ddc6613652e7e2ae09`, matching the local remote-tracking heads. All seven GitHub tag names and targets match the local tags. The feature head descends from master. Consequently, all 19 reachable commits in this audit are published to the **private** GitHub repository: the first 15 through `master`, and the four Phase 6 commits through the feature branch. Publication does **not** imply acceptance, practitioner approval, public release, or deployment. The local Phase 5C, Phase 6A and Phase 6B.1 branch names are not separate live GitHub branches; their commits are reachable through the two advertised heads.

**Test-evidence rule:** A commit adding tests or saying “Verified” is evidence of intent, but not an independently recorded pass count. Numerical totals below appear only where a tracked project document records them: [ECN design](ECN_DESIGN.md) records 124 at the Phase 4D baseline, [Phase 6A validation](PHASE6_MANUFACTURING_VALIDATION.md) records 189 at the merged Phase 5C baseline, [Phase 6B.1 specification](PHASE6B_ACCEPTANCE_SPEC.md) carries 189, and [Phase 6B.2 results](PHASE6B_ACCEPTANCE_RESULTS.md) records 202. No historical test suite was rerun for this documentation audit.

## Complete reachable commit chronology

`M` means reachable from the live private GitHub `master` head; `F` means reachable from the live private GitHub `feature/phase6b2-acceptance-tests` head. `M+F` is abbreviated as `M` because master is an ancestor of the feature branch. These are **publication locations**, not release statuses. A dash in the tag column means no tag exists for that commit.

| Order | Recorded phase or event | Commit | Existing recovery tag | GitHub ref |
|---:|---|---|---|---|
| 1 | Phase 1 — verified MRP calculations | `c0b2e61acffad91a40351319f4dcc15999fade98` | `phase1-verified` | M |
| 2 | Phase 2 Stage 1 — capacity engine | `f76d542ec31b0663ee5f8ccf59a91a93fa9408e8` | — | M |
| 3 | Phase 2 — capacity engine and dashboard | `2ac4bc19d907b705b3d9ebd28bac9fbbc7b0d9b9` | `phase2-capacity-verified` | M |
| 4 | Phase 2 Stage 3A — overtime/downtime engine | `e0269eb0b22146c3d7afd5f80fee50fc48ee874d` | — | M |
| 5 | Phase 2 Stage 3B — overtime/downtime dashboard | `5da57d6f353ec0604cb85ad7916c89e51e4bcf0b` | `phase2-stage3-verified` | M |
| 6 | Phase 4A — time-phased material availability | `abb5cad8444822f757e30db5cd049143969b747f` | `phase4a-material-verified` | M |
| 7 | Phase 4B — supply-constrained production | `a5398abb0d906dd738762ed6c012b3d506c7ca86` | `phase4b-scheduler-verified` | M |
| 8 | Phase 4C — integrated production dashboard | `8e36aa2c1bc46e9734a064a3581b9e9d9232e5f9` | `phase4c-dashboard-verified` | M |
| 9 | Phase 4D — manufacturing planning audit | `de7bf281f5929aa069c6a0b0e58450600827e974` | `phase4d-integrated-verified` | M |
| 10 | Phase 5A — ECN design | `25964199dc802bab6bc5c75e8f1ef414f430e3ad` | — | M |
| 11 | Phase 5B — ECN engine | `4ede90debf5fd2339d3c63cdc442b9315058bb3e` | — | M |
| 12 | Security — Git ignore hardening | `c16dfd3163490c28a59bb90120c4ea2b5db6428b` | — | M |
| 13 | Phase 5C — ECN dashboard integration | `c5df721d05dd7b7bfad57130f8f2d60a7150f8b5` | — | M |
| 14 | Phase 5C — dashboard reporting corrections | `6537847aeea405e76500ab434604f3f484eedf7b` | — | M |
| 15 | Merge of Phase 5C into master | `bcf6c903fa5e71af9697b49fd22f5fd37e494634` | — | M |
| 16 | Phase 6A — manufacturing validation design | `4febf7fae5a18ba485213baccd43947a5d33ad85` | — | F |
| 17 | Phase 6B.1 — acceptance specification | `449c9f498731681134eb79c9a1082924754d61fe` | — | F |
| 18 | Phase 6B.2 — independent acceptance tests | `e65829e5047aaf45ad05cdf82533a9cf37b55647` | — | F |
| 19 | Phase 6B.3 — practitioner review package | `ce50af6c485949fd434fc5ddc6613652e7e2ae09` | — | F |

The security commit is part of the development chronology, but it is not a manufacturing phase. The Phase 5C merge has two parents: the security-hardened master line and the corrected Phase 5C feature line. Its tree is the integrated Phase 5C snapshot.

## Phase-by-phase objectives, delivery, tests and limits

Commit IDs, tags and private GitHub ref locations for each row are in the chronology above. “No count recorded” means no checkpoint-specific passing total was found in tracked project documents; it does **not** mean tests failed or were absent.

| Phase | Development objective and functionality delivered | Supported test result | Known technical limit at the checkpoint |
|---|---|---|---|
| **Phase 1** | Establish a fictional single-date MRP example: direct BOM multiplication, usable stock, component shortages, pack-rounded purchasing advice, Streamlit view and initial planning/scenario tests. | Planning and scenario test files were committed; **no exact pass count recorded** in tracked documents. | One-level BOM and one common need date; suggestions are not orders. |
| **Phase 2** | Add dedicated weekday line capacity (Stage 1), capacity dashboard, integer overtime and full-day downtime engine (Stage 3A), and matching dashboard controls (Stage 3B). | Capacity and dashboard tests were committed at each relevant step; **no exact pass count recorded**. | Capacity-only dates ignore materials; no shift, labor, setup, holiday or shared-machine model. |
| **Phase 3** | **No independent Phase 3 objective or delivery can be established from this history.** | No separately identifiable Phase 3 commit, tag or test record. | “Phase 2 Stage 3A/3B” names a stage within Phase 2, not a standalone Phase 3. Do not manufacture a checkpoint. |
| **Phase 4A** | Add a dated component-availability ledger with protected opening stock, confirmed receipts, daily use and unmet needs. | Timeline tests committed; **no exact pass count recorded**. | Receipt due date is assumed usable date; inspection/release is not modeled. |
| **Phase 4B** | Add finite daily production scheduling constrained by direct components, shared stock, whole builds and line capacity. | Scheduler tests committed; **no exact pass count recorded**. | Fixed ascending-SKU product priority; no same-product lot dispatch or post-window promise. |
| **Phase 4C** | Integrate MRP, capacity, timeline and production views in Streamlit. | Dashboard integration tests committed; **no exact pass count recorded**. | Results remain simulated; capacity-only and material-constrained dates have different meanings. |
| **Phase 4D** | Audit manufacturing planning, correct MRP treatment of unconfirmed receipts, add regression cases and clarify dashboard wording and purchase-advice scope. | **124 existing tests passed** at this baseline, recorded by the later Phase 5A design review. | Still a simplified one-level planning simulator; no actual inventory or production posting. |
| **Phase 5A** | Document ECN statuses, BOM revisions, effective dates, old-stock/WIP safeguards and independent scenarios A–H in `ECN_DESIGN.md`. | Documentation-only commit; its design review records **124 existing baseline tests passed**. | Design did not activate an ECN or implement planning behavior. |
| **Phase 5B** | Implement ECN records/status validation, revision-aware daily planning, separate LED balances, stock holds, WIP/revision review, shared allocation and trace; add ECN regression tests. | ECN tests committed; **no Phase 5B-specific pass total recorded** in tracked documents. | No actual approval, WIP release, stock transaction or automatic supplier receipt. |
| **Phase 5C** | Add ECN simulation dashboard and scenarios, correct nominal requirement handling for future authorized stock holds, then improve product-level outstanding-demand and safety-stock displays; merge the corrected feature into master. | ECN dashboard tests and corrections committed. The subsequent Phase 6A audit records **189 passing tests at the merged master baseline**; individual Phase 5C commit totals are not separately recorded in tracked documents. | UI remains simulation-only; nominal purchase advice is not a material-constrained backlog recovery plan. |
| **Phase 6A** | Document manufacturing reality audit, 13 fictional EMS cases, capability limits and practitioner validation gates. | **189 existing tests passed**, recorded in `PHASE6_MANUFACTURING_VALIDATION.md`; no production code changed. | Audit is not shop-floor or industry validation. |
| **Phase 6B.1** | Turn the Phase 6A cases into a business-rule decision register and independent acceptance oracles. | **189 existing tests passed**, recorded in `PHASE6B_ACCEPTANCE_SPEC.md`; documentation-only commit. | Proposed policies remain unapproved; AC-01 lacks complete multi-level rules. |
| **Phase 6B.2** | Add executable fictional acceptance checks for AC-02–AC-13 and document expected-versus-actual results. | **202 passed**: 189 prior tests plus 13 new tests, recorded in `PHASE6B_ACCEPTANCE_RESULTS.md`. | AC-01 and proposed extensions remain blocked; tests show internal simulator conformance, not practitioner approval. |
| **Phase 6B.3** | Prepare five fictional practitioner decision scenarios, a 15-question interview guide, blank decision records and evidence rubric. | Documentation-only commit; it cites the **202-test Phase 6B.2 result**, with **no new test run recorded** for Phase 6B.3. | No interview, signed rule or industry validation has occurred. |

The Phase 6 documents and README describe the current simulator and limits in more detail. The [practitioner package](PHASE6B_PRACTITIONER_REVIEW.md) keeps the five proposed policies marked not reviewed and blocked. **Phase 6C has no completed commit in this audited history.**

## Additional object outside the reachable history

`git fsck` found unreachable commit `5b6e1e28e4e4efa54eb3df458f4467c9cb4ce50e`. It has the **same two parents, source tree and message** as the reachable Phase 5C merge `bcf6c903fa5e71af9697b49fd22f5fd37e494634`, but different author/committer metadata. No local branch or tag points to it, and it is not reachable from the two advertised GitHub heads or the seven tags. It is **not counted as a twentieth development milestone**. The audit cannot establish whether that unreferenced object was ever sent to a remote in the past; current refs do not publish it. Do not delete or rewrite it as part of documentation work.

## Repository organization recommendations — no ref changes made

1. **Keep the seven existing tags.** They provide adequate immutable names for the verified Phase 1, Phase 2 capacity and Stage 3B, and Phase 4A–4D snapshots. Their local and live GitHub targets match. Do not move or reuse them.
2. **Do not create a Phase 3 tag.** There is no separate Phase 3 checkpoint to name. Do not tag every documentation step merely to fill a numerical sequence; the Phase 5A/B and Phase 6A/B commit IDs already identify their exact snapshots.
3. **Optional future recovery tag:** If a named post-integration checkpoint is useful, review and then create a new lightweight `phase5c-merged` tag at `bcf6c903fa5e71af9697b49fd22f5fd37e494634`. This would describe an observed merge, not imply practitioner validation. No tag was created by this audit.
4. **Keep experimental work distinct from accepted releases.** `master` is the integrated software baseline through Phase 5C; Phase 6A–6B.3 live on a feature branch. Private GitHub publication is not acceptance. Reserve any future release/acceptance tag for a reviewed commit with a recorded test result, decision owner and explicit scope. A practitioner-approved manufacturing rule needs its own signed evidence; a passing test or merge is insufficient.
5. **Link the README to this record.** Under the README's project-file or documentation section, add a relative link such as `[Development history](docs/FACTORYFLOW_DEVELOPMENT_HISTORY.md)`, explaining that it lists Git checkpoints, tags, publication status and evidence limits. This audit leaves `README.md` unchanged.

This document audits only the repository objects and live refs observed on the date above. Its own documentation commit comes **after** the 19-commit source chronology and is local until separately published. A future push, tag change or release can change publication status. No history was rewritten, no existing tag was moved, and no branch was merged, pushed or deployed for this audit.
