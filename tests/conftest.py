from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.api.config import Settings
from backend.api.services.container import build_services


class Clock:
    """A clock tests can push forward, e.g. past an approval's expiry."""

    def __init__(self):
        self.offset = timedelta(0)

    def __call__(self) -> datetime:
        return datetime.now(timezone.utc) + self.offset

    def advance(self, **kwargs) -> None:
        self.offset += timedelta(**kwargs)


class Harness:
    def __init__(self, client, services, clock, workspace):
        self.client = client
        self.services = services
        self.clock = clock
        self.workspace = workspace

    def project(self, name="Blog") -> int:
        response = self.client.post("/api/projects", json={"name": name})
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def chat(self, project_id: int, message="Create a blog", **kwargs):
        return self.client.post(
            "/api/chat", json={"project_id": project_id, "message": message}, **kwargs
        )

    def project_dir(self, project_id: int):
        return self.workspace / ("project_%d" % project_id)


@pytest.fixture
def make_app(tmp_path):
    def build(agent=None, executor=None, **settings) -> Harness:
        options = {"workspace_root": tmp_path / "workspaces", "rate_limit_per_minute": 0}
        options.update(settings)
        clock = Clock()
        services = build_services(Settings(**options), agent=agent, executor=executor, clock=clock)
        client = TestClient(create_app(services), raise_server_exceptions=False)
        return Harness(client, services, clock, tmp_path / "workspaces")

    return build
