from typing import Dict
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func
from datetime import datetime, date

from app.db import get_session, get_settings, get_current_streak
from app.models import Book, Highlight, Settings, ReviewSession


router = APIRouter(prefix="/dashboard", tags=["dashboard"])
templates = Jinja2Templates(directory="app/templates")



@router.get("/ui", response_class=HTMLResponse)
async def ui_dashboard(
    request: Request,
    session: Session = Depends(get_session),
):
    """
    Render dashboard page with statistics overview and review CTA.
    """
    # Get settings for theme and daily review count
    settings = get_settings(session)

    daily_review_count = settings.daily_review_count if settings else 5
    
    # Check if user has completed review today via DB
    today_date = date.today()
    completed_today_stmt = (
        select(ReviewSession)
        .where(ReviewSession.session_date == today_date)
        .where(ReviewSession.is_completed == True)
    )
    completed_today = session.exec(completed_today_stmt).first()
    reviewed_today = completed_today is not None
    highlights_reviewed_count = completed_today.highlights_reviewed if completed_today else 0
    
    # Get total books count
    books_count_stmt = select(func.count(Book.id))
    total_books = session.exec(books_count_stmt).one()
    
    # Get total highlights count
    highlights_count_stmt = select(func.count(Highlight.id))
    total_highlights = session.exec(highlights_count_stmt).one()
    
    # Get total favorited highlights
    favorited_stmt = select(func.count(Highlight.id)).where(
        Highlight.is_favorited == True
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
    
    # Generate heatmap data via SQL GROUP BY — no full table scan
    heatmap_stmt = (
        select(func.date(Highlight.created_at), func.count(Highlight.id))
        .where(Highlight.created_at != None)
        .group_by(func.date(Highlight.created_at))
    )
    heatmap_data: Dict[str, int] = {
        str(row[0]): row[1] for row in session.exec(heatmap_stmt).all()
    }
    
    # Get review session data for review activity heatmap
    review_sessions_stmt = select(ReviewSession).where(ReviewSession.is_completed == True)
    completed_sessions = session.exec(review_sessions_stmt).all()
    
    # Create binary heatmap data (1 if reviewed that day, 0 otherwise)
    review_heatmap_data: Dict[str, int] = {}
    for review_session in completed_sessions:
        date_key = review_session.session_date.isoformat()
        review_heatmap_data[date_key] = 1  # Binary: reviewed or not
    
    # Current streak — shared utility (same logic used by the nav middleware)
    current_streak = get_current_streak(session)
    longest_streak = 0

    if completed_sessions:
        # Longest ever streak; deduplicate same-day sessions first
        all_dates_sorted = sorted({rs.session_date for rs in completed_sessions})
        if all_dates_sorted:
            temp_streak = 1
            longest_streak = 1
            for i in range(1, len(all_dates_sorted)):
                days_diff = (all_dates_sorted[i] - all_dates_sorted[i - 1]).days
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
