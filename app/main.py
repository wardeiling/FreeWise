import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import get_engine
from app.models import SQLModel, Settings
from app.routers import highlights, settings, importer

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup."""
    os.makedirs("./db", exist_ok=True)
    os.makedirs("./app/static", exist_ok=True)
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    
    # Initialize default settings if not exists
    from sqlmodel import Session, select
    with Session(engine) as session:
        statement = select(Settings)
        existing_settings = session.exec(statement).first()
        if not existing_settings:
            default_settings = Settings()
            session.add(default_settings)
            session.commit()
    
    yield


app = FastAPI(title="FreeWise", lifespan=lifespan)

# Setup templates and static files
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(highlights.router)
app.include_router(settings.router)
app.include_router(importer.router)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root endpoint returning simple HTML."""
    from sqlmodel import Session, select
    engine = get_engine()
    with Session(engine) as session:
        statement = select(Settings)
        settings = session.exec(statement).first()
    
    return templates.TemplateResponse("base.html", {
        "request": request,
        "settings": settings,
    })
