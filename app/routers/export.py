import csv
import io
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, Response
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
    Export all highlights with complete metadata to CSV.
    
    Returns a CSV file with comprehensive data including:
    - Highlight details (id, text, note, favorite, discarded)
    - Book metadata (id, title, author, tags)
    - Timestamps (created_at, updated_at)
    - Highlight-specific tags
    """
    # Query all highlights with their associated books
    statement = (
        select(Highlight, Book)
        .outerjoin(Book, Highlight.book_id == Book.id)
        .order_by(Highlight.created_at.desc())
    )
    results = session.exec(statement).all()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output, quoting=csv.QUOTE_ALL)
    
    # Write header row
    headers = [
        'highlight_id',
        'highlight_text',
        'highlight_note',
        'is_favorited',
        'is_discarded',
        'highlight_created_at',
        'highlight_updated_at',
        'book_id',
        'book_title',
        'book_author',
        'document_tags',
        'book_created_at',
        'book_updated_at',
        'highlight_tags',
        'last_reviewed_at',
        'review_count'
    ]
    writer.writerow(headers)
    
    # Write data rows
    for highlight, book in results:
        # Get highlight-specific tags
        highlight_tags_stmt = (
            select(Tag.name)
            .join(HighlightTag, HighlightTag.tag_id == Tag.id)
            .where(HighlightTag.highlight_id == highlight.id)
        )
        tag_results = session.exec(highlight_tags_stmt).all()
        highlight_tags = ', '.join(tag_results) if tag_results else ''
        
        # Determine favorite status (check both fields for backwards compatibility)
        is_favorited = highlight.is_favorited or (highlight.favorite if hasattr(highlight, 'favorite') and highlight.favorite else False)
        
        row = [
            highlight.id,
            highlight.text or '',
            highlight.note or '',
            'true' if is_favorited else 'false',
            'true' if highlight.is_discarded else 'false',
            highlight.created_at.isoformat() if highlight.created_at else '',
            highlight.updated_at.isoformat() if highlight.updated_at else '',
            book.id if book else '',
            book.title if book else (highlight.source or ''),  # Fallback to source for backwards compatibility
            book.author if book else (highlight.author or ''),  # Fallback to author for backwards compatibility
            book.document_tags if book and book.document_tags else '',
            book.created_at.isoformat() if book and book.created_at else '',
            book.updated_at.isoformat() if book and book.updated_at else '',
            highlight_tags,
            '',  # last_reviewed_at - placeholder for future review tracking
            ''   # review_count - placeholder for future review tracking
        ]
        writer.writerow(row)
    
    # Generate filename with current date
    filename = f"highlights_export_{datetime.now().strftime('%Y%m%d')}.csv"
    
    # Return CSV as downloadable file
    csv_content = output.getvalue()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )
