"""Compatibility wrapper for older uvicorn web.app:app invocations.

The real FastAPI application now lives in src.api.app so the project follows the
DSA-style src/api + src/services layout.
"""
from src.api.app import app

__all__ = ["app"]
