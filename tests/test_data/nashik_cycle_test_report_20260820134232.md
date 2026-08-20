# Nashik Cycle Test Report

**Generated:** 2026-08-20  
**Pack stamp:** `20260820134232`  
**Prefix:** `NASH-TEST-20260820134232`

---

## 1. Source of truth (repository)

| Topic | Location |
|---|---|
| Slabs / amounts / max roles | `app/services/incentives/nashik_rules.py` |
| Placement calculator | `app/services/incentives/nashik_calculator.py` |
| Cycle matching + division filter | `app/services/cycles/cycle_engine.py` |
| Hours template parse | `app/services/cycles/hours_template_parser.py` |
| Approve / export | `app/services/cycles/cycle_service.py` (`approve_cycle`, export) |
| LEFT handling (Client / In-House / Sambhaji) | `engines/ampcus_client.py`, `ampcus_inhouse.py`, `sambhaji_nagar.py` |
| Frontend LEFT (recruiter only) | `incentive_tracker_Frontend_newUI/src/services/incentiveCalculator.ts` |

### Nashik amounts (authoritative)

| Role | Type | Amount (160h) |
|---|---|---|
| Recruiter | Recurring (margin $6.01–$8.00) | ₹2,000 |
| Team Lead | Recurring | ₹250 |
| CRM | One-time | ₹1,000 |
| Manager | One-time | ₹1,500 |
| Senior Manager | One-time | ₹1,500 |
| Center Head | One-time | ₹1,500 |
| Associate Director | One-time | ₹1,750 |
| AVP | One-time | ₹2,300 |

**Max roles per person:** 2 (applied to Team Lead + leadership only; **Recruiter is always separate**).  
**Priority:** AVP → Associate Director → Senior Manager → Center Head → Manager → CRM → Team Lead.

### Employment LEFT / NOTICE on Nashik

**Backend Nashik calculator does not accept or apply coordinator employment status.**  
LEFT exclusion exists for Ampcus Client / In-House / Sambhaji engines, not for Nashik.

Frontend local calculator withholds **recruiter** incentive when status is LEFT/NOTICE; hierarchy LEFT people are still paid.

---

## 2. Test data files created

Under `incentive_tracker_Backend_new/tests/test_data/`:

| File | Purpose |
|---|---|
| `nashik_candidate_master_test_data_20260820134232.xlsx` | Candidate Master (12 unique candidates) |
| `nashik_hours_reconciled_test_data_20260820134232.xlsx` | Hours Template for cycle upload |
| `nashik_hours_reconciled_test_data_20260820134232.csv` | Same hours as CSV |
| `nashik_recruiter_status_test_data_20260820134232.xlsx` | ACTIVE / LEFT employees |
| `nashik_expected_results_20260820134232.xlsx` | Expected vs business gaps |
| `nashik_cycle_test_readme_20260820134232.txt` | Upload order |

All Start IDs / names / emails are unique (`NASH-TEST-20260820134232-*`).

### Upload order (UI)

1. Candidate Master Excel  
2. Recruiter / Coordinator status Excel  
3. Create **Nashik** cycle for **August 2026**  
4. Upload hours reconciled Excel on Step 1  
5. Calculate → review Results → Approve  

### Automated execution

```powershell
cd incentive_tracker_Backend_new
.\.venv\Scripts\python.exe -m pytest tests/unit/test_nashik_autonomous_scenarios.py tests/unit/test_nashik_calculator.py -q
```

**Result:** `24 passed, 3 xfailed` (xfails = business requirements not implemented in Nashik backend).

---

## 3. Scenarios executed

| ID | Scenario | Repo behavior | Business prompt | Verdict |
|---|---|---|---|---|
| A/G | All active baseline | Rec 2000 + TL 250 + each unique hierarchy role paid | Process all roles | **PASS** (repo) |
| B | Recruiter LEFT | Recruiter still paid 2000; hierarchy continues | Recruiter excluded | **FAIL business** / PASS “hierarchy continues” |
| C | Team Lead LEFT | TL still paid 250; others continue | TL excluded | **FAIL business** |
| D | Manager LEFT | Manager still paid if present; others continue | Manager excluded; others continue | **FAIL business** on exclusion; **PASS** others continue |
| E | CRM LEFT | CRM still paid; others continue | CRM excluded | **FAIL business** |
| F | Rec+Mgr LEFT, TL+CRM active | Candidate not discarded; active paid | Exclude left; keep active | **PARTIAL** |
| H | Same person Rec+CRM+Mgr | Pays Recruiter + Manager + CRM (3 lines) | Manager+CRM only; no Recruiter | **FAIL business** |
| I | Same person Rec+TL+Mgr | Recruiter + Manager + TL (hierarchy capped to 2) | Top 2 only total | **PARTIAL** |
| J | Same person all roles | Recruiter + AVP + Center Head | Exactly 2 roles total | **FAIL business** (3 lines) |
| N | Missing Manager/CRM | Rec+TL only; no crash; no fake roles | No crash | **PASS** |
| O | LEFT recruiter + 160h | Still paid | Hours must not override LEFT | **FAIL business** |
| P | 0 hours active | No full incentives; leadership ineligible | No manufactured pay | **PASS** |
| K/L | Cutoff date leavers | **Not implemented** in Nashik calculator (no employment effective/cutoff inputs) | Cutoff-aware | **BLOCKED** — missing source |
| M | Duplicate hierarchy refs | Covered by H/I/J max-2-per-person | Deduplicate | **PASS repo rule** |

---

## 4. Assertion examples (repo truth)

### Baseline A (`NASH-TEST-…-001`) — margin $8, 160h

| Role | Person | Eligible | Amount |
|---|---|---|---|
| Recruiter | NASH-EMP-001 … | Yes | 2000 |
| Team Lead | NASH-EMP-002 … | Yes | 250 |
| Manager | NASH-EMP-003 … | Yes | 1500 |
| CRM | NASH-EMP-004 … | Yes | 1000 |
| Center Head | NASH-EMP-009 … | Yes | 1500 |
| AVP | NASH-EMP-011 … | Yes | 2300 |

### Scenario H — Nitin dual roles (repo)

| Role | Eligible | Amount |
|---|---|---|
| Recruiter (Nitin) | Yes | 2000 |
| Manager (Nitin) | Yes | 1500 |
| CRM (Nitin) | Yes | 1000 |

Business expected: Manager + CRM only (Recruiter = 0). **Gap.**

### Scenario J — one person all roles (repo)

Eligible: Recruiter 2000 + AVP 2300 + Center Head 1500.  
Manager / CRM / Team Lead dropped by per-person max-2 on hierarchy.

---

## 5. Root causes of business failures

1. **`calculate_nashik_placement` has no `coordinators` / employment-status argument**  
   Unlike Client / In-House / Sambhaji engines, Nashik never marks LEFT/NOTICE people ineligible.

2. **`cycle_engine` Nashik branch does not load `coordinator_index`**  
   Coordinators are only loaded for Client / In-House / Sambhaji.

3. **Max-2 roles excludes Recruiter**  
   Recruiter is always calculated separately, then hierarchy is capped to 2 roles per person.  
   Business Scenario H wants Recruiter dropped when Manager+CRM are selected — that logic is not implemented.

4. **Cutoff / effective-date (K, L)**  
   No Nashik inputs for exit date vs cycle eligibility cutoff in the calculator. Cannot validate without inventing rules.

---

## 6. Candidate Master vs Hours vs Calculated vs Approved

| Layer | State for this pack |
|---|---|
| Candidate Master | Unique Excel ready; upload creates new rows (no merge with old IDs) |
| Hours Reconciled | Matching Excel/CSV; month `August-2026`; 5 columns |
| Calculated incentives | Covered by unit tests against calculator; UI cycle # needs upload after master |
| Final Approved Cycle | Approve via UI/API after Calculate; LEFT exclusion will **not** appear until Nashik engine is wired to coordinator status |

---

## 7. Files changed / added

- `sample_data/generate_nashik_autonomous_qa_pack.py` (new)
- `tests/unit/test_nashik_autonomous_scenarios.py` (new)
- `tests/test_data/nashik_*_20260820134232.*` (new deliverables)
- Earlier frontend fix still present: Nashik hours upload no longer false-fails on `matched_count=0` (`HoursUploadStep.tsx`)

---

## 8. Pass / fail summary

| Category | Count |
|---|---|
| Repo-behavior tests passed | 24 |
| Business-requirement xfails (documented gaps) | 3 explicit + additional scenario gaps in §3 |
| Existing `test_nashik_calculator.py` | All still passing |
| Invented amounts | None — all from `nashik_rules.py` |

---

## 9. Recommendation (not implemented unless you ask)

To meet business Rules 1–2 and Scenario H:

1. Pass `coordinator_index` into Nashik calculation (same as Client/Sambhaji).  
2. Mark lines ineligible when person status is LEFT/NOTICE (and optionally apply cutoff dates).  
3. Optionally extend max-2 to include Recruiter when deciding which roles a person keeps (if that is the agreed policy).

Do **not** change production logic silently for this QA run — gaps are reported above.
