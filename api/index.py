"""Vercel serverless entrypoint: exposes the Flask app from backend/ as `app`."""
import os
import sys

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend")
sys.path.insert(0, os.path.normpath(BACKEND))

from app import create_app  # noqa: E402

app = create_app()
