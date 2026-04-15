"""Mini Orchestrator — FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.engine.event_bus import EventBus
from backend.routes import artifacts as artifacts_routes
from backend.routes import chat as chat_routes
from backend.routes import events as events_routes
from backend.routes import projects as projects_routes


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    app.state.event_bus = EventBus()
    yield


app = FastAPI(title="Mini Orchestrator", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(projects_routes.router)
app.include_router(artifacts_routes.router)
app.include_router(events_routes.router)
app.include_router(chat_routes.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}
