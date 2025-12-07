from typing import Optional
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func

from app.db import get_engine
from app.models import Book, Highlight, Settings


router = APIRouter(prefix="/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")


def get_session():
    """Dependency to provide database session."""
    engine = get_engine()
    with Session(engine) as session:
        yield session


@router.get("/ui", response_class=HTMLResponse)
async def ui_dashboard(
    request: Request,
    session: Session = Depends(get_session)
):
    """
    Render dashboard page with statistics overview.
    """
    # Get settings for theme
    settings_stmt = select(Settings)
    settings = session.exec(settings_stmt).first()
    
    # Get total books count
    books_count_stmt = select(func.count(Book.id))
    total_books = session.exec(books_count_stmt).one()
    
    # Get total highlights count
    highlights_count_stmt = select(func.count(Highlight.id))
    total_highlights = session.exec(highlights_count_stmt).one()
    
    # Get total favorited highlights
    favorited_stmt = select(func.count(Highlight.id)).where(
        (Highlight.favorite == True) | (Highlight.is_favorited == True)
    )
    total_favorited = session.exec(favorited_stmt).one()
    
    # Get total discarded highlights
    discarded_stmt = select(func.count(Highlight.id)).where(
        Highlight.is_discarded == True
    )
    total_discarded = session.exec(discarded_stmt).one()
    
    # Calculate active highlights (not discarded)
    active_highlights = total_highlights - total_discarded
    
    # Calculate percentages for visualization
    favorited_percentage = (total_favorited / total_highlights * 100) if total_highlights > 0 else 0
    discarded_percentage = (total_discarded / total_highlights * 100) if total_highlights > 0 else 0
    active_percentage = (active_highlights / total_highlights * 100) if total_highlights > 0 else 0
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "settings": settings,
        "total_books": total_books,
        "total_highlights": total_highlights,
        "total_favorited": total_favorited,
        "total_discarded": total_discarded,
        "active_highlights": active_highlights,
        "favorited_percentage": favorited_percentage,
        "discarded_percentage": discarded_percentage,
        "active_percentage": active_percentage
    })
