"""
Theme Tracker
Tracks used themes to prevent story repetition.
Uses SQLite database for persistent storage.
"""
import logging
import uuid
from difflib import SequenceMatcher
from sqlalchemy.orm import Session

from ..core.models import UsedTheme
from ..core.database import SessionLocal

log = logging.getLogger(__name__)


def normalize_theme(theme: str) -> str:
    """Normalize theme text for comparison — lowercase, strip extra spaces."""
    return theme.strip().lower()


def themes_similar(t1: str, t2: str, threshold: float = 0.75) -> bool:
    """Check if two themes are too similar (fuzzy matching)."""
    t1 = normalize_theme(t1)
    t2 = normalize_theme(t2)
    if t1 == t2:
        return True
    return SequenceMatcher(None, t1, t2).ratio() >= threshold


def is_theme_used(theme: str, db: Session | None = None) -> bool:
    """Check if a theme (or very similar theme) has been used before."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        normalized = normalize_theme(theme)
        existing = db.query(UsedTheme).all()
        for record in existing:
            if themes_similar(normalized, record.theme):
                log.info(f"[ThemeTracker] Duplicate detected: '{theme}' ~ '{record.theme}'")
                return True
        return False
    finally:
        if close_db:
            db.close()


def mark_theme_used(
    theme: str,
    session_id: str = "",
    quality_score: float = 0,
    category: str = "",
    db: Session | None = None,
) -> UsedTheme:
    """Record a theme as used after successful generation."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        record = UsedTheme(
            id=str(uuid.uuid4())[:12],
            theme=normalize_theme(theme),
            session_id=session_id,
            quality_score=quality_score,
            category=category,
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        log.info(f"[ThemeTracker] Theme marked as used: '{theme[:60]}'")
        return record
    except Exception as e:
        db.rollback()
        log.error(f"[ThemeTracker] Failed to mark theme: {e}")
        raise
    finally:
        if close_db:
            db.close()


def get_used_count(db: Session | None = None) -> int:
    """Get total number of unique themes used."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        return db.query(UsedTheme).count()
    finally:
        if close_db:
            db.close()


def get_recent_themes(limit: int = 20, db: Session | None = None) -> list[dict]:
    """Get recently used themes."""
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True
    try:
        records = (
            db.query(UsedTheme)
            .order_by(UsedTheme.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "theme": r.theme,
                "session_id": r.session_id,
                "quality_score": r.quality_score,
                "category": r.category,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ]
    finally:
        if close_db:
            db.close()


def get_random_unused_theme(themes: list[str]) -> str | None:
    """From a list of themes, return one that hasn't been used yet.
    Returns None if all themes are used."""
    import random
    unused = [t for t in themes if not is_theme_used(t)]
    if not unused:
        return None
    return random.choice(unused)
