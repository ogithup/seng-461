"""ASGI entry point. From the repository root:

    uvicorn backend.main:app --reload

Sprint 2 uses the fake agent with SQLite storage (DATABASE_PATH) and mock execution. To integrate a real
module, pass it to build_services (see backend/api/services/container.py).
"""
from backend.api.app import create_app

app = create_app()
