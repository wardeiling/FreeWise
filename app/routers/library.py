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
    <div id="book-header" class="text-center mb-8">
        <form hx-post="/library/ui/book/{book_id}/edit" hx-target="#book-header" hx-swap="outerHTML" class="max-w-md mx-auto">
            <!-- Form Header with Edit Indicator -->
            <div class="bg-amber-50 dark:bg-amber-950/20 border-b border-amber-200 dark:border-amber-800 px-4 py-3 rounded-t-lg flex justify-between items-center">
                <span class="text-sm font-medium text-amber-900 dark:text-amber-100 flex items-center gap-2">
                    <svg data-lucide="pencil" class="w-4 h-4"></svg>
                    <span>Editing Book Metadata</span>
                </span>
                <div class="flex items-center gap-2">
                    <button 
                        type="button"
                        hx-get="/library/ui/book/{book_id}/cancel-edit"
                        hx-target="#book-header"
                        hx-swap="outerHTML"
                        class="flex items-center gap-1 px-3 py-1.5 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-900 dark:text-gray-100 rounded-md transition-colors text-xs font-medium"
                        title="Cancel">
                        <svg data-lucide="x" class="w-4 h-4"></svg>
                        <span>Cancel</span>
                    </button>
                    <button 
                        type="submit"
                        class="flex items-center gap-1 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 dark:bg-amber-700 dark:hover:bg-amber-600 text-white rounded-md font-medium text-xs transition-colors"
                        title="Save">
                        <svg data-lucide="save" class="w-4 h-4"></svg>
                        <span>Save</span>
                    </button>
                </div>
            </div>

            <!-- Form Fields -->
            <div class="bg-white dark:bg-gray-800 rounded-b-lg p-6 space-y-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Book Title</label>
                    <textarea 
                        name="title" 
                        required
                        rows="1"
                        class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent transition-all resize-none overflow-hidden"
                        oninput="this.style.height='auto'; this.style.height=this.scrollHeight+'px'">{escaped_title}</textarea>
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Author</label>
                    <input 
                        type="text" 
                        name="author" 
                        value="{escaped_author}" 
                        class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent transition-all">
                </div>

                <!-- Action Buttons moved to header for consistency -->
            </div>
        </form>
    </div>
    <script>
        (function() {{
            function resizeTitle(root) {{
                const t = (root && root.querySelector) ? root.querySelector('textarea[name="title"]') : document.querySelector('textarea[name="title"]');
                if (t) {{
                    t.style.height = 'auto';
                    t.style.height = t.scrollHeight + 'px';
                }}
            }}

            resizeTitle(document);

            if (window.htmx && window.htmx.onLoad) {{
                window.htmx.onLoad(resizeTitle);
            }}

            if (typeof lucide !== 'undefined') {{
                lucide.createIcons();
            }}
        }})();
    </script>
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
            tag_display = html.escape(tag_stripped)
            tag_attr = html.escape(tag_stripped, quote=True)
            tags_html += f"""
            <div class=\"inline-flex items-center px-3 py-1.5 bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-full text-sm\">
                <i data-lucide=\"tag\" class=\"w-3 h-3 mr-1.5\"></i>
                <span>{tag_display}</span>
                <form 
                    hx-post=\"/library/ui/book/{book.id}/remove-tag\"
                    hx-target=\"#document-tags-section\"
                    hx-swap=\"innerHTML\"
                    class=\"inline-flex items-center\">
                    <input type=\"hidden\" name=\"tag\" value=\"{tag_attr}\">
                    <button 
                        type=\"submit\"
                        class=\"ml-2 text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 transition-colors\"
                        title=\"Remove tag\">
                        <i data-lucide=\"x\" class=\"w-3 h-3\"></i>
                    </button>
                </form>
            </div>
            """

    full_html = f"""
    <div id=\"tags-list\" class=\"flex flex-wrap gap-2 justify-center mb-3\">
        {tags_html}
    </div>
    <div class=\"text-center\">
        <form 
            hx-post=\"/library/ui/book/{book.id}/add-tag\"
            hx-target=\"#document-tags-section\"
            hx-swap=\"innerHTML\"
            class=\"inline-flex items-center gap-2 px-3 py-2 bg-white dark:bg-gray-800 border border-dashed border-gray-300 dark:border-gray-600 rounded-full text-gray-600 dark:text-gray-400 hover:border-gray-400 dark:hover:border-gray-500 transition-colors\">
            <i data-lucide=\"plus\" class=\"w-4 h-4\"></i>
            <input 
                type=\"text\"
                name=\"new_tag\"
                placeholder=\"Add document tags\"
                class=\"bg-transparent focus:outline-none text-sm text-gray-700 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500\"
                autocomplete=\"off\">
            <button type=\"submit\" class=\"text-xs font-medium text-amber-700 dark:text-amber-300 hover:text-amber-900 dark:hover:text-amber-100 transition-colors\">Add</button>
        </form>
    </div>
    <script>
        if (typeof lucide !== 'undefined') {{
            lucide.createIcons();
        }}
    </script>
    """

    return HTMLResponse(content=full_html)


def _render_book_header(book: Book, highlight_count: int) -> HTMLResponse:
    """Helper function to render the book header section."""
    active_highlights = [h for h in book.highlights if not h.is_discarded] if book.highlights else []
    discarded_highlights = [h for h in book.highlights if h.is_discarded] if book.highlights else []
    
    author_html = f"""
        <div class="text-lg text-gray-600 dark:text-gray-400 mb-6">
            by {book.author}
        </div>
    """ if book.author else ""
    
    discarded_html = f"""
                <span class="mx-2">|</span>
                <span class="font-semibold">{len(discarded_highlights)}</span> discarded
            """ if len(discarded_highlights) > 0 else ""
    
    header_html = f"""
    <div id="book-header" class="text-center mb-8">
        <h1 class="text-4xl font-bold text-gray-900 dark:text-white mb-3 title-font">
            {book.title}
        </h1>
        
        {author_html}
        
        <div class="mb-6 text-sm text-gray-600 dark:text-gray-400">
            <span class="font-semibold">{len(active_highlights)}</span> active highlight{'s' if len(active_highlights) != 1 else ''}
            {discarded_html}
        </div>
        
        <!-- Action Buttons (Edit/Delete) -->
        <div class="flex items-center justify-center gap-4 mb-6">
            <button 
                class="flex items-center gap-2 px-3 py-2 text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300 transition-colors"
                hx-get="/library/ui/book/{book.id}/edit"
                hx-target="#book-header"
                hx-swap="outerHTML"
                title="Edit Book"
                type="button">
                <svg data-lucide="pencil" class="w-4 h-4"></svg>
                <span class="text-xs font-medium">Edit</span>
            </button>
            <button 
                class="flex items-center gap-2 px-3 py-2 text-rose-600 dark:text-rose-400 hover:text-rose-700 dark:hover:text-rose-300 transition-colors"
                hx-delete="/library/ui/book/{book.id}"
                hx-confirm="⚠️ Are you sure you want to remove '{book.title}' and all its {highlight_count} highlight(s) from your library? This action cannot be undone."
                title="Remove from Library"
                type="button">
                <svg data-lucide="trash-2" class="w-4 h-4"></svg>
                <span class="text-xs font-medium">Remove</span>
            </button>
        </div>
        
        <!-- Document Tags Section -->
        <div id="document-tags-section" class="mt-6">
            <div id="tags-list" class="flex flex-wrap gap-2 justify-center mb-3">
    """
    
    # Add tags
    if book.document_tags:
        tags = book.document_tags.split(',')
        for tag in tags:
            tag_stripped = tag.strip()
            tag_display = html.escape(tag_stripped)
            tag_attr = html.escape(tag_stripped, quote=True)
            header_html += f"""
                <div class="inline-flex items-center px-3 py-1.5 bg-gray-100 dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-full text-sm">
                    <svg data-lucide="tag" class="w-3 h-3 mr-1.5"></svg>
                    <span>{tag_display}</span>
                    <form 
                        hx-post="/library/ui/book/{book.id}/remove-tag"
                        hx-target="#document-tags-section"
                        hx-swap="innerHTML"
                        class="inline-flex items-center">
                        <input type="hidden" name="tag" value="{tag_attr}">
                        <button 
                            type="submit"
                            class="ml-2 text-red-600 dark:text-red-400 hover:text-red-700 dark:hover:text-red-300 transition-colors"
                            title="Remove tag">
                            <svg data-lucide="x" class="w-3 h-3"></svg>
                        </button>
                    </form>
                </div>
            """
    
    header_html += f"""
            </div>
            <div class="text-center">
                <form 
                    hx-post="/library/ui/book/{book.id}/add-tag"
                    hx-target="#document-tags-section"
                    hx-swap="innerHTML"
                    class="inline-flex items-center gap-2 px-3 py-2 bg-white dark:bg-gray-800 border border-dashed border-gray-300 dark:border-gray-600 rounded-full text-gray-600 dark:text-gray-400 hover:border-gray-400 dark:hover:border-gray-500 transition-colors">
                    <svg data-lucide="plus" class="w-4 h-4"></svg>
                    <input 
                        type="text"
                        name="new_tag"
                        placeholder="Add document tags"
                        class="bg-transparent focus:outline-none text-sm text-gray-700 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500"
                        autocomplete="off">
                    <button type="submit" class="text-xs font-medium text-amber-700 dark:text-amber-300 hover:text-amber-900 dark:hover:text-amber-100 transition-colors">Add</button>
                </form>
            </div>
        </div>
    </div>
    <script>
        if (typeof lucide !== 'undefined') {{
            lucide.createIcons();
        }}
    </script>
    """
    
    return HTMLResponse(content=header_html)
