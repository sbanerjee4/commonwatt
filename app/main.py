"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db
from app.routes import chat, sms


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="CommonWatt SMS", lifespan=lifespan)
app.include_router(sms.router)
app.include_router(chat.router)
