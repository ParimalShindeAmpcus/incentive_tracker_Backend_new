# Incentive Tracker Backend

Layered FastAPI scaffold. Controllers stay thin; business logic lives in services; SQL/persistence lives in repositories.

## Quick start

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env

# Create PostgreSQL database (tables/migrations later)
python scripts/create_db.py

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health check: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

## Structure

See [docs/repo_overview.md](docs/repo_overview.md).

```text
app/
  main.py
  config.py
  controllers/<feature>/controller.py
  services/<feature>/*_service.py
  repositories/<feature>/*_repository.py
  models/<feature>/schemas.py
  core/
  llm/
  security/
migrations/
scripts/          # create_db.py
tests/
docs/
```

## Architecture rules

1. Request flow: controllers → services → repositories → DB  
2. Controllers: no business logic, no raw SQL  
3. Services: no HTTP; call repositories (+ llm/security as needed)  
4. Repositories own all persistence  
5. Models = Pydantic DTOs per feature  
6. Config from environment only  

## Docker

```bash
docker build -t incentive-tracker-api .
docker run --env-file .env -p 8000:8000 incentive-tracker-api
```
