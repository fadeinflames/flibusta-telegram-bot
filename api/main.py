"""FastAPI application — serves API and static frontend."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.routers import audiobooks, books, downloads, library, profile, search
from src import database as db


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_database()
    yield


app = FastAPI(title="Flibusta WebApp API", lifespan=lifespan)

# CORS for development (Vite dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(library.router)
app.include_router(search.router)
app.include_router(books.router)
app.include_router(downloads.router)
app.include_router(profile.router)
app.include_router(audiobooks.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve frontend static files in production
web_dist = Path(__file__).parent.parent / "web" / "dist"
if web_dist.exists():
    app.mount("/", StaticFiles(directory=str(web_dist), html=True), name="frontend")
