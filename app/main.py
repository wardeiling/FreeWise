import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlmodel import Session

from app.db import get_engine, get_settings, get_current_streak
from app.models import SQLModel
from app.routers import highlights, settings, importer, library, dashboard, export

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup."""
    os.makedirs("./db", exist_ok=True)
    os.makedirs("./app/static", exist_ok=True)
    os.makedirs("./app/static/uploads/covers", exist_ok=True)
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    
    # Initialize default settings if not exists
    from sqlmodel import Session
    with Session(engine) as session:
        get_settings(session)
    
    yield


app = FastAPI(title="FreeWise", lifespan=lifespan)


@app.middleware("http")
async def inject_streak(request: Request, call_next):
    """Attach the current review streak to request.state for every rendered page.

    Skips static assets and the service worker to avoid unnecessary DB queries.
    The value is always set (defaults to 0) so templates can rely on it.
    """
    request.state.streak = 0
    path = request.url.path
    if not path.startswith("/static") and path not in ("/sw.js", "/favicon.ico"):
        try:
            with Session(get_engine()) as s:
                request.state.streak = get_current_streak(s)
        except Exception:
            pass
    return await call_next(request)


# Setup templates and static files
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(dashboard.router)
app.include_router(highlights.router)
app.include_router(settings.router)
app.include_router(importer.router)
app.include_router(library.router)
app.include_router(export.router)


@app.get("/sw.js")
async def service_worker():
    """Serve the PWA service worker from root scope.
    
    Must be served with Cache-Control: no-store so browsers always fetch the
    latest version — otherwise SW updates are silently skipped for hours.
    """
    from fastapi.responses import FileResponse
    from fastapi import Response
    response = FileResponse("app/static/sw.js", media_type="application/javascript")
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/favicon.ico")
async def favicon():
    """Serve favicon from root path (browsers always request it here)."""
    from fastapi.responses import FileResponse
    return FileResponse("app/static/favicons/favicon.ico", media_type="image/x-icon")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root endpoint redirects to dashboard."""
    return RedirectResponse(url="/dashboard/ui", status_code=302)
