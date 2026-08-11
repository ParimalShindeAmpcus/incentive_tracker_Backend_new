# Repository overview

Layered FastAPI backend. Request flow is always:

```text
controllers → services → repositories → DB
```

## Packages

| Path | Role |
|------|------|
| `app/main.py` | App factory, lifespan, CORS, router registration |
| `app/config.py` | Settings from environment only |
| `app/controllers/<feature>/` | HTTP routes only (thin) |
| `app/services/<feature>/` | Business logic / orchestration |
| `app/services/common/` | Shared cross-feature helpers |
| `app/repositories/<feature>/` | DB / persistence only |
| `app/models/<feature>/schemas.py` | Pydantic request/response DTOs |
| `app/core/` | Shared infra (db, logging, cache, json) |
| `app/llm/` | Optional LLM provider abstraction |
| `app/security/` | Optional guardrails / auth helpers |
| `migrations/` | SQL schema migrations |
| `scripts/` | One-off scripts (e.g. create DB) |
| `tests/` | pytest unit + integration |
| `docs/` | Architecture notes |

## Feature rule

One feature = same folder name under `controllers/`, `services/`, `models/`, and `repositories/`.

Example wired today: **health**

- `GET /health` → `controllers/health` → `services/health` → `repositories/health`
