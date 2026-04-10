"""FastAPI application — serves API and static frontend."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.deps import CurrentUser
from api.routers import auth_router, audiobooks, books, downloads, library, profile, search
from src import database as db
from src import rt_cache

logger = logging.getLogger(__name__)

CACHE_CLEANUP_INTERVAL = 24 * 3600  # 24 hours


async def _cache_cleanup_loop():
    """Background task: clean expired cache entries once per day."""
    while True:
        await asyncio.sleep(CACHE_CLEANUP_INTERVAL)
        try:
            deleted = await asyncio.to_thread(rt_cache.cleanup_expired)
            if deleted:
                logger.info("Cache cleanup: removed %d expired entries", deleted)
        except Exception as e:
            logger.warning("Cache cleanup error: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_database()
    rt_cache.init_cache_table()
    # Run initial cleanup on startup
    deleted = rt_cache.cleanup_expired()
    if deleted:
        logger.info("Startup cache cleanup: removed %d expired entries", deleted)
    # Start background cleanup loop
    cleanup_task = asyncio.create_task(_cache_cleanup_loop())
    yield
    cleanup_task.cancel()


app = FastAPI(title="Flibusta WebApp API", lifespan=lifespan)

# CORS — restrict in production, allow all in dev
_cors_origins = os.getenv("CORS_ORIGINS", "").strip()
_allowed_origins = [o.strip() for o in _cors_origins.split(",") if o.strip()] if _cors_origins else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routers
app.include_router(auth_router.router)
app.include_router(library.router)
app.include_router(search.router)
app.include_router(books.router)
app.include_router(downloads.router)
app.include_router(profile.router)
app.include_router(audiobooks.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.post("/api/cache/cleanup")
async def cache_cleanup(user: CurrentUser):
    """Manually trigger cache cleanup (remove expired entries). Requires auth."""
    deleted = await asyncio.to_thread(rt_cache.cleanup_expired)
    stats = await asyncio.to_thread(rt_cache.get_stats)
    return {"deleted": deleted, **stats}


@app.delete("/api/cache")
async def cache_clear(user: CurrentUser):
    """Clear entire cache. Requires auth."""
    cleared = await asyncio.to_thread(rt_cache.clear_all)
    return {"cleared": cleared}


# Serve frontend static files in production
web_dist = Path(__file__).parent.parent / "web" / "dist"
if web_dist.exists():
    # Serve static assets (JS, CSS, images)
    app.mount("/assets", StaticFiles(directory=str(web_dist / "assets")), name="assets")

    # SPA fallback: any non-API path → index.html
    @app.get("/{full_path:path}")
    async def spa_fallback(request: Request, full_path: str):
        return FileResponse(str(web_dist / "index.html"))
