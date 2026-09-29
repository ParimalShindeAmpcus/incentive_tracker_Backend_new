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

1. **Dual Database Connections**:
   - **MIS Services** connect asynchronously (`asyncpg`) to `MIS_DB_NAME` (default: `mis_db`).
   - **PRISM Services** connect synchronously (`psycopg2`) to `PRISM_DB_NAME` (default: `incentive_tracker`).
   - Tables and business logic remain completely isolated without cross-database interference.

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
   - `GET /health` checks real-time database connectivity for both `mis` and `prism` databases and returns detailed statuses.

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

Set your database credentials:
- `MIS_DB_USER`, `MIS_DB_PASSWORD`, `MIS_DB_NAME`
- `PRISM_DB_USER`, `PRISM_DB_PASSWORD`, `PRISM_DB_NAME`

### 3. Run the Unified Backend

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
