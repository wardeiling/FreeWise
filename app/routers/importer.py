import csv
import io
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
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

def parse_readwise_datetime(dt_str: str) -> datetime:
    """Parse various datetime formats from Readwise CSV."""
    if not dt_str or dt_str.strip() == "":
        return datetime.utcnow()
    
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
        book.updated_at = datetime.utcnow()
        session.add(book)
        session.commit()
        session.refresh(book)
    
    return book


@router.get("/ui", response_class=HTMLResponse)
async def ui_import(
    request: Request,
    session: Session = Depends(get_session)
):
    """Render import page with file upload form."""
    # Get settings for theme
    settings_stmt = select(Settings)
    settings = session.exec(settings_stmt).first()
    
    return templates.TemplateResponse("import.html", {
        "request": request,
        "settings": settings
    })


@router.post("/ui", response_class=HTMLResponse)
async def process_import(
    request: Request,
    file: UploadFile = File(...),
    session: Session = Depends(get_session)
):
    """
    Process uploaded Readwise CSV file and import highlights.
    
    Expected CSV columns:
    Highlight,Book Title,Book Author,Amazon Book ID,Note,Color,Tags,
    Location Type,Location,Highlighted at,Document tags
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
        
        # Validate required columns
        required_columns = ['Highlight']
        if not all(col in reader.fieldnames for col in required_columns):
            raise HTTPException(
                status_code=400, 
                detail=f"CSV must contain at least 'Highlight' column. Found: {reader.fieldnames}"
            )
        
        imported_count = 0
        skipped_count = 0
        
        for row in reader:
            # Skip empty rows
            if not row.get('Highlight', '').strip():
                skipped_count += 1
                continue
            
            # Extract data from CSV
            highlight_text = row.get('Highlight', '').strip()
            book_title = row.get('Book Title', '').strip()
            book_author = row.get('Book Author', '').strip()
            note = row.get('Note', '').strip()
            tags_str = row.get('Tags', '').strip()
            document_tags_str = row.get('Document tags', '').strip()
            highlighted_at_str = row.get('Highlighted at', '').strip()
            
            # Parse datetime
            created_at = parse_readwise_datetime(highlighted_at_str)
            if not created_at:
                created_at = datetime.utcnow()
            
            # Get or create book
            book = None
            if book_title:
                book = get_or_create_book(
                    session=session,
                    title=book_title,
                    author=book_author if book_author else None,
                    document_tags=document_tags_str if document_tags_str else None
                )
            
            # Create highlight
            highlight = Highlight(
                text=highlight_text,
                source=book_title if book_title else None,  # Keep for backwards compatibility
                author=book_author if book_author else None,  # Keep for backwards compatibility
                book_id=book.id if book else None,
                note=note if note else None,
                created_at=created_at,
                updated_at=datetime.utcnow(),
                user_id=1,  # Default user for single-user mode
                status="active",
                is_favorited=False,
                is_discarded=False
            )
            
            session.add(highlight)
            session.commit()
            session.refresh(highlight)
            
            # Process tags if present (using utility function)
            if tags_str:
                tag_names = parse_tags(tags_str)
                for tag_name in tag_names:
                    tag = get_or_create_tag(session, tag_name)
                    if tag:
                        # Create highlight-tag relationship
                        highlight_tag = HighlightTag(
                            highlight_id=highlight.id,
                            tag_id=tag.id
                        )
                        session.add(highlight_tag)
                
                session.commit()
            
            imported_count += 1
        
        # Get settings for theme
        settings_stmt = select(Settings)
        settings = session.exec(settings_stmt).first()
        
        # Return success page
        return templates.TemplateResponse("import.html", {
            "request": request,
            "settings": settings,
            "success_message": f"Successfully imported {imported_count} highlights. Skipped {skipped_count} empty rows.",
            "imported_count": imported_count,
            "skipped_count": skipped_count
        })
    
    except csv.Error as e:
        raise HTTPException(status_code=400, detail=f"Invalid CSV format: {str(e)}")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File encoding error. Please ensure the file is UTF-8 encoded.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
