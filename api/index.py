"""Vercel ASGI entrypoint — exposes the FastAPI app from app.main."""
from app.main import app  # noqa: E402,F401

handler = app
