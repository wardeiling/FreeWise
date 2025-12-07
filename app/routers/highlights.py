from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func
from pydantic import BaseModel

from app.db import get_engine
from app.models import Highlight, Settings


router = APIRouter(prefix="/highlights", tags=["highlights"])
templates = Jinja2Templates(directory="app/templates")


def get_session():
    """Dependency to provide database session."""
    engine = get_engine()
    with Session(engine) as session:
        yield session


class HighlightCreate(BaseModel):
    """Request model for creating a highlight."""
    text: str
    source: Optional[str] = None
    next_review: Optional[datetime] = None
    user_id: int = 1  # Default to user 1 for single-user mode


class HighlightUpdate(BaseModel):
    """Request model for updating a highlight."""
    text: Optional[str] = None
    source: Optional[str] = None
    next_review: Optional[datetime] = None


class FavoriteToggle(BaseModel):
    """Request model for toggling favorite status."""
    favorite: bool


@router.post("/", response_model=Highlight)
def create_highlight(
    highlight_data: HighlightCreate,
    session: Session = Depends(get_session)
):
    """Create a new highlight."""
    highlight = Highlight(
        text=highlight_data.text,
        source=highlight_data.source,
        next_review=highlight_data.next_review,
        user_id=highlight_data.user_id
    )
    session.add(highlight)
    session.commit()
    session.refresh(highlight)
    return highlight


@router.get("/", response_model=List[Highlight])
def list_highlights(
    status: Optional[str] = None,
    limit: Optional[int] = None,
    session: Session = Depends(get_session)
):
    """List highlights with optional filtering by status and limit."""
    statement = select(Highlight).order_by(Highlight.created_at.desc())
    
    if status:
        statement = statement.where(Highlight.status == status)
    
    if limit:
        statement = statement.limit(limit)
    
    highlights = session.exec(statement).all()
    return highlights


@router.get("/{id}", response_model=Highlight)
def get_highlight(id: int, session: Session = Depends(get_session)):
    """Fetch a single highlight by ID."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    return highlight


@router.put("/{id}", response_model=Highlight)
def update_highlight(
    id: int,
    highlight_data: HighlightUpdate,
    session: Session = Depends(get_session)
):
    """Update a highlight's text, source, or next_review."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    if highlight_data.text is not None:
        highlight.text = highlight_data.text
    if highlight_data.source is not None:
        highlight.source = highlight_data.source
    if highlight_data.next_review is not None:
        highlight.next_review = highlight_data.next_review
    
    highlight.updated_at = datetime.utcnow()
    session.add(highlight)
    session.commit()
    session.refresh(highlight)
    return highlight


@router.post("/{id}/favorite/json", response_model=Highlight)
def toggle_favorite(
    id: int,
    favorite_data: FavoriteToggle,
    session: Session = Depends(get_session)
):
    """Toggle favorite status of a highlight (JSON API)."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    highlight.favorite = favorite_data.favorite
    highlight.updated_at = datetime.utcnow()
    session.add(highlight)
    session.commit()
    session.refresh(highlight)
    return highlight


@router.post("/{id}/discard/json", response_model=Highlight)
def discard_highlight(id: int, session: Session = Depends(get_session)):
    """Mark a highlight as discarded (JSON API)."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    highlight.status = "discarded"
    highlight.updated_at = datetime.utcnow()
    session.add(highlight)
    session.commit()
    session.refresh(highlight)
    return highlight


@router.get("/review/", response_model=List[Highlight])
def get_review_highlights(
    n: Optional[int] = None,
    session: Session = Depends(get_session)
):
    """
    Return up to n highlights for review.
    
    If n is not provided, uses Settings.daily_review_count.
    
    Priority order:
    1. Active highlights with next_review <= now or next_review is NULL
    2. Fill remaining slots with random active highlights
    """
    # Load n from settings if not provided
    if n is None:
        settings_stmt = select(Settings)
        settings = session.exec(settings_stmt).first()
        n = settings.daily_review_count if settings else 5
    
    now = datetime.utcnow()
    
    # Get highlights due for review
    due_statement = (
        select(Highlight)
        .where(Highlight.status == "active")
        .where(
            (Highlight.next_review <= now) | (Highlight.next_review == None)
        )
        .order_by(Highlight.next_review.asc())
        .limit(n)
    )
    due_highlights = list(session.exec(due_statement).all())
    
    # If we have fewer than n, fill with random active highlights
    if len(due_highlights) < n:
        remaining = n - len(due_highlights)
        due_ids = [h.id for h in due_highlights]
        
        random_statement = (
            select(Highlight)
            .where(Highlight.status == "active")
            .where(Highlight.next_review > now)
        )
        
        if due_ids:
            random_statement = random_statement.where(Highlight.id.not_in(due_ids))
        
        random_statement = random_statement.order_by(func.random()).limit(remaining)
        random_highlights = list(session.exec(random_statement).all())
        due_highlights.extend(random_highlights)
    
    return due_highlights


# ============ HTML/HTMX Endpoints ============

@router.get("/ui/review", response_class=HTMLResponse)
async def ui_review(
    request: Request,
    session: Session = Depends(get_session)
):
    """Render HTML page with highlights for review."""
    # Get settings for theme and daily review count
    settings_stmt = select(Settings)
    settings = session.exec(settings_stmt).first()
    
    # Use daily_review_count from settings
    n = settings.daily_review_count if settings else 5
    highlights = get_review_highlights(n=n, session=session)
    
    return templates.TemplateResponse("review.html", {
        "request": request,
        "highlights": highlights,
        "n": n,
        "settings": settings
    })


@router.get("/{id}/view", response_class=HTMLResponse)
async def view_highlight_partial(
    request: Request,
    id: int,
    session: Session = Depends(get_session)
):
    """Return HTML partial for a single highlight (read-only view)."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    return templates.TemplateResponse("_highlight_row.html", {
        "request": request,
        "highlight": highlight
    })


@router.get("/{id}/edit", response_class=HTMLResponse)
async def edit_highlight_form(
    request: Request,
    id: int,
    session: Session = Depends(get_session)
):
    """Return HTML form fragment for editing a highlight."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    return templates.TemplateResponse("_highlight_edit.html", {
        "request": request,
        "highlight": highlight
    })


@router.post("/{id}/edit", response_class=HTMLResponse)
async def save_highlight_edit(
    request: Request,
    id: int,
    text: str = Form(...),
    source: Optional[str] = Form(None),
    session: Session = Depends(get_session)
):
    """Accept form submission and return updated highlight partial."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    highlight.text = text
    highlight.source = source if source else None
    highlight.updated_at = datetime.utcnow()
    
    session.add(highlight)
    session.commit()
    session.refresh(highlight)
    
    return templates.TemplateResponse("_highlight_row.html", {
        "request": request,
        "highlight": highlight
    })


@router.post("/{id}/favorite", response_class=HTMLResponse)
async def toggle_favorite_html(
    request: Request,
    id: int,
    favorite: bool = Form(...),
    session: Session = Depends(get_session)
):
    """Toggle favorite status and return updated highlight partial."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    highlight.favorite = favorite
    highlight.updated_at = datetime.utcnow()
    session.add(highlight)
    session.commit()
    session.refresh(highlight)
    
    return templates.TemplateResponse("_highlight_row.html", {
        "request": request,
        "highlight": highlight
    })


@router.post("/{id}/discard", response_class=HTMLResponse)
async def discard_highlight_html(
    request: Request,
    id: int,
    session: Session = Depends(get_session)
):
    """Mark highlight as discarded and return empty div."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    highlight.status = "discarded"
    highlight.updated_at = datetime.utcnow()
    session.add(highlight)
    session.commit()
    
    # Return empty div to remove the highlight from view
    return HTMLResponse(content=f'<div id="highlight-{id}" style="display:none;"></div>')

