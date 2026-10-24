"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db import init_db
from app.routes import auth, chat, portfolio, push


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="CommonWatt", lifespan=lifespan)

# Allow the Vite dev server (web/, port 5173) to call the API from the
# browser. Override COMMONWATT_CORS_ORIGINS (comma-separated) in deploy.
import os
_origins = os.environ.get(
    "COMMONWATT_CORS_ORIGINS",
    "http://127.0.0.1:5173,http://localhost:5173",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(push.router)
app.include_router(portfolio.router)


@app.get("/health")
def health():
    from server.data import load_buildings
    return {"status": "ok", "buildings": len(load_buildings())}
