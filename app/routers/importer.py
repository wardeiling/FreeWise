import csv
import io
import base64
from datetime import datetime
from typing import Optional, Dict, Any, List
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, select

from app.db import get_engine
from app.models import Highlight, Tag, HighlightTag, Settings, Book
from app.utils.tags import parse_tags, join_tags


router = APIRouter(prefix="/import", tags=["import"])
templates = Jinja2Templates(directory="app/templates")


def get_session():
    """Dependency to provide database session."""
    engine = get_engine()
    with Session(engine) as session:
        yield session

def parse_readwise_datetime(dt_str: str) -> Optional[datetime]:
    """Parse various datetime formats from Readwise CSV.
    
    Returns None if the date string is empty or cannot be parsed.
    """
    if not dt_str or dt_str.strip() == "":
        return None
    
    formats = [
        "%B %d, %Y %I:%M:%S %p",      # January 15, 2024 10:30:00 AM
        "%Y-%m-%d %H:%M:%S",           # 2024-01-15 10:30:00
        "%Y-%m-%dT%H:%M:%S",           # 2024-01-15T10:30:00
        "%Y-%m-%d %H:%M:%S%z",         # 2025-12-10 14:18:00+00:00
        "%Y-%m-%dT%H:%M:%S%z",         # 2025-12-10T14:18:00+00:00
        "%Y-%m-%d %H:%M:%S.%f",        # 2024-01-15 10:30:00.000000
        "%Y-%m-%d %H:%M:%S.%f%z",      # 2024-01-15 10:30:00.000000+00:00
    ]
    
    for fmt in formats:
        try:
            parsed = datetime.strptime(dt_str.strip(), fmt)
            # Convert timezone-aware datetime to UTC naive datetime
            if parsed.tzinfo is not None:
                parsed = parsed.replace(tzinfo=None)
            return parsed
        except ValueError:
            continue
    
    # If all formats fail, return None
    return None


def get_or_create_tag(session: Session, tag_name: str) -> Tag:
    """Get existing tag or create new one."""
    tag_name = tag_name.strip()
    if not tag_name:
        return None
    
    # Check if tag exists
    statement = select(Tag).where(Tag.name == tag_name)
    tag = session.exec(statement).first()
    
    if not tag:
        tag = Tag(name=tag_name)
        session.add(tag)
        session.commit()
        session.refresh(tag)
    
    return tag


def get_or_create_book(session: Session, title: str, author: Optional[str] = None, document_tags: Optional[str] = None) -> Optional[Book]:
    """Get existing book or create new one based on title and author."""
    if not title or not title.strip():
        return None
    
    title = title.strip()
    author = author.strip() if author else None
    
    # Check if book exists (match on title and author)
    statement = select(Book).where(Book.title == title)
    if author:
        statement = statement.where(Book.author == author)
    else:
        statement = statement.where(Book.author == None)
    
    book = session.exec(statement).first()
    
    if not book:
        book = Book(
            title=title,
            author=author,
            document_tags=document_tags
        )
        session.add(book)
        session.commit()
        session.refresh(book)
    elif document_tags and not book.document_tags:
        # Update document tags if they weren't set before
        book.document_tags = document_tags
        session.add(book)
        session.commit()
        session.refresh(book)
    
    return book


@router.get("/ui", response_class=HTMLResponse)
async def ui_import(
    request: Request,
    session: Session = Depends(get_session)
):
    """Render main import page with source selection."""
    # Get settings for theme
    settings_stmt = select(Settings)
    settings = session.exec(settings_stmt).first()
    
    return templates.TemplateResponse("import_main.html", {
        "request": request,
        "settings": settings
    })


@router.get("/ui/readwise", response_class=HTMLResponse)
async def ui_import_readwise(
    request: Request,
    session: Session = Depends(get_session)
):
    """Render Readwise import page."""
    # Get settings for theme
    settings_stmt = select(Settings)
    settings = session.exec(settings_stmt).first()
    
    return templates.TemplateResponse("import_readwise.html", {
        "request": request,
        "settings": settings
    })


@router.get("/ui/custom", response_class=HTMLResponse)
async def ui_import_custom(
    request: Request,
    session: Session = Depends(get_session)
):
    """Render custom CSV import page."""
    # Get settings for theme
    settings_stmt = select(Settings)
    settings = session.exec(settings_stmt).first()
    
    return templates.TemplateResponse("import_custom.html", {
        "request": request,
        "settings": settings
    })


@router.post("/ui/custom/preview", response_class=HTMLResponse)
async def ui_import_custom_preview(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    """Preview CSV and show column mapping interface."""
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    try:
        # Read file content
        contents = await file.read()
        csv_text = contents.decode('utf-8')
        csv_file = io.StringIO(csv_text)
        
        # Parse CSV
        reader = csv.DictReader(csv_file)
        
        # Get column names
        csv_columns = reader.fieldnames
        if not csv_columns:
            raise HTTPException(status_code=400, detail="CSV file has no columns")
        
        # Get first 3 rows for preview
        preview_data = []
        for i, row in enumerate(reader):
            if i >= 3:
                break
            preview_data.append(row)
        
        # Encode CSV data for passing to next step
        csv_data_b64 = base64.b64encode(csv_text.encode('utf-8')).decode('utf-8')
        
        # Get settings for theme
        settings_stmt = select(Settings)
        settings = session.exec(settings_stmt).first()
        
        return templates.TemplateResponse("import_custom.html", {
            "request": request,
            "settings": settings,
            "preview_data": preview_data,
            "csv_columns": csv_columns,
            "csv_data_b64": csv_data_b64
        })
    
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File encoding error. Please ensure the file is UTF-8 encoded.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Preview failed: {str(e)}")


@router.post("/ui/custom/process", response_class=HTMLResponse)
async def process_custom_import(
    request: Request,
    csv_data: str = Form(...),
    highlight: str = Form(...),
    book_title: str = Form(...),
    book_author: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),
    document_tags: Optional[str] = Form(None),
    highlighted_at: Optional[str] = Form(None),
    location: Optional[str] = Form(None),
    session: Session = Depends(get_session)
):
    """Process custom CSV with user-defined column mapping."""
    try:
        # Decode CSV data
        csv_text = base64.b64decode(csv_data).decode('utf-8')
        csv_file = io.StringIO(csv_text)
        
        # Parse CSV
        reader = csv.DictReader(csv_file)
        
        # Build column mapping
        column_mapping = {
            'highlight': highlight,
            'book_title': book_title if book_title else None,
            'book_author': book_author if book_author else None,
            'note': note if note else None,
            'tags': tags if tags else None,
            'document_tags': document_tags if document_tags else None,
            'highlighted_at': highlighted_at if highlighted_at else None,
            'location': location if location else None
        }
        
        imported_count = 0
        skipped_count = 0
        duplicate_count = 0
        skipped_rows = []
        
        for idx, row in enumerate(reader, start=1):
            # Map columns
            highlight_text = row.get(column_mapping['highlight'], '').strip() if column_mapping['highlight'] else ''
            
            # Skip empty rows
            if not highlight_text:
                skipped_count += 1
                skipped_rows.append({
                    "row": idx,
                    "reason": "Empty highlight",
                    "highlight": highlight_text,
                    "note": "",
                    "book_title": ""
                })
                continue
            
            # Extract mapped data
            book_title_val = row.get(column_mapping['book_title'], '').strip() if column_mapping['book_title'] else ''
            book_author_val = row.get(column_mapping['book_author'], '').strip() if column_mapping['book_author'] else ''
            note_val = row.get(column_mapping['note'], '').strip() if column_mapping['note'] else ''

            # Require book title
            if not book_title_val:
                skipped_count += 1
                skipped_rows.append({
                    "row": idx,
                    "reason": "Missing book title",
                    "highlight": highlight_text,
                    "note": note_val,
                    "book_title": book_title_val
                })
                continue
            
            # Skip header marker notes
            if note_val.lower() in {'.h1', '.h2', '.h3', '.h4', '.h5', '.h6'}:
                skipped_count += 1
                skipped_rows.append({
                    "row": idx,
                    "reason": "Header marker note (.h1-.h6)",
                    "highlight": highlight_text,
                    "note": note_val,
                    "book_title": book_title_val
                })
                continue
            
            tags_val = row.get(column_mapping['tags'], '').strip() if column_mapping['tags'] else ''
            document_tags_val = row.get(column_mapping['document_tags'], '').strip() if column_mapping['document_tags'] else ''
            highlighted_at_val = row.get(column_mapping['highlighted_at'], '').strip() if column_mapping['highlighted_at'] else ''
            location_val = row.get(column_mapping['location'], '').strip() if column_mapping['location'] else ''
            
            # Parse datetime
            created_at = parse_readwise_datetime(highlighted_at_val) if highlighted_at_val else None
            
            # Get or create book
            book = get_or_create_book(
                session=session,
                title=book_title_val,
                author=book_author_val if book_author_val else None,
                document_tags=document_tags_val if document_tags_val else None
            )
            
            # Parse tags
            is_favorited = False
            is_discarded = False
            regular_tags = []
            
            if tags_val:
                tag_names = parse_tags(tags_val)
                for tag_name in tag_names:
                    tag_lower = tag_name.lower()
                    if tag_lower == "favorite":
                        is_favorited = True
                    elif tag_lower == "discard":
                        is_discarded = True
                    else:
                        regular_tags.append(tag_name)
            
            # Deduplicate
            existing_stmt = select(Highlight).where(
                Highlight.text == highlight_text,
                Highlight.note == (note_val if note_val else None),
                Highlight.book_id == (book.id if book else None)
            )
            existing_highlight = session.exec(existing_stmt).first()
            if existing_highlight:
                duplicate_count += 1
                skipped_rows.append({
                    "row": idx,
                    "reason": "Duplicate highlight",
                    "highlight": highlight_text,
                    "note": note_val,
                    "book_title": book_title_val
                })
                continue
            
            # Parse location
            location_int = None
            if location_val:
                try:
                    location_int = int(location_val)
                except (ValueError, TypeError):
                    location_int = None
            
            # Create highlight
            highlight = Highlight(
                text=highlight_text,
                source=book_title_val if book_title_val else None,
                author=book_author_val if book_author_val else None,
                book_id=book.id if book else None,
                note=note_val if note_val else None,
                created_at=created_at,
                location=location_int,
                user_id=1,
                status="discarded" if is_discarded else "active",
                is_favorited=is_favorited,
                is_discarded=is_discarded,
                favorite=is_favorited
            )
            
            session.add(highlight)
            session.commit()
            session.refresh(highlight)
            
            # Process tags
            for tag_name in regular_tags:
                tag = get_or_create_tag(session, tag_name)
                if tag:
                    highlight_tag = HighlightTag(
                        highlight_id=highlight.id,
                        tag_id=tag.id
                    )
                    session.add(highlight_tag)
            
            if regular_tags:
                session.commit()
            
            imported_count += 1
        
        # Get settings for theme
        settings_stmt = select(Settings)
        settings = session.exec(settings_stmt).first()
        
        # Return success page on custom import page
        return templates.TemplateResponse("import_custom.html", {
            "request": request,
            "settings": settings,
            "success_message": f"Successfully imported {imported_count} highlights. Skipped {skipped_count} rows. Deduplicated {duplicate_count} duplicates.",
            "imported_count": imported_count,
            "skipped_count": skipped_count,
            "duplicate_count": duplicate_count,
            "skipped_rows": skipped_rows
        })
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


@router.post("/ui/readwise", response_class=HTMLResponse)
async def process_readwise_import(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    """
    Process uploaded Readwise CSV file and import highlights.
    
    Accepts both:
    1. Standard Readwise CSV exports with columns:
       Highlight, Book Title, Book Author, Amazon Book ID, Note, Color, Tags,
       Location Type, Location, Highlighted at, Document tags
    
    2. Extended FreeWise CSV exports with additional columns:
       is_favorited, is_discarded
    
    The importer is backwards-compatible and will use extended metadata if present,
    or fall back to defaults if columns are missing.
    """
    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    try:
        # Read file content
        contents = await file.read()
        csv_text = contents.decode('utf-8')
        csv_file = io.StringIO(csv_text)
        
        # Parse CSV
        reader = csv.DictReader(csv_file)
        
        # Validate required columns (must have at least Highlight column)
        required_columns = ['Highlight']
        if not all(col in reader.fieldnames for col in required_columns):
            raise HTTPException(
                status_code=400, 
                detail=f"CSV must contain at least 'Highlight' column. Found: {reader.fieldnames}"
            )
        
        imported_count = 0
        skipped_count = 0
        duplicate_count = 0
        skipped_rows = []
        
        for idx, row in enumerate(reader, start=1):
            # Skip empty rows
            if not row.get('Highlight', '').strip():
                skipped_count += 1
                skipped_rows.append({
                    "row": idx,
                    "reason": "Empty highlight",
                    "highlight": row.get('Highlight', '').strip(),
                    "note": row.get('Note', '').strip(),
                    "book_title": row.get('Book Title', '').strip()
                })
                continue
            
            # Extract data from CSV - support both Readwise and extended format
            highlight_text = row.get('Highlight', '').strip()
            book_title = row.get('Book Title', '').strip()
            book_author = row.get('Book Author', '').strip()
            note = row.get('Note', '').strip()
            if note.lower() in {'.h1', '.h2', '.h3', '.h4', '.h5', '.h6'}:
                skipped_count += 1
                skipped_rows.append({
                    "row": idx,
                    "reason": "Header marker note (.h1-.h6)",
                    "highlight": highlight_text,
                    "note": note,
                    "book_title": book_title
                })
                continue
            tags_str = row.get('Tags', '').strip()
            document_tags_str = row.get('Document tags', '').strip()
            highlighted_at_str = row.get('Highlighted at', '').strip()
            location_type_str = row.get('Location Type', '').strip()
            location_str = row.get('Location', '').strip()
            
            # Extended columns (optional - only in FreeWise exports)
            is_favorited_str = row.get('is_favorited', '').strip().lower()
            is_discarded_str = row.get('is_discarded', '').strip().lower()
            
            # Parse datetime
            datetime_str = highlighted_at_str
            created_at = parse_readwise_datetime(datetime_str)
            # If no date is provided, created_at remains None (don't use today's date as fallback)
            
            # Get or create book
            book = None
            if book_title:
                book = get_or_create_book(
                    session=session,
                    title=book_title,
                    author=book_author if book_author else None,
                    document_tags=document_tags_str if document_tags_str else None
                )
            
            # Parse tags and check for special tags (favorite, discard)
            # Extended format: use explicit is_favorited/is_discarded columns if present
            # Standard format: parse from tags
            is_favorited = False
            is_discarded = False
            regular_tags = []
            
            # Check extended columns first (takes precedence)
            if is_favorited_str in ['true', '1', 'yes']:
                is_favorited = True
            if is_discarded_str in ['true', '1', 'yes']:
                is_discarded = True
            
            # Parse tags string for both tag creation and legacy favorite/discard detection
            if tags_str:
                tag_names = parse_tags(tags_str)
                for tag_name in tag_names:
                    tag_lower = tag_name.lower()
                    # Only use tag-based favorite/discard if extended columns not present
                    if tag_lower == "favorite" and not is_favorited_str:
                        is_favorited = True
                    elif tag_lower == "discard" and not is_discarded_str:
                        is_discarded = True
                    else:
                        regular_tags.append(tag_name)
            
            # Deduplicate: skip if an identical highlight (same text and note) already exists for this book
            existing_stmt = select(Highlight).where(
                Highlight.text == highlight_text,
                Highlight.note == (note if note else None),
                Highlight.book_id == (book.id if book else None)
            )
            existing_highlight = session.exec(existing_stmt).first()
            if existing_highlight:
                duplicate_count += 1
                skipped_rows.append({
                    "row": idx,
                    "reason": "Duplicate highlight",
                    "highlight": highlight_text,
                    "note": note,
                    "book_title": book_title
                })
                continue

            # Parse location if provided
            location = None
            location_type = location_type_str if location_type_str else None
            if location_str:
                try:
                    location = int(location_str)
                except (ValueError, TypeError):
                    # If location is not a valid integer, skip it
                    location = None
                    location_type = None

            # Create highlight with appropriate boolean flags
            highlight = Highlight(
                text=highlight_text,
                source=book_title if book_title else None,  # Keep for backwards compatibility
                author=book_author if book_author else None,  # Keep for backwards compatibility
                book_id=book.id if book else None,
                note=note if note else None,
                created_at=created_at,
                location_type=location_type,
                location=location,
                user_id=1,  # Default user for single-user mode
                status="discarded" if is_discarded else "active",
                is_favorited=is_favorited,
                is_discarded=is_discarded,
                favorite=is_favorited  # Set the favorite alias field too
            )
            
            session.add(highlight)
            session.commit()
            session.refresh(highlight)
            
            # Process regular tags (excluding favorite/discard which are now boolean fields)
            for tag_name in regular_tags:
                tag = get_or_create_tag(session, tag_name)
                if tag:
                    # Create highlight-tag relationship
                    highlight_tag = HighlightTag(
                        highlight_id=highlight.id,
                        tag_id=tag.id
                    )
                    session.add(highlight_tag)
            
            if regular_tags:
                session.commit()
            
            imported_count += 1
        
        # Get settings for theme
        settings_stmt = select(Settings)
        settings = session.exec(settings_stmt).first()
        
        # Return success page
        return templates.TemplateResponse("import_readwise.html", {
            "request": request,
            "settings": settings,
            "success_message": f"Successfully imported {imported_count} highlights. Skipped {skipped_count} rows. Deduplicated {duplicate_count} duplicates.",
            "imported_count": imported_count,
            "skipped_count": skipped_count,
            "duplicate_count": duplicate_count,
            "skipped_rows": skipped_rows
        })
    
    except csv.Error as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV format: {str(e)}")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File encoding error. Please ensure the file is UTF-8 encoded.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")


# Legacy route for backward compatibility
@router.post("/ui", response_class=HTMLResponse)
async def process_import_legacy(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    """Legacy import route - redirects to Readwise import for backward compatibility."""
    return await process_readwise_import(request, file, session)
