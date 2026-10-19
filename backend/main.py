"""ASGI entry point. From the repository root:

    uvicorn backend.main:app --reload

Sprint 1 uses the fake agent with mock execution and storage. To integrate a real
module, pass it to build_services (see backend/api/services/container.py).
"""
from backend.api.app import create_app

app = create_app()
