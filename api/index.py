"""Vercel serverless entry point.

Vercel's @vercel/python runtime serves any module-level ASGI `app`, so this
file just re-exports the FastAPI app. All routes are rewritten here via
vercel.json.
"""
import sys
from pathlib import Path

# api/ lives one level below the repo root; make the `app` package importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app  # noqa: E402,F401
