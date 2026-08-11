# Repository overview

Layered FastAPI backend. Request flow is always:

```text
controllers → services → repositories → DB (entities)
```

## Packages

| Path | Role |
|------|------|
| `app/main.py` | App factory, lifespan, CORS, router registration |
| `app/config.py` | Settings from environment only |
| `app/controllers/<feature>/` | HTTP routes only (thin) |
| `app/services/<feature>/` | Business logic / orchestration |
| `app/services/common/` | Shared deps, seed |
| `app/repositories/<feature>/` | DB queries |
| `app/repositories/entities/` | SQLAlchemy ORM table models (28 tables) |
| `app/models/<feature>/schemas.py` | Pydantic request/response DTOs |
| `app/core/` | Shared infra (db, logging, cache, json) |
| `app/llm/` | Optional LLM provider abstraction |
| `app/security/` | JWT / password / guardrail stubs |
| `migrations/` | Schema notes |
| `scripts/` | `create_db.py` |
| `tests/` | pytest unit + integration |
| `docs/` | Architecture notes |

## Feature rule

One feature = same folder name under `controllers/`, `services/`, `models/`, and `repositories/` (plus shared `entities/` for ORM).

## Domains wired

health · auth · organization · candidates · recruiters · hours · project_end · cycles · incentives · audit · vlookup · reports
