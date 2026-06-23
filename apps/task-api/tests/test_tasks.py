"""Unit tests for Task API."""

import pytest
from httpx import AsyncClient, ASGITransport

from task_api.main import app, _tasks


@pytest.fixture(autouse=True)
def clear_tasks():
    """Reset in-memory store between tests."""
    _tasks.clear()
    yield
    _tasks.clear()


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


async def test_health_liveness(client):
    r = await client.get("/healthz")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "version" in data


async def test_health_readiness(client):
    r = await client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


async def test_create_task(client):
    r = await client.post("/tasks", json={"title": "Deploy to AKS", "priority": "high"})
    assert r.status_code == 201
    data = r.json()
    assert data["title"] == "Deploy to AKS"
    assert data["priority"] == "high"
    assert data["status"] == "pending"
    assert "id" in data


async def test_list_tasks_empty(client):
    r = await client.get("/tasks")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_tasks_filter_priority(client):
    await client.post("/tasks", json={"title": "Low priority task", "priority": "low"})
    await client.post("/tasks", json={"title": "High priority task", "priority": "high"})

    r = await client.get("/tasks?priority=high")
    assert r.status_code == 200
    tasks = r.json()
    assert len(tasks) == 1
    assert tasks[0]["priority"] == "high"


async def test_get_task(client):
    create_r = await client.post("/tasks", json={"title": "Test task"})
    task_id = create_r.json()["id"]

    r = await client.get(f"/tasks/{task_id}")
    assert r.status_code == 200
    assert r.json()["id"] == task_id


async def test_get_task_not_found(client):
    r = await client.get("/tasks/nonexistent-id")
    assert r.status_code == 404


async def test_complete_task(client):
    create_r = await client.post("/tasks", json={"title": "Finish me"})
    task_id = create_r.json()["id"]

    r = await client.patch(f"/tasks/{task_id}/complete")
    assert r.status_code == 200
    assert r.json()["status"] == "done"


async def test_delete_task(client):
    create_r = await client.post("/tasks", json={"title": "Delete me"})
    task_id = create_r.json()["id"]

    r = await client.delete(f"/tasks/{task_id}")
    assert r.status_code == 204

    r2 = await client.get(f"/tasks/{task_id}")
    assert r2.status_code == 404


async def test_metrics_endpoint(client):
    r = await client.get("/metrics")
    assert r.status_code == 200
    assert "task_api_requests_total" in r.text


async def test_invalid_priority(client):
    r = await client.post("/tasks", json={"title": "Bad task", "priority": "urgent"})
    assert r.status_code == 422  # validation error
