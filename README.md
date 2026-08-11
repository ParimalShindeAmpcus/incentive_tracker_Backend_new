# Incentive Tracker Backend

Layered FastAPI backend: **controllers → services → repositories → DB**.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Set DB_USER / DB_PASSWORD / DB_NAME

python scripts/create_db.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Health: http://127.0.0.1:8000/health  
- Docs: http://127.0.0.1:8000/api/v1/docs  
- Admin (seeded): `admin@example.com` / `Admin@123`

## Structure

| Layer | Path |
|-------|------|
| ORM tables | `app/repositories/entities/` (28 tables) |
| Pydantic DTOs | `app/models/<feature>/schemas.py` |
| Persistence | `app/repositories/<feature>/` |
| Business logic | `app/services/<feature>/` |
| HTTP routes | `app/controllers/<feature>/` |

See [docs/repo_overview.md](docs/repo_overview.md) and [migrations/001_initial.md](migrations/001_initial.md).

## Features under `/api/v1`

auth · organization · candidates · recruiter-master · hours-data · hours-benchmarks · project-end · cycles · incentive-slabs · payments · audit · vlookup

## Docker

```bash
docker build -t incentive-tracker-api .
docker run --env-file .env -p 8000:8000 incentive-tracker-api
```
