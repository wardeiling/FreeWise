from typing import Optional, List
from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func
from datetime import datetime
import html

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
            highlight_count_col,
            last_highlight_col
        )
        .outerjoin(Highlight, Book.id == Highlight.book_id)
        .group_by(Book.id)
    )
    
    # Apply sorting
    valid_sorts = ["title", "author", "highlight_count", "last_highlight"]
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
            "last_highlight_date": result.last_highlight_date
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
    
    return templates.TemplateResponse("book_detail.html", {
        "request": request,
        "settings": settings,
        "book": book,
        "highlights": highlights
    })


@router.get("/ui/book/{book_id}/edit", response_class=HTMLResponse)
async def ui_book_edit_form(
    request: Request,
    book_id: int,
    session: Session = Depends(get_session)
):
    """Return inline form for editing book metadata."""
    book = session.get(Book, book_id)
    if not book:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Get highlight count for the book
    highlights_stmt = select(Highlight).where(Highlight.book_id == book_id)
    highlights = session.exec(highlights_stmt).all()
    highlight_count = len(highlights)
    
    # Escape HTML entities to prevent quote issues
    escaped_title = html.escape(book.title, quote=True)
    escaped_author = html.escape(book.author or '', quote=True)
    
    form_html = f"""
    <div id="book-header" style="position: relative; text-align: center; margin-bottom: 30px; padding: 30px; background: var(--highlight-bg); border-radius: 8px; border: 1px solid var(--border-color);">
        <form hx-post="/library/ui/book/{book_id}/edit" hx-target="#book-header" hx-swap="outerHTML" style="max-width: 500px; margin: 0 auto;">
            <div style="margin-bottom: 15px;">
                <label style="display: block; text-align: left; margin-bottom: 5px; font-weight: bold; color: var(--text-color);">Book Title</label>
                <input 
                    type="text" 
                    name="title" 
                    value="{escaped_title}" 
                    required
                    style="width: 100%; padding: 10px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-color); color: var(--text-color); font-size: 1em;">
            </div>
            <div style="margin-bottom: 20px;">
                <label style="display: block; text-align: left; margin-bottom: 5px; font-weight: bold; color: var(--text-color);">Author</label>
                <input 
                    type="text" 
                    name="author" 
                    value="{escaped_author}" 
                    style="width: 100%; padding: 10px; border: 1px solid var(--border-color); border-radius: 4px; background: var(--bg-color); color: var(--text-color); font-size: 1em;">
            </div>
            <div style="display: flex; gap: 10px; justify-content: center;">
                <button 
                    type="submit"
                    style="background: #28a745; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: 500;">
                    ✓ Save
                </button>
                <button 
                    type="button"
                    hx-get="/library/ui/book/{book_id}/cancel-edit"
                    hx-target="#book-header"
                    hx-swap="outerHTML"
                    style="background: #6c757d; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-size: 14px; font-weight: 500;">
                    ✕ Cancel
                </button>
            </div>
        </form>
    </div>
    """
    
    return HTMLResponse(content=form_html)


@router.post("/ui/book/{book_id}/edit", response_class=HTMLResponse)
async def ui_book_update(
    request: Request,
    book_id: int,
    title: str = Form(...),
    author: str = Form(""),
    session: Session = Depends(get_session)
):
    """Update book metadata and return updated header."""
    book = session.get(Book, book_id)
    if not book:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Update book metadata
    book.title = title.strip()
    book.author = author.strip() if author.strip() else None
    
    session.add(book)
    session.commit()
    session.refresh(book)
    
    # Get highlight count for the book
    highlights_stmt = select(Highlight).where(Highlight.book_id == book_id)
    highlights = session.exec(highlights_stmt).all()
    highlight_count = len(highlights)
    
    return _render_book_header(book, highlight_count)


@router.get("/ui/book/{book_id}/cancel-edit", response_class=HTMLResponse)
async def ui_book_cancel_edit(
    request: Request,
    book_id: int,
    session: Session = Depends(get_session)
):
    """Cancel editing and return normal book header."""
    book = session.get(Book, book_id)
    if not book:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Get highlight count for the book
    highlights_stmt = select(Highlight).where(Highlight.book_id == book_id)
    highlights = session.exec(highlights_stmt).all()
    highlight_count = len(highlights)
    
    return _render_book_header(book, highlight_count)


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


@router.delete("/ui/book/{book_id}", response_class=HTMLResponse)
async def ui_book_delete(
    request: Request,
    book_id: int,
    session: Session = Depends(get_session)
):
    """Delete a book and all its highlights from the library."""
    book = session.get(Book, book_id)
    if not book:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Book not found")
    
    # Delete all highlights associated with this book
    highlights_stmt = select(Highlight).where(Highlight.book_id == book_id)
    highlights = session.exec(highlights_stmt).all()
    for highlight in highlights:
        session.delete(highlight)
    
    # Delete the book
    session.delete(book)
    session.commit()
    
    # Return response that triggers redirect to library
    return HTMLResponse(
        content="",
        headers={"HX-Redirect": "/library/ui"}
    )


def _render_tags_section(book: Book) -> HTMLResponse:
    """Helper function to render the tags section."""
    tags_html = ""
    if book.document_tags:
        tags = book.document_tags.split(',')
        for tag in tags:
            tag_stripped = tag.strip()
            tags_html += f"""
            <div class="inline-flex items-center px-3 py-1.5 bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-full text-sm">
                <i data-lucide="tag" class="w-3 h-3 mr-1.5"></i>
                <span>{tag_stripped}</span>
                <button 
                    class="ml-2 text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 transition-colors"
                    hx-post="/library/ui/book/{book.id}/remove-tag"
                    hx-vals='{{"tag": "{tag_stripped}"}}'
                    hx-target="#document-tags-section"
                    hx-swap="innerHTML"
                    title="Remove tag">
                    <i data-lucide="x" class="w-3 h-3"></i>
                </button>
            </div>
            """
    
    full_html = f"""
    <div id="tags-list" class="flex flex-wrap gap-2 justify-center mb-3">
        {tags_html}
    </div>
    <div class="text-center">
        <button 
            class="inline-flex items-center gap-1.5 px-4 py-2 bg-white dark:bg-gray-800 border border-dashed border-gray-300 dark:border-gray-600 rounded-full text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200 hover:border-gray-400 dark:hover:border-gray-500 transition-colors"
            hx-get="/library/ui/book/{book.id}/add-tag"
            hx-target="#add-tag-form"
            hx-swap="innerHTML">
            <i data-lucide="plus" class="w-4 h-4"></i>
            <span>Add document tags</span>
        </button>
    </div>
    <div id="add-tag-form" class="mt-3 text-center"></div>
    """
    
    return HTMLResponse(content=full_html)


def _render_book_header(book: Book, highlight_count: int) -> HTMLResponse:
    """Helper function to render the book header section."""
    author_html = f"""
    <div style="margin-bottom: 15px; font-size: 1.2em; color: var(--muted-text);">
        by {book.author}
    </div>
    """ if book.author else ""
    
    header_html = f"""
    <div id="book-header" style="position: relative; text-align: center; margin-bottom: 30px; padding: 30px; background: var(--highlight-bg); border-radius: 8px; border: 1px solid var(--border-color);">
        <!-- Edit Button in Top-Left -->
        <button 
            style="position: absolute; top: 15px; left: 15px; background: transparent; border: none; color: #007bff; cursor: pointer; font-size: 20px; line-height: 1; padding: 5px; transition: transform 0.2s;"
            hx-get="/library/ui/book/{book.id}/edit"
            hx-target="#book-header"
            hx-swap="outerHTML"
            title="Edit Book"
            type="button"
            onmouseover="this.style.transform='scale(1.2)'"
            onmouseout="this.style.transform='scale(1)'">
            ✏️
        </button>
        
        <!-- Delete Button in Top-Right -->
        <button 
            style="position: absolute; top: 15px; right: 15px; background: transparent; border: none; color: #dc3545; cursor: pointer; font-size: 24px; line-height: 1; padding: 5px; transition: transform 0.2s;"
            hx-delete="/library/ui/book/{book.id}"
            hx-confirm="⚠️ Are you sure you want to remove '{book.title}' and all its {highlight_count} highlight(s) from your library? This action cannot be undone."
            title="Remove from Library"
            type="button"
            onmouseover="this.style.transform='scale(1.2)'"
            onmouseout="this.style.transform='scale(1)'">
            ✕
        </button>
        
        <h1 style="margin: 0 0 15px 0; font-size: 2em; color: var(--text-color);">
            {book.title}
        </h1>
        
        {author_html}
        
        <!-- Document Tags Section -->
        <div id="document-tags-section" style="margin-top: 20px;">
            <div id="tags-list" style="display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; margin-bottom: 10px;">
    """
    
    # Add tags
    if book.document_tags:
        tags = book.document_tags.split(',')
        for tag in tags:
            tag_stripped = tag.strip()
            header_html += f"""
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
    
    header_html += f"""
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
        </div>
        
        <div style="margin-top: 20px; color: var(--muted-text); font-size: 0.9em;">
            <strong>{highlight_count}</strong> highlight{'s' if highlight_count != 1 else ''}
        </div>
    </div>
    """
    
    return HTMLResponse(content=header_html)
