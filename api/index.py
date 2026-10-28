"""Vercel Serverless Function entry point for FastAPI backend."""

import sys
from pathlib import Path

# Add project root to sys.path so 'backend' package is importable
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Ensure database path is resolved relative to repository root on Vercel
from backend.config import settings
settings.db_path = str(ROOT_DIR / "data" / "bmrs_cache.db")

from backend.main import app

# Vercel's Python runtime automatically detects the ASGI 'app'
