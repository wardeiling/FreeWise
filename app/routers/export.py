import csv
import io
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, Response, HTTPException
from sqlmodel import Session, select

from app.db import get_engine
from app.models import Highlight, Book, Tag, HighlightTag


router = APIRouter(prefix="/export", tags=["export"])


def get_session():
    """Dependency to provide database session."""
    engine = get_engine()
    with Session(engine) as session:
        yield session


@router.get("/csv")
async def export_highlights_csv(
    session: Session = Depends(get_session)
):
    """
    Export all highlights to CSV with Readwise-compatible schema.
    
    The export follows the official Readwise CSV format for the first 11 columns,
    allowing direct re-import into Readwise or FreeWise. Additional FreeWise-specific
    metadata columns are appended after the Readwise-compatible block.
    
    Readwise columns (1-11):
    - Highlight, Book Title, Book Author, Amazon Book ID, Note, Color,
      Tags, Location Type, Location, Highlighted at, Document tags
    
    Extended columns (12-13):
    - is_favorited, is_discarded
    """
    # Query all highlights with their associated books
    statement = (
        select(Highlight, Book)
        .outerjoin(Book, Highlight.book_id == Book.id)
        .order_by(Highlight.created_at.desc())
    )
    results = session.exec(statement).all()
    
    if not results:
        raise HTTPException(status_code=400, detail="No highlights available to export.")

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    
    # Write header row - Readwise columns first, then extended columns
    headers = [
        # Readwise-compatible columns (exact naming and order)
        'Highlight',
        'Book Title',
        'Book Author',
        'Amazon Book ID',
        'Note',
        'Color',
        'Tags',
        'Location Type',
        'Location',
        'Highlighted at',
        'Document tags',
        # Extended FreeWise columns
        'is_favorited',
        'is_discarded',
    ]
    writer.writerow(headers)
    
    # Write data rows
    for highlight, book in results:
        # Get highlight-specific tags (excluding special tags like favorite/discard)
        highlight_tags_stmt = (
            select(Tag.name)
            .join(HighlightTag, HighlightTag.tag_id == Tag.id)
            .where(HighlightTag.highlight_id == highlight.id)
        )
        tag_results = session.exec(highlight_tags_stmt).all()
        # Filter out system tags and join with comma-space separator
        regular_tags = [tag for tag in tag_results if tag.lower() not in ['favorite', 'discard']]
        tags_str = ', '.join(regular_tags) if regular_tags else ''
        
        # Determine favorite status (check both fields for backwards compatibility)
        is_favorited = highlight.is_favorited or (highlight.favorite if hasattr(highlight, 'favorite') and highlight.favorite else False)
        
        # Format timestamps in ISO format for consistency
        highlighted_at = highlight.created_at.isoformat() if highlight.created_at else ''
        
        row = [
            # Readwise-compatible columns
            highlight.text or '',                                           # Highlight
            book.title if book else (highlight.source or ''),              # Book Title
            book.author if book else (highlight.author or ''),             # Book Author
            '',                                                             # Amazon Book ID (not used)
            highlight.note or '',                                           # Note
            '',                                                             # Color (not used)
            tags_str,                                                       # Tags (highlight-level)
            highlight.location_type or '',                                  # Location Type (page or order)
            str(highlight.location) if highlight.location else '',          # Location (page number or order)
            highlighted_at,                                                 # Highlighted at (ISO format)
            book.document_tags if book and book.document_tags else '',     # Document tags (book-level)
            # Extended FreeWise columns
            'true' if is_favorited else 'false',                           # is_favorited
            'true' if highlight.is_discarded else 'false',                 # is_discarded
        ]
        writer.writerow(row)
    
    # Generate filename with current date
    filename = f"freewise_export_{datetime.now().strftime('%Y%m%d')}.csv"
    
    # Return CSV as downloadable file
    csv_content = output.getvalue()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
