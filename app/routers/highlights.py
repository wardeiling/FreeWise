from datetime import datetime, timedelta, date
from typing import Optional, List, Dict
from collections import defaultdict
import math
import random
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Form, Cookie
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func
from pydantic import BaseModel

from app.db import get_engine
from app.models import Highlight, Settings, ReviewSession


router = APIRouter(prefix="/highlights", tags=["highlights"])
templates = Jinja2Templates(directory="app/templates")

# In-memory session storage for review queues
# Format: {session_id: {"highlight_ids": [int], "current_index": int, "timestamp": datetime}}
review_sessions: Dict[str, Dict] = {}


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

    # Auto-unfavorite when discarding
    if highlight.favorite or getattr(highlight, "is_favorited", False):
        highlight.favorite = False
        highlight.is_favorited = False
    
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
    """
    # Load n from settings if not provided
    if n is None:
        settings_stmt = select(Settings)
        settings = session.exec(settings_stmt).first()
        n = settings.daily_review_count if settings else 5
    
    now = datetime.utcnow()

    # Fetch all active highlights (exclude discarded)
    statement = (
        select(Highlight)
        .where(Highlight.status == "active")
        .where(Highlight.is_discarded == False)
    )
    highlights = list(session.exec(statement).all())

    if not highlights:
        return []

    # Scoring parameters
    tau_days = 14.0

    def get_book_weight(h: Highlight) -> float:
        if h.book and h.book.review_weight is not None:
            return max(0.0, float(h.book.review_weight))
        return 1.0

    def get_days_since(h: Highlight) -> float:
        anchor = h.last_reviewed_at or h.created_at
        if anchor is None:
            return 30.0
        delta = now - anchor
        return max(0.0, delta.total_seconds() / 86400.0)

    def time_score(days: float) -> float:
        # Smooth time-decayed resurfacing
        return 1.0 - math.exp(-days / tau_days)

    # Build candidate list with scores
    candidates = []
    for h in highlights:
        weight = get_book_weight(h)
        if weight <= 0.0:
            continue
        days = get_days_since(h)
        score = time_score(days) * weight
        if score <= 0.0:
            continue
        book_id = h.book_id
        candidates.append((h, score, book_id))

    if not candidates:
        return []

    # Diversity constraint (Option B): weighted sampling with per-book cap
    max_per_book = 2 if n >= 4 else 1
    selected = []
    book_counts: Dict[Optional[int], int] = defaultdict(int)

    def weighted_pick(items: list[tuple[Highlight, float, Optional[int]]]) -> tuple[Highlight, float, Optional[int]]:
        total = sum(item[1] for item in items)
        if total <= 0:
            return random.choice(items)
        r = random.random() * total
        upto = 0.0
        for item in items:
            upto += item[1]
            if upto >= r:
                return item
        return items[-1]

    remaining = candidates[:]

    while len(selected) < n and remaining:
        eligible = [c for c in remaining if book_counts[c[2]] < max_per_book]
        if not eligible:
            break
        pick = weighted_pick(eligible)
        selected.append(pick[0])
        book_counts[pick[2]] += 1
        remaining.remove(pick)

    # Fill remaining slots ignoring per-book cap if needed
    if len(selected) < n and remaining:
        while len(selected) < n and remaining:
            pick = weighted_pick(remaining)
            selected.append(pick[0])
            remaining.remove(pick)

    return selected


# ============ HTML/HTMX Endpoints ============

@router.get("/ui/review", response_class=HTMLResponse)
async def ui_review(
    request: Request,
    session: Session = Depends(get_session),
    review_session_id: Optional[str] = Cookie(None),
    reset: Optional[str] = None
):
    """Render HTML page with single highlight for review."""
    # Get settings for theme and daily review count
    settings_stmt = select(Settings)
    settings = session.exec(settings_stmt).first()
    
    # Use daily_review_count from settings
    n = settings.daily_review_count if settings else 5
    
    # Check if we should reset or if session is invalid/expired
    should_create_new = (
        reset == "true" or
        not review_session_id or
        review_session_id not in review_sessions or
        (datetime.utcnow() - review_sessions[review_session_id]["timestamp"]).total_seconds() > 86400  # 24 hours
    )
    
    if should_create_new:
        # Generate new review queue
        highlights = get_review_highlights(n=n, session=session)
        highlight_ids = [h.id for h in highlights]
        
        # Create new session
        new_session_id = str(uuid.uuid4())
        now = datetime.utcnow()
        review_sessions[new_session_id] = {
            "highlight_ids": highlight_ids,
            "current_index": 0,
            "timestamp": now
        }
        review_session_id = new_session_id
        
        # Create ReviewSession database record
        db_session = ReviewSession(
            user_id=1,  # Default user
            session_uuid=new_session_id,
            started_at=now,
            session_date=date.today(),
            target_count=n,
            highlights_reviewed=0,
            highlights_discarded=0,
            highlights_favorited=0,
            is_completed=False
        )
        session.add(db_session)
        session.commit()
        
        # Clean up old sessions (older than 24 hours)
        expired = [sid for sid, data in review_sessions.items() 
                   if (now - data["timestamp"]).total_seconds() > 86400]
        for sid in expired:
            del review_sessions[sid]
    else:
        # Resume existing session
        session_data = review_sessions[review_session_id]
        highlight_ids = session_data["highlight_ids"]
    
    # Get current highlight from session
    session_data = review_sessions[review_session_id]
    current_index = session_data["current_index"]
    highlight_ids = session_data["highlight_ids"]
    
    if current_index < len(highlight_ids):
        highlight_id = highlight_ids[current_index]
        highlight = session.get(Highlight, highlight_id)
        current = current_index + 1
        total = len(highlight_ids)
    else:
        highlight = None
        current = 0
        total = len(highlight_ids)
    
    response = templates.TemplateResponse("review.html", {
        "request": request,
        "highlight": highlight,
        "current": current,
        "total": total,
        "settings": settings
    })
    
    # Set session cookie
    response.set_cookie(
        key="review_session_id",
        value=review_session_id,
        max_age=86400,  # 24 hours
        httponly=True,
        samesite="lax"
    )
    
    return response


@router.post("/ui/review/next", response_class=HTMLResponse)
async def ui_review_next(
    request: Request,
    current_id: int = Form(...),
    reviews_completed: int = Form(0),
    total_reviews: int = Form(0),
    session: Session = Depends(get_session),
    review_session_id: Optional[str] = Cookie(None)
):
    """Get the next highlight for review after marking current as done."""
    # Mark the current highlight as reviewed
    current_highlight = session.get(Highlight, current_id)
    if current_highlight:
        current_highlight.last_reviewed_at = datetime.utcnow()
        current_highlight.review_count = (current_highlight.review_count or 0) + 1
        session.add(current_highlight)
        session.commit()
    
    # Update ReviewSession highlights_reviewed counter
    if review_session_id:
        stmt = select(ReviewSession).where(ReviewSession.session_uuid == review_session_id)
        db_review_session = session.exec(stmt).first()
        if db_review_session:
            db_review_session.highlights_reviewed += 1
            session.add(db_review_session)
            session.commit()
    
    # Update session index
    if review_session_id and review_session_id in review_sessions:
        review_sessions[review_session_id]["current_index"] += 1
        session_data = review_sessions[review_session_id]
        current_index = session_data["current_index"]
        highlight_ids = session_data["highlight_ids"]
        
        # Check if we've reached the end
        if current_index >= len(highlight_ids):
            # Mark session as complete in database
            stmt = select(ReviewSession).where(ReviewSession.session_uuid == review_session_id)
            db_review_session = session.exec(stmt).first()
            if db_review_session:
                db_review_session.completed_at = datetime.utcnow()
                db_review_session.is_completed = True
                session.add(db_review_session)
                session.commit()
            
            # Review complete - clean up session and show completion message
            del review_sessions[review_session_id]
            return HTMLResponse(content="""<div class="text-center">
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
        
        # Get next highlight from session
        next_highlight_id = highlight_ids[current_index]
        next_highlight = session.get(Highlight, next_highlight_id)
        
        if next_highlight:
            return templates.TemplateResponse("_review_card.html", {
                "request": request,
                "highlight": next_highlight,
                "current": current_index + 1,
                "total": len(highlight_ids)
            })
    
    # Fallback: No valid session, show completion
    return HTMLResponse(content="""
        <div class="text-center">
            <div class="mb-6">
                <i data-lucide="check-circle" class="w-20 h-20 mx-auto text-green-500"></i>
            </div>
            <h2 class="text-3xl font-bold text-gray-900 dark:text-white mb-4">Session Expired</h2>
            <p class="text-lg text-gray-600 dark:text-gray-400 mb-8">
                Your review session has expired. Please start a new review.
            </p>
            <a href="/highlights/ui/review?reset=true" class="inline-flex items-center gap-2 bg-primary-600 hover:bg-primary-700 text-white px-8 py-4 rounded-lg transition-colors text-lg font-semibold">
                <i data-lucide="refresh-cw" class="w-6 h-6"></i>
                <span>Start New Review</span>
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
    session: Session = Depends(get_session),
    review_session_id: Optional[str] = Cookie(None)
):
    """Return edit form for highlight."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    # For review context, return special edit form with session info
    if context == "review" and review_session_id and review_session_id in review_sessions:
        session_data = review_sessions[review_session_id]
        current_index = session_data["current_index"]
        highlight_ids = session_data["highlight_ids"]
        
        return templates.TemplateResponse("_review_edit.html", {
            "request": request,
            "highlight": highlight,
            "current": current_index + 1,
            "total": len(highlight_ids)
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
    session: Session = Depends(get_session),
    review_session_id: Optional[str] = Cookie(None)
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
    
    # For review context, return to review card with session info
    if context == "review" and review_session_id and review_session_id in review_sessions:
        session_data = review_sessions[review_session_id]
        current_index = session_data["current_index"]
        highlight_ids = session_data["highlight_ids"]
        
        return templates.TemplateResponse("_review_card.html", {
            "request": request,
            "highlight": highlight,
            "current": current_index + 1,
            "total": len(highlight_ids)
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
    session: Session = Depends(get_session),
    review_session_id: Optional[str] = Cookie(None)
):
    """Return review card for a specific highlight."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    # Get session info
    if review_session_id and review_session_id in review_sessions:
        session_data = review_sessions[review_session_id]
        current_index = session_data["current_index"]
        highlight_ids = session_data["highlight_ids"]
        current = current_index + 1
        total = len(highlight_ids)
    else:
        current = 1
        total = 1
    
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
    session: Session = Depends(get_session),
    review_session_id: Optional[str] = Cookie(None)
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
    
    # Update ReviewSession counter if favoriting during review
    if context == "review" and review_session_id and favorite:
        stmt = select(ReviewSession).where(ReviewSession.session_uuid == review_session_id)
        db_review_session = session.exec(stmt).first()
        if db_review_session:
            db_review_session.highlights_favorited += 1
            session.add(db_review_session)
            session.commit()
    
    # If context is book, render both highlight sections
    if context == "book":
        return render_book_highlights_sections(request, highlight.book_id, session)
    
    # If context is review, return the same highlight card with session info
    if context == "review" and review_session_id and review_session_id in review_sessions:
        session_data = review_sessions[review_session_id]
        current_index = session_data["current_index"]
        highlight_ids = session_data["highlight_ids"]
        
        return templates.TemplateResponse("_review_card.html", {
            "request": request,
            "highlight": highlight,
            "current": current_index + 1,
            "total": len(highlight_ids)
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
    session: Session = Depends(get_session),
    review_session_id: Optional[str] = Cookie(None)
):
    """Toggle is_discarded status and return updated highlight partial or next review item."""
    highlight = session.get(Highlight, id)
    if not highlight:
        raise HTTPException(status_code=404, detail="Highlight not found")
    
    # Toggle the is_discarded field
    new_state = not highlight.is_discarded
    if new_state and (highlight.favorite or getattr(highlight, "is_favorited", False)):
        highlight.favorite = False
        highlight.is_favorited = False

    highlight.is_discarded = new_state
    highlight.status = "discarded" if new_state else "active"
    session.add(highlight)
    session.commit()
    session.refresh(highlight)
    
    # Update ReviewSession counter if discarding during review
    if context == "review" and review_session_id and new_state:
        stmt = select(ReviewSession).where(ReviewSession.session_uuid == review_session_id)
        db_review_session = session.exec(stmt).first()
        if db_review_session:
            db_review_session.highlights_discarded += 1
            session.add(db_review_session)
            session.commit()
    
    # If context is book, render both highlight sections
    if context == "book":
        return render_book_highlights_sections(request, highlight.book_id, session)
    
    # If context is review, move to next highlight using session queue
    if context == "review" and review_session_id and review_session_id in review_sessions:
        review_sessions[review_session_id]["current_index"] += 1
        session_data = review_sessions[review_session_id]
        current_index = session_data["current_index"]
        highlight_ids = session_data["highlight_ids"]
        
        # Check if we've reached the end
        if current_index >= len(highlight_ids):
            # Mark session as complete in database
            stmt = select(ReviewSession).where(ReviewSession.session_uuid == review_session_id)
            db_review_session = session.exec(stmt).first()
            if db_review_session:
                db_review_session.completed_at = datetime.utcnow()
                db_review_session.is_completed = True
                session.add(db_review_session)
                session.commit()
            
            # Review complete - clean up session
            del review_sessions[review_session_id]
            return HTMLResponse(content="""<div class="text-center">
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
        
        # Get next highlight from session
        next_highlight_id = highlight_ids[current_index]
        next_highlight = session.get(Highlight, next_highlight_id)
        
        if next_highlight:
            return templates.TemplateResponse("_review_card.html", {
                "request": request,
                "highlight": next_highlight,
                "current": current_index + 1,
                "total": len(highlight_ids)
            })
    
    # Otherwise return just the single highlight
    template_name = "_book_highlight.html" if context == "book" else "_highlight_row.html"
    
    # Return updated highlight with badge
    return templates.TemplateResponse(template_name, {
        "request": request,
        "highlight": highlight
    })

