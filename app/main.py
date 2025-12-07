import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.db import get_engine
from app.models import SQLModel
from app.routers import highlights

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create database tables on startup."""
    os.makedirs("./db", exist_ok=True)
    os.makedirs("./app/static", exist_ok=True)
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    yield


app = FastAPI(title="FreeWise", lifespan=lifespan)

# Setup templates and static files
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Include routers
app.include_router(highlights.router)


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    """Root endpoint returning simple HTML."""
    return templates.TemplateResponse("base.html", {
        "request": request,
    })
