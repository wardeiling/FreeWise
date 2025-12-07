import os
import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

from app.main import app
from app.models import Highlight, User
from app.routers.highlights import get_session


# Create test database
TEST_DB_URL = "sqlite:///./test_freewise.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})


def get_test_session():
    """Override database session for testing."""
    with Session(test_engine) as session:
        yield session


app.dependency_overrides[get_session] = get_test_session
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_database():
    """Create tables before each test and drop after."""
    SQLModel.metadata.create_all(test_engine)
    
    # Create a test user
    with Session(test_engine) as session:
        user = User(
            email="test@example.com",
            password_hash="test_hash"
        )
        session.add(user)
        session.commit()
    
    yield
    
    SQLModel.metadata.drop_all(test_engine)
    test_engine.dispose()  # Close all connections
    if os.path.exists("test_freewise.db"):
        os.remove("test_freewise.db")


def test_review_endpoint_returns_five_highlights():
    """Test that /review returns up to 5 highlights and excludes discarded ones."""
    now = datetime.utcnow()
    
    # Create 8 highlights with varied next_review times
    highlights_data = [
        {"text": "Past review 1", "source": "Book A", "next_review": (now - timedelta(days=5)).isoformat()},
        {"text": "Past review 2", "source": "Book B", "next_review": (now - timedelta(days=2)).isoformat()},
        {"text": "Due now", "source": "Book C", "next_review": now.isoformat()},
        {"text": "Future review 1", "source": "Book D", "next_review": (now + timedelta(days=3)).isoformat()},
        {"text": "Future review 2", "source": "Book E", "next_review": (now + timedelta(days=7)).isoformat()},
        {"text": "No review set", "source": "Book F", "next_review": None},
        {"text": "Another no review", "source": "Book G", "next_review": None},
        {"text": "Discarded highlight", "source": "Book H", "next_review": (now - timedelta(days=1)).isoformat()},
    ]
    
    created_ids = []
    for data in highlights_data:
        response = client.post("/highlights/", json=data)
        assert response.status_code == 200
        created_ids.append(response.json()["id"])
    
    # Discard the last highlight
    discard_response = client.post(f"/highlights/{created_ids[-1]}/discard")
    assert discard_response.status_code == 200
    assert discard_response.json()["status"] == "discarded"
    
    # Get review highlights
    review_response = client.get("/highlights/review/?n=5")
    assert review_response.status_code == 200
    
    review_highlights = review_response.json()
    assert len(review_highlights) == 5
    
    # Assert none are discarded
    for highlight in review_highlights:
        assert highlight["status"] == "active"
        assert highlight["id"] != created_ids[-1]  # Not the discarded one


def test_create_and_toggle_favorite():
    """Test creating a highlight and toggling its favorite status."""
    # Create a highlight
    highlight_data = {
        "text": "This is a favorite highlight",
        "source": "Important Book"
    }
    
    create_response = client.post("/highlights/", json=highlight_data)
    assert create_response.status_code == 200
    
    created_highlight = create_response.json()
    assert created_highlight["text"] == highlight_data["text"]
    assert created_highlight["favorite"] is False
    
    highlight_id = created_highlight["id"]
    
    # Toggle favorite to True
    favorite_response = client.post(
        f"/highlights/{highlight_id}/favorite",
        json={"favorite": True}
    )
    assert favorite_response.status_code == 200
    assert favorite_response.json()["favorite"] is True
    
    # Verify by fetching the highlight
    get_response = client.get(f"/highlights/{highlight_id}")
    assert get_response.status_code == 200
    assert get_response.json()["favorite"] is True
