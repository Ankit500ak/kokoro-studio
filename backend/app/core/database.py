import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import StaticPool
from pathlib import Path

log = logging.getLogger(__name__)

DB_DIR = Path(__file__).parent.parent / "storage"
DB_PATH = DB_DIR / "kokoro.db"
DB_URL = f"sqlite:///{DB_PATH.as_posix()}"

engine = create_engine(
    DB_URL,
    connect_args={"check_same_thread": False},
    pool_pre_ping=True,
    poolclass=StaticPool,
)

@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    from . import models
    Base.metadata.create_all(bind=engine)
    _migrate_db()


def _migrate_db():
    """Add missing columns to existing tables."""
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    try:
        # Check if video_folder column exists on render_jobs
        cursor.execute("PRAGMA table_info(render_jobs)")
        columns = {row[1] for row in cursor.fetchall()}
        if "video_folder" not in columns:
            cursor.execute("ALTER TABLE render_jobs ADD COLUMN video_folder VARCHAR")
            log.info("Migration: added video_folder column to render_jobs")
        conn.commit()
    except Exception as e:
        log.warning(f"Migration skipped: {e}")
    finally:
        conn.close()
