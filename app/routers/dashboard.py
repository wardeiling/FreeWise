from typing import Optional, Dict
from fastapi import APIRouter, Depends, Request, Cookie
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func
from datetime import datetime, date, timedelta

from app.db import get_engine
from app.models import Book, Highlight, Settings, ReviewSession


router = APIRouter(prefix="/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")

# Simple in-memory storage for review tracking (per session)
# In production, this should be stored in database or Redis
review_sessions = {}


def get_session():
    """Dependency to provide database session."""
    engine = get_engine()
    with Session(engine) as session:
        yield session


@router.get("/ui", response_class=HTMLResponse)
async def ui_dashboard(
    request: Request,
    session: Session = Depends(get_session),
    reviewed: Optional[str] = None,
    session_id: Optional[str] = Cookie(None)
):
    """
    Render dashboard page with statistics overview and review CTA.
    """
    # Get settings for theme and daily review count
    settings_stmt = select(Settings)
    settings = session.exec(settings_stmt).first()
    
    daily_review_count = settings.daily_review_count if settings else 5
    
    # Check if user has completed review today
    today = date.today().isoformat()
    reviewed_today = False
    highlights_reviewed_count = 0
    
    # Check if the 'reviewed' query parameter indicates completion
    if reviewed == "complete":
        reviewed_today = True
        highlights_reviewed_count = daily_review_count
        
        # Store in session tracking
        if session_id:
            if session_id not in review_sessions:
                review_sessions[session_id] = {}
            review_sessions[session_id][today] = highlights_reviewed_count
    
    # Check session storage
    if session_id and session_id in review_sessions:
        if today in review_sessions[session_id]:
            reviewed_today = True
            highlights_reviewed_count = review_sessions[session_id][today]
    
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
    
    # Generate heatmap data: group highlights by date (created_at)
    # Query all highlights with created_at dates
    highlights_stmt = select(Highlight).where(Highlight.created_at != None)
    highlights_with_dates = session.exec(highlights_stmt).all()
    
    # Group by date and count
    heatmap_data: Dict[str, int] = {}
    for highlight in highlights_with_dates:
        if highlight.created_at:
            date_key = highlight.created_at.date().isoformat()
            heatmap_data[date_key] = heatmap_data.get(date_key, 0) + 1
    
    # If no data, create empty dict for template compatibility
    if not heatmap_data:
        heatmap_data = {}
    
    # Get review session data for review activity heatmap
    review_sessions_stmt = select(ReviewSession).where(ReviewSession.is_completed == True)
    completed_sessions = session.exec(review_sessions_stmt).all()
    
    # Create binary heatmap data (1 if reviewed that day, 0 otherwise)
    review_heatmap_data: Dict[str, int] = {}
    for review_session in completed_sessions:
        date_key = review_session.session_date.isoformat()
        review_heatmap_data[date_key] = 1  # Binary: reviewed or not
    
    # Calculate streaks
    current_streak = 0
    longest_streak = 0
    
    if completed_sessions:
        # Sort sessions by date (most recent first)
        sorted_dates = sorted([rs.session_date for rs in completed_sessions], reverse=True)
        
        # Calculate current streak
        today_date = date.today()
        yesterday = today_date - timedelta(days=1)
        
        # Check if there's a session today or yesterday to start the streak
        if sorted_dates[0] >= yesterday:
            current_streak = 1
            check_date = sorted_dates[0] - timedelta(days=1)
            
            for i in range(1, len(sorted_dates)):
                if sorted_dates[i] == check_date:
                    current_streak += 1
                    check_date -= timedelta(days=1)
                elif sorted_dates[i] < check_date:
                    # Gap found, break
                    break
        
        # Calculate longest streak (including current)
        if len(sorted_dates) > 0:
            all_dates_sorted = sorted([rs.session_date for rs in completed_sessions])
            temp_streak = 1
            longest_streak = 1
            
            for i in range(1, len(all_dates_sorted)):
                days_diff = (all_dates_sorted[i] - all_dates_sorted[i-1]).days
                if days_diff == 1:
                    temp_streak += 1
                    longest_streak = max(longest_streak, temp_streak)
                else:
                    temp_streak = 1
    
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "settings": settings,
        "daily_review_count": daily_review_count,
        "reviewed_today": reviewed_today,
        "highlights_reviewed_count": highlights_reviewed_count,
        "total_books": total_books,
        "total_highlights": total_highlights,
        "active_highlights": active_highlights,
        "total_favorited": total_favorited,
        "total_discarded": total_discarded,
        "favorited_percentage": favorited_percentage,
        "discarded_percentage": discarded_percentage,
        "active_percentage": active_percentage,
        "heatmap_data": heatmap_data,
        "review_heatmap_data": review_heatmap_data,
        "current_streak": current_streak,
        "longest_streak": longest_streak
    })
