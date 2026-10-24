"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db
from app.routes import chat, portfolio, push, sms


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="CommonWatt", lifespan=lifespan)
app.include_router(sms.router)
app.include_router(chat.router)
app.include_router(push.router)
app.include_router(portfolio.router)


@app.get("/health")
def health():
    from server.data import load_buildings
    return {"status": "ok", "buildings": len(load_buildings())}
