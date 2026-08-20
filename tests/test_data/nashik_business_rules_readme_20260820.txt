NASHIK BUSINESS RULES QA PACK — August 2026
========================================================================

Generated files (real .xlsx via openpyxl):
  1. nashik_business_rules_candidate_master_20260820.xlsx
  2. nashik_business_rules_recruiter_status_20260820.xlsx
  3. nashik_business_rules_hours_reconciled_20260820.xlsx
  4. nashik_business_rules_expected_results_20260820.xlsx
  5. nashik_business_rules_readme_20260820.txt

Location:
  C:\Users\mukesh.pawar\OneDrive - Ampcus Tech Pvt Ltd\Desktop\Incentive_14-26\incentive_tracker_Backend_new\tests\test_data

UPLOAD ORDER
------------------------------------------------------------------------
1. Upload Candidate Master  → nashik_business_rules_candidate_master_20260820.xlsx
2. Upload Employee/Recruiter Status → nashik_business_rules_recruiter_status_20260820.xlsx
3. Create Nashik Division Incentive Cycle for August 2026
   (cycle start 2026-08-01, cycle end 2026-08-31)
4. Upload Hours Reconciled → nashik_business_rules_hours_reconciled_20260820.xlsx
5. Calculate
6. Review Results (eligible lines, excluded LEFT/NOTICE, top-2 selections)
7. Approve
8. Compare Final Approved Cycle against expected-results Excel

AUTHORITATIVE RULES
------------------------------------------------------------------------
Amounts / priority: app/services/incentives/nashik_rules.py
ROLE_PRIORITY: AVP → Associate Director → Senior Manager → Center Head → Manager → CRM → Team Lead → Recruiter
MAX roles per person: 2 (Recruiter is INSIDE the pool — not separate)
NOTICE: not incentive-eligible (Client / In-House / Sambhaji semantics)
LEFT: not incentive-eligible; hierarchy continues for other people
Status is person-level via Coordinator Master (not role-level)

Margin $8 → Recruiter ₹2000 @160h | TL ₹250 | CRM ₹1000 | Manager ₹1500 | Sr Mgr ₹1500 | Assoc Dir ₹1750 | Center Head ₹1500 | AVP ₹2300

SCENARIO EXPECTED RESULTS
------------------------------------------------------------------------
NASH-BR-001 Baseline all ACTIVE
  Every distinct ACTIVE role holder is selected (per-person top-2).
  Recruiter Amit ₹2000; TL Vivek ₹250; CRM David ₹1000;
  Manager Nitin ₹1500; Sr Mgr Rajesh ₹1500; Assoc Dir Nikhil ₹1750;
  Center Head ABC ₹1500; AVP Aisha ₹2300.

NASH-BR-002 Recruiter LEFT
  Recruiter Left → NO incentive. All remaining hierarchy continues.

NASH-BR-003 Manager LEFT
  Manager Left → NO incentive. Recruiter, TL, CRM, and all roles above Manager continue.

NASH-BR-004 Team Lead LEFT
  TL Left → NO incentive. Other eligible roles continue.

NASH-BR-005 CRM LEFT
  CRM Left → NO incentive. Other eligible roles continue.

NASH-BR-006 Multiple LEFT
  Recruiter Left, CRM Left, Manager Left → excluded.
  TL + Senior Manager + Assoc Dir + Center Head + AVP continue.

NASH-BR-007 Nitin = Recruiter + CRM + Manager
  Selected: Manager ₹1500, CRM ₹1000. Recruiter excluded by top-2.

NASH-BR-008 Nitin = Recruiter + Team Lead + Manager
  Selected: Manager ₹1500, Team Lead ₹250. Recruiter excluded by top-2.

NASH-BR-009 Nitin = ALL roles
  Selected: AVP ₹2300, Associate Director ₹1750. Exactly two roles.

NASH-BR-010 Manager LEFT + Nitin Recruiter/CRM
  IMPORTANT: Coordinator status is person-level. Role-specific LEFT for the same
  person while remaining ACTIVE on other roles is not supported by the schema.
  Pack uses Manager Left (LEFT) + Nitin Giri ACTIVE for Recruiter+CRM.
  Expected: Manager excluded; Nitin CRM ₹1000 + Recruiter ₹2000.

NASH-BR-011 AVP LEFT
  AVP Left → NO incentive. Remaining eligible roles continue.

NASH-BR-012 NOTICE
  Notice Employee (Recruiter) → NO incentive (NOTICE not eligible).
  Remaining hierarchy continues.

NASH-BR-013 Zero Hours
  Hours=0 → no payable Nashik incentives (pro-rata 0 / leadership needs 160h).

COLUMN SCHEMAS (application)
------------------------------------------------------------------------
Candidate Master: Start ID, Activity ID, Candidate, Email, ... Team Lead, CRM,
  Team Manager (=Manager), Senior Manager, Associate Director, Director,
  Center Head, Assistant VP (=AVP), Organization, Recruiter Location,
  Start Date, Margin, Recruiter, Status
Status file: Coordinator Name, Email, Organization, Role / Title,
  Employment Status, Exit Date, Bank Name, Account Number, IFSC Code
Hours: Candidate Name, Candidate Start ID, Client Name, Hours Worked, Month

DATA QUALITY
------------------------------------------------------------------------
13 unique Start IDs NASH-BR-001 .. NASH-BR-013
Unique Activity IDs ACT-NASH-BR-00x
Synthetic emails @nash-qa.example.com (not production)
Client = Acme Corp | Work Location = NASHIK | Candidate Location = Nashik
Recruiter Location = Nashik | Organization/Resume Source = Ampcus Inc
Every hierarchy person appears in the status file

