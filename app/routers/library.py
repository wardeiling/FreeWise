from typing import Optional, List
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func
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
    highlight_count_col = func.count(Highlight.id).label("highlight_count")
    last_highlight_col = func.max(Highlight.created_at).label("last_highlight_date")
    
    books_query = (
        select(
            Book.id,
            Book.title,
            Book.author,
            Book.document_tags,
            Book.created_at,
            Book.updated_at,
            highlight_count_col,
            last_highlight_col
        )
        .outerjoin(Highlight, Book.id == Highlight.book_id)
        .group_by(Book.id)
    )
    
    # Apply sorting
    valid_sorts = ["title", "author", "highlight_count", "date_added", "last_highlight"]
    if sort not in valid_sorts:
        sort = "title"
    
    if order not in ["asc", "desc"]:
        order = "asc"
    
    if sort == "title":
        sort_col = Book.title
    elif sort == "author":
        sort_col = Book.author
    elif sort == "highlight_count":
        sort_col = highlight_count_col
    elif sort == "date_added":
        sort_col = Book.created_at
    elif sort == "last_highlight":
        sort_col = last_highlight_col
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
            "last_highlight_date": result.last_highlight_date,
            "date_added": result.created_at
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


@router.get("/ui/book/{book_id}/add-tag", response_class=HTMLResponse)
async def ui_book_add_tag_form(
    request: Request,
    book_id: int,
    session: Session = Depends(get_session)
):
    """Return inline form for adding a new tag."""
    book = session.get(Book, book_id)
    if not book:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Book not found")
    
    form_html = f"""
    <form hx-post="/library/ui/book/{book_id}/add-tag" hx-target="#document-tags-section" hx-swap="innerHTML" style="display: inline-block;">
        <input 
            type="text" 
            name="new_tag" 
            placeholder="Enter new tag..."
            style="padding: 8px 12px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-color); color: var(--text-color); min-width: 200px;"
            autofocus>
        <button type="submit" style="margin-left: 8px; padding: 8px 16px; background: var(--link-color); color: white; border: none; border-radius: 4px; cursor: pointer;">Add</button>
        <button type="button" 
            hx-get="/library/ui/book/{book_id}/cancel-add-tag" 
            hx-target="#add-tag-form" 
            hx-swap="innerHTML"
            style="margin-left: 8px; padding: 8px 16px; background: transparent; color: var(--muted-text); border: 1px solid var(--border-color); border-radius: 4px; cursor: pointer;">Cancel</button>
    </form>
    """
    return HTMLResponse(content=form_html)


@router.post("/ui/book/{book_id}/add-tag", response_class=HTMLResponse)
async def ui_book_add_tag(
    request: Request,
    book_id: int,
    new_tag: str = Form(""),
    session: Session = Depends(get_session)
):
    """Add a new tag to the book and return updated tags section."""
    book = session.get(Book, book_id)
    if not book:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Add new tag
    new_tag = new_tag.strip()
    if new_tag:
        if book.document_tags:
            # Split existing tags, add new one, deduplicate
            existing_tags = [t.strip() for t in book.document_tags.split(',')]
            if new_tag not in existing_tags:
                existing_tags.append(new_tag)
            book.document_tags = ', '.join(existing_tags)
        else:
            book.document_tags = new_tag
        
        book.updated_at = datetime.utcnow()
        session.add(book)
        session.commit()
        session.refresh(book)
    
    # Return updated tags section
    return _render_tags_section(book)


@router.post("/ui/book/{book_id}/remove-tag", response_class=HTMLResponse)
async def ui_book_remove_tag(
    request: Request,
    book_id: int,
    tag: str = Form(...),
    session: Session = Depends(get_session)
):
    """Remove a tag from the book and return updated tags section."""
    book = session.get(Book, book_id)
    if not book:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Remove tag
    if book.document_tags:
        existing_tags = [t.strip() for t in book.document_tags.split(',')]
        existing_tags = [t for t in existing_tags if t != tag.strip()]
        book.document_tags = ', '.join(existing_tags) if existing_tags else None
        
        book.updated_at = datetime.utcnow()
        session.add(book)
        session.commit()
        session.refresh(book)
    
    # Return updated tags section
    return _render_tags_section(book)


@router.get("/ui/book/{book_id}/cancel-add-tag", response_class=HTMLResponse)
async def ui_book_cancel_add_tag(
    request: Request,
    book_id: int,
    session: Session = Depends(get_session)
):
    """Cancel adding a tag."""
    return HTMLResponse(content="")


def _render_tags_section(book: Book) -> HTMLResponse:
    """Helper function to render the tags section."""
    tags_html = ""
    if book.document_tags:
        tags = book.document_tags.split(',')
        for tag in tags:
            tag_stripped = tag.strip()
            tags_html += f"""
            <div style="display: inline-flex; align-items: center; padding: 6px 12px; background: var(--bg-color); border: 1px solid var(--border-color); border-radius: 20px;">
                <span style="margin-right: 8px;">🏷️ {tag_stripped}</span>
                <button 
                    style="background: transparent; border: none; cursor: pointer; color: #dc3545; padding: 0; font-size: 1.2em; line-height: 1;"
                    hx-post="/library/ui/book/{book.id}/remove-tag"
                    hx-vals='{{"tag": "{tag_stripped}"}}'
                    hx-target="#document-tags-section"
                    hx-swap="innerHTML"
                    title="Remove tag">
                    ×
                </button>
            </div>
            """
    
    full_html = f"""
    <div id="tags-list" style="display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-bottom: 10px;">
        {tags_html}
    </div>
    <div style="text-align: center;">
        <button 
            style="background: var(--bg-color); border: 1px dashed var(--border-color); padding: 8px 16px; border-radius: 20px; cursor: pointer; color: var(--muted-text);"
            hx-get="/library/ui/book/{book.id}/add-tag"
            hx-target="#add-tag-form"
            hx-swap="innerHTML">
            + Add document tags
        </button>
    </div>
    <div id="add-tag-form" style="margin-top: 10px; text-align: center;"></div>
    """
    
    return HTMLResponse(content=full_html)
