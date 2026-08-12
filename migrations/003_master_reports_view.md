# Migration 003 — Master Reports View

Creates a SQL View `master_reports_view` to simplify and centralize the join logic for the reports page.

## PostgreSQL one-time script

Run against the database to create or replace the view:

```sql
CREATE OR REPLACE VIEW master_reports_view AS
SELECT
    il.id AS line_id,
    il.person AS person,
    il.role AS role,
    il.candidate_name AS line_candidate_name,
    il.amount AS amount,
    il.hours AS hours,
    il.margin AS line_margin,
    il.incentive_type AS incentive_type,
    il.eligible AS eligible,
    
    ic.id AS cycle_id,
    ic.name AS cycle_name,
    ic.division AS division,
    ic.incentive_month AS incentive_month,
    ic.status AS cycle_status,
    
    c.external_candidate_id AS external_candidate_id,
    c.candidate_name AS candidate_name,
    c.start_date AS start_date,
    c.contract_type AS contract_type,
    c.candidate_source AS candidate_source,
    c.organization AS organization,
    c.margin AS candidate_margin,
    c.crm AS crm,
    c.center_head AS center_head,
    c.associate_director AS associate_director,
    c.manager AS manager,
    c.senior_manager AS senior_manager,
    c.team_lead AS team_lead
FROM incentive_lines il
JOIN incentive_cycles ic ON ic.id = il.cycle_id
LEFT JOIN candidates c ON c.id = il.candidate_id;
```
