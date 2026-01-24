from typing import Optional, List
from fastapi import APIRouter, Depends, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select, func
from datetime import datetime
import html
import os
import uuid
import aiofiles
import httpx

from app.db import get_engine
from app.models import Book, Highlight, Settings


router = APIRouter(prefix="/library", tags=["library"])
templates = Jinja2Templates(directory="app/templates")

COVER_UPLOAD_DIR = os.path.join("app", "static", "uploads", "covers")
ALLOWED_COVER_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_COVER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_COVER_SIZE_BYTES = 5 * 1024 * 1024


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


@router.post("/ui/book/{book_id}/cover/upload", response_class=HTMLResponse)
async def ui_book_cover_upload(
    request: Request,
    book_id: int,
    cover_file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    """Upload a cover image for a book and return updated cover section."""
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if cover_file.content_type not in ALLOWED_COVER_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    original_name = cover_file.filename or ""
    ext = os.path.splitext(original_name)[1].lower()
    if ext not in ALLOWED_COVER_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported file extension")

    content = await cover_file.read()
    if len(content) > MAX_COVER_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File is too large")

    _delete_existing_cover_file(book)
    os.makedirs(COVER_UPLOAD_DIR, exist_ok=True)
    filename = f"book-{book_id}-{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(COVER_UPLOAD_DIR, filename)

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    book.cover_image_url = f"/static/uploads/covers/{filename}"
    book.cover_image_source = "upload"
    session.add(book)
    session.commit()
    session.refresh(book)

    return _render_cover_section(book)


@router.post("/ui/book/{book_id}/cover/search", response_class=HTMLResponse)
async def ui_book_cover_search(
    request: Request,
    book_id: int,
    query: str = Form(""),
    session: Session = Depends(get_session)
):
    """Search Open Library for book covers and return search results HTML."""
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    search_query = query.strip()
    if not search_query:
        return _render_cover_search_results(book_id, [], "")

    results: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://openlibrary.org/search.json",
                params={"q": search_query, "limit": 8}
            )
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError:
        return HTMLResponse(content="<div class=\"text-sm text-gray-500 dark:text-gray-400 text-center\">Open Library search failed. Please try again.</div>")

    for doc in data.get("docs", []):
        cover_id = doc.get("cover_i")
        if not cover_id:
            continue
        title = doc.get("title") or "Untitled"
        author_list = doc.get("author_name") or []
        author = author_list[0] if author_list else "Unknown"
        year = doc.get("first_publish_year")
        results.append({
            "cover_id": cover_id,
            "title": title,
            "author": author,
            "year": year
        })

    return _render_cover_search_results(book_id, results, search_query)


@router.post("/ui/book/{book_id}/cover/select", response_class=HTMLResponse)
async def ui_book_cover_select(
    request: Request,
    book_id: int,
    cover_url: str = Form(""),
    session: Session = Depends(get_session)
):
    """Select an Open Library cover image for a book and return updated cover section."""
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    if not (cover_url.startswith("https://covers.openlibrary.org/") or cover_url.startswith("http://covers.openlibrary.org/")):
        raise HTTPException(status_code=400, detail="Invalid cover URL")

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(cover_url, follow_redirects=True)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "").split(";")[0].strip().lower()
            content = response.content
    except httpx.HTTPError:
        return HTMLResponse(
            content="<div class=\"text-sm text-red-600 dark:text-red-400 text-center\">Failed to download cover image. Please try again.</div>",
            status_code=400
        )

    ext = os.path.splitext(cover_url)[1].lower()
    inferred_ok = ext in ALLOWED_COVER_EXTENSIONS
    if content_type and content_type not in ALLOWED_COVER_TYPES and not inferred_ok:
        return HTMLResponse(
            content="<div class=\"text-sm text-red-600 dark:text-red-400 text-center\">Unsupported cover image type.</div>",
            status_code=400
        )

    if len(content) > MAX_COVER_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="Cover image is too large")

    ext_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
    }
    if content_type in ext_map:
        ext = ext_map[content_type]
    elif inferred_ok:
        ext = os.path.splitext(cover_url)[1].lower()
    else:
        ext = ".jpg"

    _delete_existing_cover_file(book)
    os.makedirs(COVER_UPLOAD_DIR, exist_ok=True)
    filename = f"book-{book_id}-{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(COVER_UPLOAD_DIR, filename)

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    book.cover_image_url = f"/static/uploads/covers/{filename}"
    book.cover_image_source = "openlibrary"
    session.add(book)
    session.commit()
    session.refresh(book)

    return _render_cover_section(book)


@router.post("/ui/book/{book_id}/cover/delete", response_class=HTMLResponse)
async def ui_book_cover_delete(
    request: Request,
    book_id: int,
    session: Session = Depends(get_session)
):
    """Delete the existing cover image for a book and return updated cover section."""
    book = session.get(Book, book_id)
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    _delete_existing_cover_file(book)
    book.cover_image_url = None
    book.cover_image_source = None
    session.add(book)
    session.commit()
    session.refresh(book)

    return _render_cover_section(book)


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
    
    cover_source_badge = ""
    if book.cover_image_source:
        cover_source_badge = f"""
            <span class=\"inline-flex items-center px-2 py-0.5 text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-full\">
                {html.escape(book.cover_image_source)}
            </span>
        """

    form_html = f"""
    <div id="book-header" class="text-center mb-8">
        <div class="w-full max-w-2xl mx-auto">
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
                        form="book-metadata-form"
                        class="flex items-center gap-1 px-3 py-1.5 bg-amber-600 hover:bg-amber-700 dark:bg-amber-700 dark:hover:bg-amber-600 text-white rounded-md font-medium text-xs transition-colors"
                        title="Save">
                        <svg data-lucide="save" class="w-4 h-4"></svg>
                        <span>Save</span>
                    </button>
                </div>
            </div>

            <!-- Form Fields -->
            <div class="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-b-lg p-6 space-y-4">
                <div class=\"border border-dashed border-gray-300 dark:border-gray-600 rounded-lg p-4\">
                    <div class=\"flex items-center justify-between mb-2\">
                        <div class=\"text-xs font-semibold text-gray-600 dark:text-gray-300\">Cover Image</div>
                        {cover_source_badge}
                    </div>
                    <p class=\"text-xs text-gray-500 dark:text-gray-400 mb-4\">Choose one option: upload your own file or search Open Library.</p>

                    <div class=\"grid grid-cols-1 md:grid-cols-2 gap-4\">
                        <div class=\"border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-gray-50 dark:bg-gray-900/30\">
                            <div class=\"flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-200 mb-3\">
                                <svg data-lucide=\"upload\" class=\"w-4 h-4\"></svg>
                                <span>Manual upload</span>
                            </div>
                            <form 
                                hx-post=\"/library/ui/book/{book_id}/cover/upload\"
                                hx-target=\"#cover-section\"
                                hx-swap=\"outerHTML\"
                                hx-encoding=\"multipart/form-data\"
                                hx-indicator=\"#cover-upload-indicator\"
                                class=\"flex flex-col items-center gap-3\">
                                <input 
                                    type=\"file\"
                                    name=\"cover_file\"
                                    accept=\"image/jpeg,image/png,image/webp\"
                                    class=\"block w-full text-sm text-gray-500 file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:text-sm file:font-semibold file:bg-amber-50 file:text-amber-700 hover:file:bg-amber-100 dark:file:bg-gray-700 dark:file:text-gray-200\"
                                    required>
                                <button 
                                    type=\"submit\"
                                    class=\"w-full px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white text-sm font-medium rounded-md transition-colors\">
                                    Upload cover
                                </button>
                            </form>

                            <div id=\"cover-upload-indicator\" class=\"htmx-indicator mt-3\">
                                <div class=\"h-2 w-full bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden\">
                                    <div class=\"h-full bg-amber-600 animate-pulse\" style=\"width: 100%;\"></div>
                                </div>
                                <div class=\"text-xs text-gray-500 dark:text-gray-400 text-center mt-1\">Uploading...</div>
                            </div>
                        </div>

                        <div class=\"border border-gray-200 dark:border-gray-700 rounded-lg p-4 bg-gray-50 dark:bg-gray-900/30\">
                            <div class=\"flex items-center gap-2 text-sm font-semibold text-gray-700 dark:text-gray-200 mb-3\">
                                <svg data-lucide=\"search\" class=\"w-4 h-4\"></svg>
                                <span>Search Open Library</span>
                            </div>
                            <form 
                                hx-post=\"/library/ui/book/{book_id}/cover/search\"
                                hx-target=\"#cover-search-results\"
                                hx-swap=\"innerHTML\"
                                class=\"flex flex-col items-center gap-3\">
                                <input 
                                    type=\"text\"
                                    name=\"query\"
                                    value=\"{escaped_title}\"
                                    placeholder=\"Search by title or author\"
                                    class=\"w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 text-sm\">
                                <button 
                                    type=\"submit\"
                                    class=\"w-full px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium rounded-md transition-colors\">
                                    Find covers
                                </button>
                            </form>
                        </div>
                    </div>

                    <div id=\"cover-search-results\" class=\"mt-4\"></div>

                    <div id=\"cover-download-indicator\" class=\"htmx-indicator mt-4\">
                        <div class=\"h-2 w-full max-w-xs mx-auto bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden\">
                            <div class=\"h-full bg-emerald-600 animate-pulse\" style=\"width: 100%;\"></div>
                        </div>
                        <div class=\"text-xs text-gray-500 dark:text-gray-400 text-center mt-1\">Downloading cover...</div>
                    </div>

                    <form 
                        hx-post=\"/library/ui/book/{book_id}/cover/delete\"
                        hx-target=\"#cover-section\"
                        hx-swap=\"outerHTML\"
                        class=\"flex items-center justify-center mt-3\">
                        <button 
                            type=\"submit\"
                            class=\"px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white text-sm font-medium rounded-md transition-colors\">
                            Remove cover
                        </button>
                    </form>
                </div>
                <form id="book-metadata-form" hx-post="/library/ui/book/{book_id}/edit" hx-target="#book-header" hx-swap="outerHTML" class="space-y-4">
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
                <div>
                    <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Review Frequency</label>
                    <div>
                        <div class="flex items-center gap-3">
                            <span class="text-xs text-gray-500 dark:text-gray-400">Never</span>
                            <input 
                                type="range"
                                name="review_weight"
                                min="0"
                                max="2"
                                step="0.1"
                                value="{book.review_weight if book.review_weight is not None else 1.0}"
                                class="flex-1 accent-amber-600">
                            <span class="text-xs text-gray-500 dark:text-gray-400">More</span>
                        </div>
                        <div class="text-center text-xs text-gray-500 dark:text-gray-400 mt-1">Normally</div>
                    </div>
                </div>
                </form>

                <!-- Action Buttons moved to header for consistency -->
            </div>
        </div>
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
    review_weight: float = Form(1.0),
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
    book.review_weight = min(2.0, max(0.0, float(review_weight)))
    
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


def _render_cover_section(book: Book) -> HTMLResponse:
    """Render the cover image display section only."""
    cover_url = book.cover_image_url or ""
    title_attr = html.escape(book.title, quote=True)

    cover_display = f"""
        <div class=\"w-36 h-52 rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 flex items-center justify-center\">
            <img src=\"{cover_url}\" alt=\"Cover for {title_attr}\" class=\"w-full h-full object-cover\" />
        </div>
    """ if cover_url else """
        <div class=\"w-36 h-52 rounded-lg border border-dashed border-gray-300 dark:border-gray-700 bg-gray-50 dark:bg-gray-800 flex flex-col items-center justify-center text-gray-400\">
            <svg data-lucide=\"image\" class=\"w-8 h-8 mb-2\"></svg>
            <span class=\"text-xs\">No cover</span>
        </div>
    """

    html_content = f"""
    <div id=\"cover-section\" class=\"mb-10\">
        <div class=\"flex flex-col items-center gap-4\">
            {cover_display}
        </div>
    </div>
    <script>
        if (typeof lucide !== 'undefined') {{
            lucide.createIcons();
        }}
    </script>
    """

    return HTMLResponse(content=html_content)


def _render_cover_search_results(book_id: int, results: list[dict], query: str) -> HTMLResponse:
    """Render Open Library cover search results list."""
    if not query:
        return HTMLResponse(content="<div class=\"text-sm text-gray-500 dark:text-gray-400 text-center\">Enter a search query to find covers.</div>")

    if not results:
        return HTMLResponse(content="<div class=\"text-sm text-gray-500 dark:text-gray-400 text-center\">No covers found. Try a different search.</div>")

    items_html = ""
    for item in results:
        cover_id = item["cover_id"]
        cover_url = f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg"
        title = html.escape(item["title"])
        author = html.escape(item["author"])
        year = item.get("year")
        year_html = f"<span class=\\\"text-xs text-gray-500 dark:text-gray-400\\\">({year})</span>" if year else ""
        items_html += f"""
        <div class=\"flex items-center gap-4 p-3 border border-gray-200 dark:border-gray-700 rounded-lg\">
            <img src=\"{cover_url}\" alt=\"Cover\" class=\"w-12 h-16 object-cover rounded\" />
            <div class=\"flex-1\">
                <div class=\"text-sm font-semibold text-gray-900 dark:text-gray-100\">{title} {year_html}</div>
                <div class=\"text-xs text-gray-600 dark:text-gray-400\">{author}</div>
            </div>
            <form 
                hx-post=\"/library/ui/book/{book_id}/cover/select\"
                hx-target=\"#cover-section\"
                hx-swap=\"outerHTML\"
                hx-indicator=\"#cover-download-indicator\">
                <input type=\"hidden\" name=\"cover_url\" value=\"{cover_url}\">
                <button type=\"submit\" class=\"px-3 py-1.5 text-xs font-medium bg-emerald-600 hover:bg-emerald-700 text-white rounded-md\">Use</button>
            </form>
        </div>
        """

    html_content = f"""
    <div class=\"space-y-3\">
        {items_html}
    </div>
    """

    return HTMLResponse(content=html_content)


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


def _delete_existing_cover_file(book: Book) -> None:
    """Delete existing local cover file if present."""
    if not book.cover_image_url:
        return
    if not book.cover_image_url.startswith("/static/uploads/covers/"):
        return

    filename = book.cover_image_url.split("/")[-1]
    file_path = os.path.join(COVER_UPLOAD_DIR, filename)
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except OSError:
        pass


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
