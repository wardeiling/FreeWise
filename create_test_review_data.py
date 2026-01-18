"""
Create test review sessions to visualize the heatmap and streaks.
Run this to populate some sample data.
"""
from datetime import datetime, date, timedelta
from sqlmodel import Session, select
from app.db import get_engine
from app.models import ReviewSession
import uuid

def create_test_sessions():
    """Create test review sessions for demonstration."""
    engine = get_engine()
    
    with Session(engine) as session:
        # Check if we already have test data
        stmt = select(ReviewSession)
        existing = session.exec(stmt).all()
        
        if existing:
            print(f"⚠️  Found {len(existing)} existing sessions.")
            response = input("Delete all and create test data? (yes/no): ")
            if response.lower() != 'yes':
                print("Cancelled.")
                return
            
            # Delete existing
            for s in existing:
                session.delete(s)
            session.commit()
            print("✅ Deleted existing sessions.")
        
        today = date.today()
        now = datetime.utcnow()
        
        # Create a realistic pattern:
        # - 7 day streak ending 10 days ago
        # - Skip 2 days
        # - 5 day current streak (ending today)
        
        sessions_to_create = []
        
        # Past 7-day streak (17 to 11 days ago)
        for i in range(7):
            session_date = today - timedelta(days=17 - i)
            sessions_to_create.append({
                'date': session_date,
                'reviewed': 5,
                'discarded': 1,
                'favorited': 2
            })
        
        # Current 5-day streak (last 5 days including today)
        for i in range(5):
            session_date = today - timedelta(days=4 - i)
            sessions_to_create.append({
                'date': session_date,
                'reviewed': 5,
                'discarded': 0 if i % 2 == 0 else 1,
                'favorited': 1 if i % 3 == 0 else 2
            })
        
        # Create the sessions
        for data in sessions_to_create:
            review_session = ReviewSession(
                user_id=1,
                session_uuid=str(uuid.uuid4()),
                started_at=datetime.combine(data['date'], datetime.min.time()),
                completed_at=datetime.combine(data['date'], datetime.min.time()) + timedelta(minutes=5),
                session_date=data['date'],
                target_count=5,
                highlights_reviewed=data['reviewed'],
                highlights_discarded=data['discarded'],
                highlights_favorited=data['favorited'],
                is_completed=True
            )
            session.add(review_session)
        
        session.commit()
        print(f"✅ Created {len(sessions_to_create)} test review sessions!")
        print()
        print("Session breakdown:")
        print(f"  - 7-day streak: {(today - timedelta(days=17)).strftime('%b %d')} to {(today - timedelta(days=11)).strftime('%b %d')}")
        print(f"  - Gap: 2 days")
        print(f"  - 5-day current streak: {(today - timedelta(days=4)).strftime('%b %d')} to {today.strftime('%b %d')} (today)")
        print()
        print("Expected results:")
        print("  - Current Streak: 5 days")
        print("  - Longest Streak: 7 days")
        print()
        print("Visit the dashboard to see the visualization!")

if __name__ == "__main__":
    create_test_sessions()
