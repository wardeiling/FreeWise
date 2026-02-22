import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import get_engine, get_settings
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
    """Serve the PWA service worker from root scope."""
    from fastapi.responses import FileResponse
    return FileResponse("app/static/sw.js", media_type="application/javascript")


@app.get("/favicon.ico")
async def favicon():
    """Serve favicon from root path (browsers always request it here)."""
    from fastapi.responses import FileResponse
    return FileResponse("app/static/favicons/favicon.ico", media_type="image/x-icon")


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root endpoint redirects to dashboard."""
    return RedirectResponse(url="/dashboard/ui", status_code=302)
