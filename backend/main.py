"""ASGI entry point. From the repository root:

    uvicorn backend.main:app --reload

Sprint 1 runs on mocks for the agent, execution and storage modules. To integrate a real
module, pass it to build_services (see backend/api/services/container.py).
"""
from backend.api.app import create_app

app = create_app()
