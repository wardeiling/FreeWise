from datetime import datetime, timedelta
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


def render_book_highlights_sections(request: Request, book_id: int, session: Session) -> HTMLResponse:
    """
    Helper function to render both active and discarded highlights sections.
    Returns HTML for both containers.
    """
    # Get all highlights for this book, ordered by location if available, then by date
    # Order: location ASC (if available), created_at DESC (for fallback)
    highlights_stmt = (
        select(Highlight)
        .where(Highlight.book_id == book_id)
        .order_by(
            Highlight.location.asc().nullslast(),  # Location first (page/order), nulls last
            Highlight.created_at.desc()             # Then by date
        )
    )
    highlights = session.exec(highlights_stmt).all()
    
    # Split into active and discarded
    active_highlights = [h for h in highlights if not h.is_discarded]
    discarded_highlights = [h for h in highlights if h.is_discarded]
    
    # Render the sections template
    return templates.TemplateResponse("_book_highlights_sections.html", {
        "request": request,
        "active_highlights": active_highlights,
        "discarded_highlights": discarded_highlights
    })


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

    # Block favoriting discarded highlights
    if favorite_data.favorite and highlight.is_discarded:
        raise HTTPException(status_code=400, detail="Cannot favorite a discarded highlight. Restore it first.")
    
    highlight.favorite = favorite_data.favorite
    highlight.is_favorited = favorite_data.favorite  # keep alias in sync
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

    # Prevent discarding favorites
    if highlight.favorite or getattr(highlight, "is_favorited", False):
        raise HTTPException(status_code=400, detail="Cannot discard a favorited highlight. Unfavorite it first.")
    
    highlight.status = "discarded"
    highlight.is_discarded = True
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
    """Render HTML page with single highlight for review."""
    # Get settings for theme and daily review count
    settings_stmt = select(Settings)
    settings = session.exec(settings_stmt).first()
    
    # Use daily_review_count from settings
    n = settings.daily_review_count if settings else 5
    highlights = get_review_highlights(n=n, session=session)
    
    # Get the first highlight and total count
    highlight = highlights[0] if highlights else None
    total = len(highlights)
    current = 1 if highlight else 0
    
    return templates.TemplateResponse("review.html", {
        "request": request,
        "highlight": highlight,
        "current": current,
        "total": total,
        "settings": settings
    })


@router.post("/ui/review/next", response_class=HTMLResponse)
async def ui_review_next(
    request: Request,
    current_id: int = Form(...),
    reviews_completed: int = Form(0),
    total_reviews: int = Form(0),
    session: Session = Depends(get_session)
):
    """Get the next highlight for review after marking current as done."""
    # Mark the current highlight as reviewed by setting next_review to far future
    current_highlight = session.get(Highlight, current_id)
    if current_highlight:
        # Set next_review to 30 days in the future (or use spaced repetition logic later)
        current_highlight.next_review = datetime.utcnow() + timedelta(days=30)
        session.add(current_highlight)
        session.commit()
    
    # Calculate the next position
    next_current = reviews_completed + 2  # +1 for the current we just completed, +1 for next
    
    # Check if we've reached the total
    if next_current > total_reviews:
        # Review complete - show completion message
        return HTMLResponse(content="""
            <div class="text-center">
                <div class="mb-6">
                    <i data-lucide="check-circle" class="w-20 h-20 mx-auto text-green-500"></i>
                </div>
                <h2 class="text-3xl font-bold text-gray-900 dark:text-white mb-4">Review Complete!</h2>
                <p class="text-lg text-gray-600 dark:text-gray-400 mb-8">
                    Great job! You've reviewed all your highlights for today.
                </p>
                <a href="/dashboard/ui?reviewed=complete" class="inline-flex items-center gap-2 bg-primary-600 hover:bg-primary-700 text-white px-8 py-4 rounded-lg transition-colors text-lg font-semibold">
                    <i data-lucide="arrow-left" class="w-6 h-6"></i>
                    <span>Back to Dashboard</span>
                </a>
            </div>
        """)
    
    # Get settings for theme and daily review count
    settings_stmt = select(Settings)
    settings = session.exec(settings_stmt).first()
    
    # Use daily_review_count from settings
    n = settings.daily_review_count if settings else 5
    highlights = get_review_highlights(n=n, session=session)
    
    # Get next highlight
    if highlights:
        next_highlight = highlights[0]
        current = next_current
        
        return templates.TemplateResponse("_review_card.html", {
            "request": request,
            "highlight": next_highlight,
            "current": current,
            "total": total_reviews
        })
    else:
        # No more highlights - show completion message
        return HTMLResponse(content="""
            <div class="text-center">
                <div class="mb-6">
                    <i data-lucide="check-circle" class="w-20 h-20 mx-auto text-green-500"></i>
                </div>
                <h2 class="text-3xl font-bold text-gray-900 dark:text-white mb-4">Review Complete!</h2>
                <p class="text-lg text-gray-600 dark:text-gray-400 mb-8">
                    Great job! You've reviewed all your highlights for today.
                </p>
                <a href="/dashboard/ui?reviewed=complete" class="inline-flex items-center gap-2 bg-primary-600 hover:bg-primary-700 text-white px-8 py-4 rounded-lg transition-colors text-lg font-semibold">
                    <i data-lucide="arrow-left" class="w-6 h-6"></i>
                    <span>Back to Dashboard</span>
                </a>
            </div>
        """)


@router.get("/ui/favorites", response_class=HTMLResponse)
async def ui_favorites(
    request: Request,
    session: Session = Depends(get_session)
):
    """Render HTML page with all favorite highlights."""
    # Get settings for theme
    settings_stmt = select(Settings)
    settings = session.exec(settings_stmt).first()
    
    # Query all favorited highlights, ordered by most recent first
    statement = (
        select(Highlight)
        .where(Highlight.is_favorited == True)
        .order_by(Highlight.created_at.desc())
    )
    highlights = session.exec(statement).all()
    
    return templates.TemplateResponse("favorites.html", {
        "request": request,
        "highlights": highlights,
        "settings": settings
    })


@router.get("/ui/discarded", response_class=HTMLResponse)
async def ui_discarded(
    request: Request,
    session: Session = Depends(get_session)
):
    """Render HTML page with all discarded highlights."""
    # Get settings for theme
    settings_stmt = select(Settings)
    settings = session.exec(settings_stmt).first()
    
    # Query all discarded highlights, ordered by most recent first
    statement = (
        select(Highlight)
        .where(Highlight.is_discarded == True)
        .order_by(Highlight.created_at.desc())
    )
    highlights = session.exec(statement).all()
    
    return templates.TemplateResponse("discarded.html", {
        "request": request,
        "highlights": highlights,
        "settings": settings
    })


@router.get("/{id}/view", response_class=HTMLResponse)
async def view_highlight_partial(
    request: Request,
    id: int,
    context: Optional[str] = None,
    session: Session = Depends(get_session)
):
    """Return HTML partial for a single highlight (read-only view)."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    # Choose template based on context
    template_name = "_book_highlight.html" if context == "book" else "_highlight_row.html"
    
    return templates.TemplateResponse(template_name, {
        "request": request,
        "highlight": highlight
    })


@router.get("/{id}/edit", response_class=HTMLResponse)
async def get_highlight_edit_form(
    request: Request,
    id: int,
    context: Optional[str] = None,
    session: Session = Depends(get_session)
):
    """Return edit form for highlight."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    # For review context, return special edit form with progress info
    if context == "review":
        # Get settings for daily review count
        settings_stmt = select(Settings)
        settings = session.exec(settings_stmt).first()
        n = settings.daily_review_count if settings else 5
        highlights = get_review_highlights(n=n, session=session)
        
        # Find current position
        current_index = None
        for i, h in enumerate(highlights):
            if h.id == id:
                current_index = i
                break
        
        current = (current_index + 1) if current_index is not None else 1
        total = len(highlights)
        
        return templates.TemplateResponse("_review_edit.html", {
            "request": request,
            "highlight": highlight,
            "current": current,
            "total": total
        })
    
    # Store context in the form for use after save
    return templates.TemplateResponse("_highlight_edit.html", {
        "request": request,
        "highlight": highlight,
        "context": context
    })


@router.post("/{id}/edit", response_class=HTMLResponse)
async def save_highlight_edit(
    request: Request,
    id: int,
    text: str = Form(...),
    note: Optional[str] = Form(None),
    source: Optional[str] = Form(None),
    context: Optional[str] = Form(None),
    session: Session = Depends(get_session)
):
    """Accept form submission and return updated highlight partial."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    highlight.text = text
    highlight.note = note if note else None
    highlight.source = source if source else None
    
    session.add(highlight)
    session.commit()
    session.refresh(highlight)
    
    # For review context, return to review card
    if context == "review":
        # Get settings for daily review count
        settings_stmt = select(Settings)
        settings = session.exec(settings_stmt).first()
        n = settings.daily_review_count if settings else 5
        highlights = get_review_highlights(n=n, session=session)
        
        # Find current position
        current_index = None
        for i, h in enumerate(highlights):
            if h.id == id:
                current_index = i
                break
        
        current = (current_index + 1) if current_index is not None else 1
        total = len(highlights)
        
        return templates.TemplateResponse("_review_card.html", {
            "request": request,
            "highlight": highlight,
            "current": current,
            "total": total
        })
    
    # Choose template based on context
    template_name = "_book_highlight.html" if context == "book" else "_highlight_row.html"
    
    return templates.TemplateResponse(template_name, {
        "request": request,
        "highlight": highlight
    })


# Helper endpoint for cancel button in review edit
@router.get("/ui/review/card/{id}", response_class=HTMLResponse)
async def get_review_card(
    request: Request,
    id: int,
    session: Session = Depends(get_session)
):
    """Return review card for a specific highlight."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    # Get settings for daily review count
    settings_stmt = select(Settings)
    settings = session.exec(settings_stmt).first()
    n = settings.daily_review_count if settings else 5
    highlights = get_review_highlights(n=n, session=session)
    
    # Find current position
    current_index = None
    for i, h in enumerate(highlights):
        if h.id == id:
            current_index = i
            break
    
    current = (current_index + 1) if current_index is not None else 1
    total = len(highlights)
    
    return templates.TemplateResponse("_review_card.html", {
        "request": request,
        "highlight": highlight,
        "current": current,
        "total": total
    })



@router.post("/{id}/favorite", response_class=HTMLResponse)
async def toggle_favorite_html(
    request: Request,
    id: int,
    favorite: bool = Form(...),
    context: Optional[str] = Form(None),
    reviews_completed: int = Form(0),
    total_reviews: int = Form(0),
    session: Session = Depends(get_session)
):
    """Toggle favorite status and return updated highlight partial."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")

    # Block favoriting discarded highlights
    if favorite and highlight.is_discarded:
        raise HTTPException(status_code=400, detail="Cannot favorite a discarded highlight. Restore it first.")
    
    highlight.favorite = favorite
    highlight.is_favorited = favorite  # keep alias in sync
    session.add(highlight)
    session.commit()
    session.refresh(highlight)
    
    # If context is book, render both highlight sections
    if context == "book":
        return render_book_highlights_sections(request, highlight.book_id, session)
    
    # If context is review, return the same highlight card (just updated)
    if context == "review":
        current = reviews_completed + 1
        total = total_reviews
        
        return templates.TemplateResponse("_review_card.html", {
            "request": request,
            "highlight": highlight,
            "current": current,
            "total": total
        })
    
    # Otherwise return just the single highlight
    template_name = "_book_highlight.html" if context == "book" else "_highlight_row.html"
    
    return templates.TemplateResponse(template_name, {
        "request": request,
        "highlight": highlight
    })


@router.post("/{id}/discard", response_class=HTMLResponse)
async def discard_highlight_html(
    request: Request,
    id: int,
    context: Optional[str] = Form(None),
    reviews_completed: int = Form(0),
    total_reviews: int = Form(0),
    session: Session = Depends(get_session)
):
    """Toggle is_discarded status and return updated highlight partial or next review item."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    # Toggle the is_discarded field, blocking when favorited
    new_state = not highlight.is_discarded
    if new_state and (highlight.favorite or getattr(highlight, "is_favorited", False)):
        raise HTTPException(status_code=400, detail="Cannot discard a favorited highlight. Unfavorite it first.")

    highlight.is_discarded = new_state
    highlight.status = "discarded" if new_state else "active"
    session.add(highlight)
    session.commit()
    session.refresh(highlight)
    
    # If context is book, render both highlight sections
    if context == "book":
        return render_book_highlights_sections(request, highlight.book_id, session)
    
    # If context is review, move to next highlight
    if context == "review":
        # Calculate the next position
        next_current = reviews_completed + 2  # +1 for the current we just discarded, +1 for next
        
        # Check if we've reached the total
        if next_current > total_reviews:
            # Review complete - show completion message
            return HTMLResponse(content="""
                <div class="text-center">
                    <div class="mb-6">
                        <i data-lucide="check-circle" class="w-20 h-20 mx-auto text-green-500"></i>
                    </div>
                    <h2 class="text-3xl font-bold text-gray-900 dark:text-white mb-4">Review Complete!</h2>
                    <p class="text-lg text-gray-600 dark:text-gray-400 mb-8">
                        Great job! You've reviewed all your highlights for today.
                    </p>
                    <a href="/dashboard/ui?reviewed=complete" class="inline-flex items-center gap-2 bg-primary-600 hover:bg-primary-700 text-white px-8 py-4 rounded-lg transition-colors text-lg font-semibold">
                        <i data-lucide="arrow-left" class="w-6 h-6"></i>
                        <span>Back to Dashboard</span>
                    </a>
                </div>
            """)
        
        # Get settings for daily review count
        settings_stmt = select(Settings)
        settings = session.exec(settings_stmt).first()
        n = settings.daily_review_count if settings else 5
        highlights = get_review_highlights(n=n, session=session)
        
        # Get the first highlight from the refreshed list (after discarding, the next highlight is now first in the filtered results)
        if highlights:
            next_highlight = highlights[0]
            # Increment reviews_completed since we just processed one
            current = next_current
            total = total_reviews
            
            return templates.TemplateResponse("_review_card.html", {
                "request": request,
                "highlight": next_highlight,
                "current": current,
                "total": total
            })
        else:
            # No more highlights - show completion message
            return HTMLResponse(content="""
                <div class="text-center">
                    <div class="mb-6">
                        <i data-lucide="check-circle" class="w-20 h-20 mx-auto text-green-500"></i>
                    </div>
                    <h2 class="text-3xl font-bold text-gray-900 dark:text-white mb-4">Review Complete!</h2>
                    <p class="text-lg text-gray-600 dark:text-gray-400 mb-8">
                        Great job! You've reviewed all your highlights for today.
                    </p>
                    <a href="/dashboard/ui?reviewed=complete" class="inline-flex items-center gap-2 bg-primary-600 hover:bg-primary-700 text-white px-8 py-4 rounded-lg transition-colors text-lg font-semibold">
                        <i data-lucide="arrow-left" class="w-6 h-6"></i>
                        <span>Back to Dashboard</span>
                    </a>
                </div>
            """)
    
    # Otherwise return just the single highlight
    template_name = "_book_highlight.html" if context == "book" else "_highlight_row.html"
    
    # Return updated highlight with badge
    return templates.TemplateResponse(template_name, {
        "request": request,
        "highlight": highlight
    })

