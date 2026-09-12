"""Nura API application entry point.

Run it locally with::

    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

``--host 0.0.0.0`` matters: a phone on your Wi-Fi cannot reach a server bound
only to localhost.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.api.v1 import router as v1
from app.core.config import API_VERSION, get_settings
from app.core.logging import configure_logging

settings = get_settings()
configure_logging(development=settings.is_development)

app = FastAPI(
    title="Nura API",
    version=API_VERSION,
    summary="Backend for the Nura health companion.",
)

# Native builds do not use CORS at all. This exists so the Expo web target can
# reach the API during development. In production, only origins that were
# explicitly configured are allowed -- never "*".
allowed_origins = settings.cors_origins
if settings.is_development and not allowed_origins:
    # Expo picks its dev-server port dynamically, so pin nothing locally.
    allowed_origins = ["*"]

if allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(health.router)
app.include_router(v1.router)
