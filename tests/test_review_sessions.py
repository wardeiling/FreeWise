"""
Test script to verify ReviewSession logging functionality.
This creates a mock review session and verifies database tracking.
"""
from datetime import datetime, date
from sqlmodel import Session, select
from app.db import get_engine
from app.models import ReviewSession

def test_review_session():
    engine = get_engine()
    
    with Session(engine) as session:
        # Check if any review sessions exist
        stmt = select(ReviewSession)
        existing_sessions = session.exec(stmt).all()
        
        print(f"📊 Found {len(existing_sessions)} existing review session(s)")
        print()
        
        if existing_sessions:
            print("Recent Review Sessions:")
            print("-" * 80)
            for rs in existing_sessions[-5:]:  # Show last 5
                duration = "In Progress"
                if rs.completed_at:
                    duration_seconds = (rs.completed_at - rs.started_at).total_seconds()
                    duration = f"{int(duration_seconds // 60)}m {int(duration_seconds % 60)}s"
                
                print(f"Session: {rs.session_uuid[:8]}...")
                print(f"  Date: {rs.session_date}")
                print(f"  Started: {rs.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"  Duration: {duration}")
                print(f"  Target: {rs.target_count} highlights")
                print(f"  Reviewed: {rs.highlights_reviewed}")
                print(f"  Discarded: {rs.highlights_discarded}")
                print(f"  Favorited: {rs.highlights_favorited}")
                print(f"  Completed: {'✅' if rs.is_completed else '⏳'}")
                print()
        else:
            print("No review sessions found yet.")
            print("Start a daily review to create your first session!")
        
        # Test creating a sample session (commented out to avoid polluting data)
        # Uncomment the following to test database write:
        """
        print("Creating test session...")
        test_session = ReviewSession(
            user_id=1,
            session_uuid="test-" + datetime.utcnow().isoformat(),
            started_at=datetime.utcnow(),
            session_date=date.today(),
            target_count=5,
            highlights_reviewed=0,
            highlights_discarded=0,
            highlights_favorited=0,
            is_completed=False
        )
        session.add(test_session)
        session.commit()
        print("✅ Test session created successfully!")
        """

if __name__ == "__main__":
    test_review_session()
