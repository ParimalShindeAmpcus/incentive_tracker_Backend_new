-- Optional manual PostgreSQL bootstrap.
-- Prefer: python scripts/create_db.py
--
--   psql -U postgres -f scripts/create_database.sql

SELECT 'CREATE DATABASE incentive_tracker'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'incentive_tracker')\gexec
