import os
from sqlmodel import create_engine, SQLModel, Session, select

# Module-level engine singleton — created once when the module is first imported.
_engine = create_engine(
    os.getenv("FREEWISE_DB_URL", "sqlite:///./db/freewise.db"),
    echo=False,
    connect_args={"check_same_thread": False},
)


def get_engine():
    """Return the module-level SQLAlchemy engine singleton."""
    return _engine


def get_session():
    """FastAPI dependency that yields a database session."""
    with Session(_engine) as session:
        yield session


def get_settings(session: Session):
    """Return the single Settings record, creating defaults if absent."""
    from app.models import Settings
    settings = session.exec(select(Settings)).first()
    if not settings:
        settings = Settings()
        session.add(settings)
        session.commit()
        session.refresh(settings)
    if settings.highlight_recency is None:
        settings.highlight_recency = 5
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings


def get_current_streak(session: Session) -> int:
    """Return the current consecutive-day review streak (0 if no active streak).

    A streak is alive if a completed session exists for today or yesterday.
    Multiple sessions on the same calendar day count as one streak day.
    """
    from app.models import ReviewSession
    from datetime import date, timedelta

    today = date.today()
    completed_stmt = select(ReviewSession).where(ReviewSession.is_completed == True)
    completed_sessions = session.exec(completed_stmt).all()

    if not completed_sessions:
        return 0

    # Deduplicate: multiple sessions on the same day count as one streak day
    sorted_dates = sorted({rs.session_date for rs in completed_sessions}, reverse=True)
    yesterday = today - timedelta(days=1)

    # Streak must start from today or yesterday to be "current"
    if sorted_dates[0] < yesterday:
        return 0

    streak = 1
    check_date = sorted_dates[0] - timedelta(days=1)
    for d in sorted_dates[1:]:
        if d == check_date:
            streak += 1
            check_date -= timedelta(days=1)
        else:
            break

    return streak
