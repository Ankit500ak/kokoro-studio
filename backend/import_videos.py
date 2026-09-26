"""
Bulk import video templates into the database and storage.

Usage:
    cd backend
    python import_videos.py
"""
import os
import sys
import uuid
import json
import shutil
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# Paths
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_DIR = os.path.join(BACKEND_DIR, "..", "videotemplate")
MEDIA_DIR = os.path.join(BACKEND_DIR, "app", "storage", "media")

def probe_video(filepath: str) -> dict:
    """Use FFprobe to extract video metadata."""
    try:
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            filepath,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        info = {}
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                info["width"] = int(stream.get("width", 0))
                info["height"] = int(stream.get("height", 0))
                info["codec"] = stream.get("codec_name", "")
                # Parse fps from r_frame_rate (e.g. "30/1" or "30000/1001")
                rfr = stream.get("r_frame_rate", "30/1")
                num, den = rfr.split("/")
                info["fps"] = round(int(num) / int(den), 2) if int(den) > 0 else 30.0
                break
        fmt = data.get("format", {})
        info["duration"] = float(fmt.get("duration", 0))
        info["file_size"] = int(fmt.get("size", 0))
        return info
    except Exception as e:
        log.warning(f"FFprobe failed for {filepath}: {e}")
        return {}


def main():
    os.makedirs(MEDIA_DIR, exist_ok=True)

    if not os.path.exists(SOURCE_DIR):
        log.error(f"Source directory not found: {SOURCE_DIR}")
        sys.exit(1)

    # Collect all .mp4 files
    files = sorted([
        f for f in os.listdir(SOURCE_DIR)
        if f.lower().endswith(".mp4")
    ])
    log.info(f"Found {len(files)} video files in {SOURCE_DIR}")

    if not files:
        log.error("No .mp4 files found")
        sys.exit(1)

    # Import via database directly
    sys.path.insert(0, BACKEND_DIR)
    os.environ.setdefault("DATABASE_URL", "sqlite:///./app/storage/kokoro.db")

    from app.core.database import engine, SessionLocal, Base
    from app.core.models import VideoAsset

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    imported = 0
    skipped = 0

    for filename in files:
        # Check if already imported
        existing = db.query(VideoAsset).filter(VideoAsset.original_name == filename).first()
        if existing:
            skipped += 1
            continue

        src_path = os.path.join(SOURCE_DIR, filename)
        asset_id = str(uuid.uuid4())[:8]
        dest_filename = f"{asset_id}.mp4"
        dest_path = os.path.join(MEDIA_DIR, dest_filename)

        # Copy file
        log.info(f"Copying: {filename} -> {dest_filename}")
        shutil.copy2(src_path, dest_path)

        # Probe metadata
        info = probe_video(dest_path)

        # Create database record
        asset = VideoAsset(
            id=asset_id,
            filename=dest_filename,
            original_name=filename,
            storage_key=f"media/{dest_filename}",
            duration=info.get("duration"),
            width=info.get("width"),
            height=info.get("height"),
            fps=info.get("fps"),
            codec=info.get("codec"),
            file_size=info.get("file_size"),
            tags="kinetic sand,asmr,satisfying,relaxing",
            category="broll",
            status="ready",
        )
        db.add(asset)
        imported += 1

        if imported % 10 == 0:
            db.commit()
            log.info(f"  Progress: {imported}/{len(files)} imported")

    db.commit()
    db.close()

    log.info(f"Done! Imported: {imported}, Skipped (already exists): {skipped}")


if __name__ == "__main__":
    main()
