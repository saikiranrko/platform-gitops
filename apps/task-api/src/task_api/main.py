"""
Task API — enterprise-style FastAPI microservice.
Demonstrates: structured logging, metrics, health probes, secret injection.
"""

import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import PlainTextResponse

# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger("task-api")

# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
REQUEST_COUNT = Counter(
    "task_api_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)
REQUEST_LATENCY = Histogram(
    "task_api_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
)

# ---------------------------------------------------------------------------
# In-memory task store (replace with Azure Cosmos DB / Postgres in production)
# ---------------------------------------------------------------------------
_tasks: dict[str, dict] = {}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    priority: str = Field(default="medium", pattern="^(low|medium|high)$")


class Task(BaseModel):
    id: str
    title: str
    description: Optional[str]
    priority: str
    status: str
    created_at: float


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime_seconds: float


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------
_start_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("task-api starting", extra={"version": "0.1.0"})
    # In production: connect to DB, warm caches, etc.
    yield
    logger.info("task-api shutting down")


app = FastAPI(
    title="Task API",
    description="Demo microservice for platform-gitops",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Middleware: request timing + metrics
# ---------------------------------------------------------------------------
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status_code=response.status_code,
    ).inc()
    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=request.url.path,
    ).observe(duration)
    return response


# ---------------------------------------------------------------------------
# Health probes (Kubernetes liveness + readiness)
# ---------------------------------------------------------------------------
@app.get("/healthz", response_model=HealthResponse, tags=["health"])
async def liveness():
    """Kubernetes liveness probe."""
    return HealthResponse(
        status="ok",
        version="0.1.0",
        uptime_seconds=round(time.time() - _start_time, 2),
    )


@app.get("/readyz", tags=["health"])
async def readiness():
    """Kubernetes readiness probe — add real dependency checks here."""
    return {"status": "ready"}


# ---------------------------------------------------------------------------
# Prometheus scrape endpoint
# ---------------------------------------------------------------------------
@app.get("/metrics", response_class=PlainTextResponse, include_in_schema=False)
async def metrics():
    return PlainTextResponse(
        content=generate_latest().decode("utf-8"),
        media_type=CONTENT_TYPE_LATEST,
    )


# ---------------------------------------------------------------------------
# Task endpoints
# ---------------------------------------------------------------------------
@app.post("/tasks", response_model=Task, status_code=status.HTTP_201_CREATED, tags=["tasks"])
async def create_task(body: TaskCreate):
    task_id = str(uuid.uuid4())
    task = {
        "id": task_id,
        "title": body.title,
        "description": body.description,
        "priority": body.priority,
        "status": "pending",
        "created_at": time.time(),
    }
    _tasks[task_id] = task
    logger.info(f"Task created: {task_id}")
    return task


@app.get("/tasks", response_model=list[Task], tags=["tasks"])
async def list_tasks(priority: Optional[str] = None, status_filter: Optional[str] = None):
    tasks = list(_tasks.values())
    if priority:
        tasks = [t for t in tasks if t["priority"] == priority]
    if status_filter:
        tasks = [t for t in tasks if t["status"] == status_filter]
    return tasks


@app.get("/tasks/{task_id}", response_model=Task, tags=["tasks"])
async def get_task(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    return task


@app.patch("/tasks/{task_id}/complete", response_model=Task, tags=["tasks"])
async def complete_task(task_id: str):
    task = _tasks.get(task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    task["status"] = "done"
    logger.info(f"Task completed: {task_id}")
    return task


@app.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["tasks"])
async def delete_task(task_id: str):
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    del _tasks[task_id]
    logger.info(f"Task deleted: {task_id}")
