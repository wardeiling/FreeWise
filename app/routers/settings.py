from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func
from pydantic import BaseModel

from app.db import get_engine
from app.models import Settings, Highlight


router = APIRouter(prefix="/settings", tags=["settings"])
templates = Jinja2Templates(directory="app/templates")


def get_session():
    """Dependency to provide database session."""
    engine = get_engine()
    with Session(engine) as session:
        yield session


def get_settings(session: Session) -> Settings:
    """Helper function to get the settings record."""
    statement = select(Settings)
    settings = session.exec(statement).first()
    if not settings:
        # Create default settings if none exist
        settings = Settings()
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


class SettingsUpdate(BaseModel):
    """Request model for updating settings."""
    daily_review_count: Optional[int] = None
    default_sort: Optional[str] = None
    theme: Optional[str] = None


# ============ JSON API Endpoints ============

@router.get("/", response_model=Settings)
def get_settings_api(session: Session = Depends(get_session)):
    """Return application settings as JSON."""
    return get_settings(session)


@router.put("/", response_model=Settings)
def update_settings_api(
    settings_data: SettingsUpdate,
    session: Session = Depends(get_session)
):
    """Update application settings via JSON."""
    settings = get_settings(session)
    
    if settings_data.daily_review_count is not None:
        settings.daily_review_count = settings_data.daily_review_count
    if settings_data.default_sort is not None:
        settings.default_sort = settings_data.default_sort
    if settings_data.theme is not None:
        settings.theme = settings_data.theme
    
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings


# ============ HTML/HTMX Endpoints ============

@router.get("/ui", response_class=HTMLResponse)
async def ui_settings(
    request: Request,
    session: Session = Depends(get_session)
):
    """Render settings page with form."""
    settings = get_settings(session)
    highlights_count_stmt = select(func.count(Highlight.id))
    highlights_count = session.exec(highlights_count_stmt).one()
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": settings,
        "highlights_count": highlights_count
    })


@router.post("/ui", response_class=HTMLResponse)
async def update_settings_ui(
    request: Request,
    daily_review_count: int = Form(...),
    theme: str = Form(...),
    session: Session = Depends(get_session)
):
    """Update settings from form submission."""
    settings = get_settings(session)
    
    settings.daily_review_count = daily_review_count
    settings.theme = theme
    
    session.add(settings)
    session.commit()
    session.refresh(settings)
    
    highlights_count_stmt = select(func.count(Highlight.id))
    highlights_count = session.exec(highlights_count_stmt).one()
    
    # Return updated form with success message
    return templates.TemplateResponse("settings.html", {
        "request": request,
        "settings": settings,
        "highlights_count": highlights_count,
        "success_message": "Settings saved successfully!"
    })
