from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from mis.core.config import settings

# Common Vite / local frontend ports used in development
_DEV_ORIGINS = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://localhost:8080",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8080",
]


def add_cors(app: FastAPI) -> None:
    configured = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    # Merge configured + known local origins (deduped, order preserved)
    origins: list[str] = []
    for origin in configured + _DEV_ORIGINS:
        if origin not in origins:
            origins.append(origin)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
