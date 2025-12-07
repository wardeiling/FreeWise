from typing import Optional, List
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func, col
from datetime import datetime

from app.db import get_engine
from app.models import Book, Highlight, Settings


router = APIRouter(prefix="/library", tags=["library"])
templates = Jinja2Templates(directory="app/templates")


def get_session():
    """Dependency to provide database session."""
    engine = get_engine()
    with Session(engine) as session:
        yield session


@router.get("/ui", response_class=HTMLResponse)
async def ui_library(
    request: Request,
    sort: Optional[str] = "title",
    order: Optional[str] = "asc",
    session: Session = Depends(get_session)
):
    """
    Render library page with sortable table of books.
    
    Sort options: title, author, highlight_count, last_updated
    Order options: asc, desc
    """
    # Get settings for theme
    settings_stmt = select(Settings)
    settings = session.exec(settings_stmt).first()
    
    # Get all books with aggregated data
    books_query = (
        select(
            Book.id,
            Book.title,
            Book.author,
            Book.document_tags,
            Book.created_at,
            Book.updated_at,
            func.count(Highlight.id).label("highlight_count"),
            func.max(Highlight.updated_at).label("last_highlight_update")
        )
        .outerjoin(Highlight, Book.id == Highlight.book_id)
        .group_by(Book.id)
    )
    
    # Apply sorting
    valid_sorts = ["title", "author", "highlight_count", "last_updated"]
    if sort not in valid_sorts:
        sort = "title"
    
    if order not in ["asc", "desc"]:
        order = "asc"
    
    if sort == "title":
        sort_col = Book.title
    elif sort == "author":
        sort_col = Book.author
    elif sort == "highlight_count":
        sort_col = col("highlight_count")
    elif sort == "last_updated":
        sort_col = col("last_highlight_update")
    else:
        sort_col = Book.title
    
    if order == "desc":
        books_query = books_query.order_by(sort_col.desc())
    else:
        books_query = books_query.order_by(sort_col.asc())
    
    results = session.exec(books_query).all()
    
    # Convert results to list of dicts for template
    books = []
    for result in results:
        books.append({
            "id": result.id,
            "title": result.title,
            "author": result.author or "Unknown",
            "document_tags": result.document_tags,
            "highlight_count": result.highlight_count,
            "last_updated": result.last_highlight_update or result.updated_at,
            "created_at": result.created_at
        })
    
    return templates.TemplateResponse("library.html", {
        "request": request,
        "settings": settings,
        "books": books,
        "current_sort": sort,
        "current_order": order
    })


@router.get("/ui/book/{book_id}", response_class=HTMLResponse)
async def ui_book_detail(
    request: Request,
    book_id: int,
    session: Session = Depends(get_session)
):
    """Display all highlights from a specific book."""
    # Get settings for theme
    settings_stmt = select(Settings)
    settings = session.exec(settings_stmt).first()
    
    # Get book
    book = session.get(Book, book_id)
    if not book:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Get all highlights for this book
    highlights_stmt = (
        select(Highlight)
        .where(Highlight.book_id == book_id)
        .order_by(Highlight.created_at.desc())
    )
    highlights = session.exec(highlights_stmt).all()
    
    return templates.TemplateResponse("book_detail.html", {
        "request": request,
        "settings": settings,
        "book": book,
        "highlights": highlights
    })


@router.get("/ui/book/{book_id}/edit-tags", response_class=HTMLResponse)
async def ui_book_edit_tags_form(
    request: Request,
    book_id: int,
    session: Session = Depends(get_session)
):
    """Return inline form for editing book document tags."""
    book = session.get(Book, book_id)
    if not book:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Book not found")
    
    form_html = f"""
    <form hx-post="/library/ui/book/{book_id}/edit-tags" hx-target="#document-tags-section" hx-swap="innerHTML">
        <div style="display: inline-block;">
            <input 
                type="text" 
                name="document_tags" 
                value="{book.document_tags or ''}"
                placeholder="Enter tags..."
                style="padding: 8px 12px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-color); color: var(--text-color); min-width: 300px;"
                autofocus>
            <button type="submit" style="margin-left: 8px; padding: 8px 16px; background: var(--link-color); color: white; border: none; border-radius: 4px; cursor: pointer;">Save</button>
            <button type="button" 
                hx-get="/library/ui/book/{book_id}/cancel-edit-tags" 
                hx-target="#document-tags-section" 
                hx-swap="innerHTML"
                style="margin-left: 8px; padding: 8px 16px; background: transparent; color: var(--muted-text); border: 1px solid var(--border-color); border-radius: 4px; cursor: pointer;">Cancel</button>
        </div>
    </form>
    """
    return HTMLResponse(content=form_html)


@router.post("/ui/book/{book_id}/edit-tags", response_class=HTMLResponse)
async def ui_book_save_tags(
    request: Request,
    book_id: int,
    document_tags: str = Form(""),
    session: Session = Depends(get_session)
):
    """Save edited book document tags and return updated display."""
    book = session.get(Book, book_id)
    if not book:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Update tags
    book.document_tags = document_tags.strip() or None
    book.updated_at = datetime.utcnow()
    session.add(book)
    session.commit()
    session.refresh(book)
    
    # Return updated display
    if book.document_tags:
        display_html = f"""
        <div style="display: inline-block; padding: 8px 16px; background: var(--bg-color); border: 1px solid var(--border-color); border-radius: 20px; margin-bottom: 10px;">
            <span style="margin-right: 10px;">🏷️</span>
            <span id="document-tags-display">{book.document_tags}</span>
            <button 
                style="margin-left: 10px; background: transparent; border: none; cursor: pointer; color: var(--link-color); padding: 0;"
                hx-get="/library/ui/book/{book.id}/edit-tags"
                hx-target="#document-tags-section"
                hx-swap="innerHTML">
                ✎
            </button>
        </div>
        """
    else:
        display_html = f"""
        <button 
            style="background: var(--bg-color); border: 1px dashed var(--border-color); padding: 8px 16px; border-radius: 20px; cursor: pointer; color: var(--muted-text);"
            hx-get="/library/ui/book/{book.id}/edit-tags"
            hx-target="#document-tags-section"
            hx-swap="innerHTML">
            + Add document tags
        </button>
        """
    
    return HTMLResponse(content=display_html)


@router.get("/ui/book/{book_id}/cancel-edit-tags", response_class=HTMLResponse)
async def ui_book_cancel_edit_tags(
    request: Request,
    book_id: int,
    session: Session = Depends(get_session)
):
    """Cancel editing and return original display."""
    book = session.get(Book, book_id)
    if not book:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Return original display
    if book.document_tags:
        display_html = f"""
        <div style="display: inline-block; padding: 8px 16px; background: var(--bg-color); border: 1px solid var(--border-color); border-radius: 20px; margin-bottom: 10px;">
            <span style="margin-right: 10px;">🏷️</span>
            <span id="document-tags-display">{book.document_tags}</span>
            <button 
                style="margin-left: 10px; background: transparent; border: none; cursor: pointer; color: var(--link-color); padding: 0;"
                hx-get="/library/ui/book/{book.id}/edit-tags"
                hx-target="#document-tags-section"
                hx-swap="innerHTML">
                ✎
            </button>
        </div>
        """
    else:
        display_html = f"""
        <button 
            style="background: var(--bg-color); border: 1px dashed var(--border-color); padding: 8px 16px; border-radius: 20px; cursor: pointer; color: var(--muted-text);"
            hx-get="/library/ui/book/{book.id}/edit-tags"
            hx-target="#document-tags-section"
            hx-swap="innerHTML">
            + Add document tags
        </button>
        """
    
    return HTMLResponse(content=display_html)
