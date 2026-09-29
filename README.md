# Unified MIS & PRISM Backend

This repository unifies **Starts MIS** and **PRISM (Incentive Tracker)** backend services into a single, high-performance, modular FastAPI application.

---

## 🏛 Architecture Overview

```
mis-prism-backend/
├── main.py                    # Unified FastAPI entry point (Lifespan, Common Auth, Dual DB Health)
├── mis/                       # Modular Starts MIS Application
│   ├── api/                   # MIS REST endpoints (/api/v1/mis/* and /api/v1/*)
│   ├── core/                  # MIS Configuration (AsyncPG settings, security)
│   ├── db/                    # Async SQLAlchemy session (connects to mis_db)
│   ├── models/                # MIS SQLAlchemy models (User, Role, Start, Master, etc.)
│   ├── schemas/               # MIS Pydantic schemas
│   ├── services/              # MIS business logic (Email Ingestion, JobDiva, Starts)
│   └── middleware/            # MIS security & CORS handlers
├── prism/                     # Modular PRISM (Incentive Tracker) Application
│   ├── controllers/           # PRISM REST controllers (/api/v1/prism/* and /api/v1/*)
│   ├── core/                  # PRISM DB session (Sync psycopg2 connects to incentive_tracker)
│   ├── models/                # PRISM schemas & DTOs
│   ├── repositories/          # PRISM ORM entities and database operations
│   ├── services/              # PRISM calculation engines (CandidateMatcher, IncentiveRules)
│   ├── security/              # PRISM JWT, CSRF, and security headers
│   └── config.py              # PRISM settings & environment config
├── alembic/                   # MIS database migrations
├── migrations/                # PRISM database migrations
├── sql/                       # Schema scripts
├── requirements.txt           # Unified Python dependencies
└── Dockerfile                 # Production container image
```

---

## 🚀 Key Features

1. **Unified Standalone Database with Schema Separation**:
   - Both **Starts MIS** and **PRISM** connect to a single standalone PostgreSQL database (`mis_prism_db` by default).
   - **Schema `mis`**: Dedicated schema for Starts MIS (AsyncPG async engine, Alembic migrations, candidate starts, approvals, users).
   - **Schema `prism`**: Dedicated schema for PRISM (Psycopg2 sync engine, cycle calculations, hours reconciliation, benchmarks).
   - Prevents table collisions (e.g. `users`, `roles`, `organizations`, `audit_logs`) while enabling seamless future cross-module joins and single-database backups.

2. **Common Authentication Router**:
   - `POST /api/v1/auth/login`: Accepts `{ "email", "password", "app": "mis" | "prism" }` and authenticates against the specified workspace.
   - `POST /api/v1/auth/logout`: Clears both `mis_session` and PRISM `access_token` / `refresh_token` cookies.

3. **Dual API Routing**:
   - **Namespaced Endpoints**:
     - MIS: `/api/v1/mis/...`
     - PRISM: `/api/v1/prism/...`
   - **Backward-Compatible Endpoints**:
     - Key endpoints remain available at `/api/v1/...` so existing integrations and legacy requests continue to function seamlessly.

4. **Unified Health Check**:
   - `GET /health` checks real-time database connectivity for both `mis` and `prism` schemas and returns detailed statuses.

---

## 🛠 Local Setup

### 1. Create Virtual Environment & Install Dependencies

```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Default standalone configuration:
- `DB_NAME=mis_prism_db`
- `MIS_DB_NAME=mis_prism_db`, `MIS_DB_SCHEMA=mis`
- `PRISM_DB_NAME=mis_prism_db`, `PRISM_DB_SCHEMA=prism`

### 3. Create Standalone Database & Tables (Single File)

Create the unified standalone database (`mis_prism_db`) with all schemas, tables, and views:

```bash
python create_db.py
# Or:
python scripts/create_db.py
# Optional reset: python scripts/create_db.py --reset
```

### 4. Seed Test Users & Data (Single File)

Seed test users, roles, organizations, dropdowns, and sample records for both Starts MIS and PRISM:

```bash
python seed_data.py
# Or:
python scripts/seed_data.py
# Options: --mis-only, --prism-only, --reset-passwords
```

### 5. Run the Unified Backend

```bash
python main.py
```
Or via Uvicorn:
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Interactive API documentation will be available at:
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/health](http://localhost:8000/health)
