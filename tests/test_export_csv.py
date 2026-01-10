import csv
import io
import pytest
from datetime import datetime
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine, SQLModel
from sqlmodel.pool import StaticPool

from app.main import app
from app.db import get_engine
from app.models import Book, Highlight, Tag, HighlightTag, Settings


# Test database setup
@pytest.fixture(name="session")
def session_fixture():
    """Create a test database session."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    
    with Session(engine) as session:
        # Create default settings
        settings = Settings()
        session.add(settings)
        session.commit()
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    """Create a test client with overridden database dependency."""
    def get_session_override():
        return session

    app.dependency_overrides[get_engine] = lambda: session.bind
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def test_export_csv_endpoint_exists(client: TestClient):
    """Test that the export CSV endpoint returns 200."""
    response = client.get("/export/csv")
    assert response.status_code == 200


def test_export_csv_content_type(client: TestClient):
    """Test that the export returns text/csv content type."""
    response = client.get("/export/csv")
    assert response.headers["content-type"] == "text/csv; charset=utf-8"


def test_export_csv_has_attachment_header(client: TestClient):
    """Test that the export has Content-Disposition attachment header."""
    response = client.get("/export/csv")
    assert "content-disposition" in response.headers
    assert "attachment" in response.headers["content-disposition"]
    assert "freewise_export_" in response.headers["content-disposition"]
    assert ".csv" in response.headers["content-disposition"]


def test_export_csv_headers(client: TestClient):
    """Test that the CSV includes all expected column headers in Readwise-compatible order."""
    response = client.get("/export/csv")
    
    # Parse CSV
    csv_text = response.text
    reader = csv.reader(io.StringIO(csv_text))
    headers = next(reader)
    
    expected_headers = [
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
        'is_discarded'
    ]
    
    assert headers == expected_headers


def test_export_csv_with_sample_data(session: Session, client: TestClient):
    """Test that CSV export includes correct data for sample book and highlights."""
    # Create a sample book
    book = Book(
        title="Test Book",
        author="Test Author",
        document_tags="philosophy, science"
    )
    session.add(book)
    session.commit()
    session.refresh(book)
    
    # Create sample highlights
    highlight1 = Highlight(
        text="This is a test highlight",
        note="This is a test note",
        book_id=book.id,
        is_favorited=True,
        is_discarded=False,
        created_at=datetime(2024, 1, 15, 10, 30, 0),
        updated_at=datetime(2024, 1, 15, 10, 30, 0)
    )
    
    highlight2 = Highlight(
        text="Another test highlight",
        note="",
        book_id=book.id,
        is_favorited=False,
        is_discarded=True,
        created_at=datetime(2024, 1, 16, 14, 45, 0),
        updated_at=datetime(2024, 1, 16, 14, 45, 0)
    )
    
    session.add(highlight1)
    session.add(highlight2)
    session.commit()
    
    # Export CSV
    response = client.get("/export/csv")
    
    # Parse CSV
    csv_text = response.text
    reader = csv.DictReader(io.StringIO(csv_text))
    rows = list(reader)
    
    # Should have 2 rows (2 highlights)
    assert len(rows) == 2
    
    # Check first highlight (most recent first, so highlight2)
    row1 = rows[0]
    assert row1['Highlight'] == "Another test highlight"
    assert row1['Note'] == ""
    assert row1['is_favorited'] == "false"
    assert row1['is_discarded'] == "true"
    assert row1['Book Title'] == "Test Book"
    assert row1['Book Author'] == "Test Author"
    assert row1['Document tags'] == "philosophy, science"
    assert "2024-01-16" in row1['Highlighted at']
    
    # Check second highlight
    row2 = rows[1]
    assert row2['Highlight'] == "This is a test highlight"
    assert row2['Note'] == "This is a test note"
    assert row2['is_favorited'] == "true"
    assert row2['is_discarded'] == "false"
    assert row2['Book Title'] == "Test Book"
    assert row2['Book Author'] == "Test Author"
    assert "2024-01-15" in row2['Highlighted at']


def test_export_csv_favorite_discarded_fields(session: Session, client: TestClient):
    """Test that favorited and discarded fields export correctly."""
    # Create highlights with different states
    book = Book(title="Test Book", author="Test Author")
    session.add(book)
    session.commit()
    session.refresh(book)
    
    h1 = Highlight(text="Favorited", book_id=book.id, is_favorited=True, is_discarded=False)
    h2 = Highlight(text="Discarded", book_id=book.id, is_favorited=False, is_discarded=True)
    h3 = Highlight(text="Both", book_id=book.id, is_favorited=True, is_discarded=True)
    h4 = Highlight(text="Neither", book_id=book.id, is_favorited=False, is_discarded=False)
    
    session.add_all([h1, h2, h3, h4])
    session.commit()
    
    # Export and check
    response = client.get("/export/csv")
    reader = csv.DictReader(io.StringIO(response.text))
    rows = list(reader)
    
    assert len(rows) == 4
    
    # Find each row by text
    rows_by_text = {row['Highlight']: row for row in rows}
    
    assert rows_by_text['Favorited']['is_favorited'] == 'true'
    assert rows_by_text['Favorited']['is_discarded'] == 'false'
    
    assert rows_by_text['Discarded']['is_favorited'] == 'false'
    assert rows_by_text['Discarded']['is_discarded'] == 'true'
    
    assert rows_by_text['Both']['is_favorited'] == 'true'
    assert rows_by_text['Both']['is_discarded'] == 'true'
    
    assert rows_by_text['Neither']['is_favorited'] == 'false'
    assert rows_by_text['Neither']['is_discarded'] == 'false'


def test_export_csv_with_highlight_tags(session: Session, client: TestClient):
    """Test that highlight-specific tags are exported correctly."""
    # Create book and highlight
    book = Book(title="Test Book", author="Test Author")
    session.add(book)
    session.commit()
    session.refresh(book)
    
    highlight = Highlight(text="Tagged highlight", book_id=book.id)
    session.add(highlight)
    session.commit()
    session.refresh(highlight)
    
    # Create tags and associate with highlight
    tag1 = Tag(name="important")
    tag2 = Tag(name="review-later")
    session.add_all([tag1, tag2])
    session.commit()
    
    # Link tags to highlight
    ht1 = HighlightTag(highlight_id=highlight.id, tag_id=tag1.id)
    ht2 = HighlightTag(highlight_id=highlight.id, tag_id=tag2.id)
    session.add_all([ht1, ht2])
    session.commit()
    
    # Export and check
    response = client.get("/export/csv")
    reader = csv.DictReader(io.StringIO(response.text))
    rows = list(reader)
    
    assert len(rows) == 1
    
    # Check tags are in CSV (order may vary)
    highlight_tags = rows[0]['Tags']
    assert 'important' in highlight_tags
    assert 'review-later' in highlight_tags


def test_export_csv_without_book(session: Session, client: TestClient):
    """Test that highlights without books still export with fallback data."""
    # Create highlight without book (legacy data)
    highlight = Highlight(
        text="Orphan highlight",
        source="Legacy Source",
        author="Legacy Author",
        note="Legacy note"
    )
    session.add(highlight)
    session.commit()
    
    # Export and check
    response = client.get("/export/csv")
    reader = csv.DictReader(io.StringIO(response.text))
    rows = list(reader)
    
    assert len(rows) == 1
    assert rows[0]['Highlight'] == "Orphan highlight"
    assert rows[0]['book_id'] == ""
    assert rows[0]['Book Title'] == "Legacy Source"
    assert rows[0]['Book Author'] == "Legacy Author"
    assert rows[0]['Note'] == "Legacy note"


def test_export_csv_empty_database(client: TestClient):
    """Test that export works even with no data."""
    response = client.get("/export/csv")
    assert response.status_code == 200
    
    # Should still have headers
    reader = csv.reader(io.StringIO(response.text))
    headers = next(reader)
    assert len(headers) > 0
    
    # But no data rows
    rows = list(reader)
    assert len(rows) == 0
