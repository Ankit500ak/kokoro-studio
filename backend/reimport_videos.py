"""
Re-import videos from subfolders with folder tracking.
Scans: odlysatisfy, sandsatisfy, sandsound, SandTagious, stablesatisfaction
"""
import os
import sys
import uuid
import shutil
import subprocess
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("reimport")

MEDIA_DIR = os.path.join(os.path.dirname(__file__), "app", "storage", "media")
FOLDERS = ["odlysatisfy", "sandsatisfy", "sandsound", "SandTagious", "stablesatisfaction"]

sys.path.insert(0, os.path.dirname(__file__))
from app.core.database import SessionLocal
from app.core.models import VideoAsset


def probe_video(path):
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", path],
            capture_output=True, text=True, timeout=30
        )
        import json
        data = json.loads(result.stdout)
        fmt = data.get("format", {})
        stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
        return {
            "duration": float(fmt.get("duration", 0)),
            "width": int(stream.get("width", 0)),
            "height": int(stream.get("height", 0)),
            "fps": eval(stream.get("r_frame_rate", "0/1")) if "/" in stream.get("r_frame_rate", "") else float(stream.get("r_frame_rate", 0)),
            "codec": stream.get("codec_name", ""),
            "file_size": int(fmt.get("size", 0)),
        }
    except Exception as e:
        log.warning(f"Probe failed for {path}: {e}")
        return {"duration": 0, "width": 0, "height": 0, "fps": 0, "codec": "", "file_size": 0}


def main():
    db = SessionLocal()

    # Clear existing assets
    existing = db.query(VideoAsset).count()
    if existing > 0:
        log.info(f"Clearing {existing} existing assets...")
        db.query(VideoAsset).delete()
        db.commit()

    imported = 0
    skipped = 0

    for folder_name in FOLDERS:
        folder_path = os.path.join(MEDIA_DIR, folder_name)
        if not os.path.isdir(folder_path):
            log.warning(f"Folder not found: {folder_path}")
            continue

        files = [f for f in os.listdir(folder_path) if f.lower().endswith(".mp4")]
        log.info(f"Scanning {folder_name}: {len(files)} mp4 files")

        for filename in files:
            src_path = os.path.join(folder_path, filename)

            # Generate UUID name
            asset_id = str(uuid.uuid4())[:8]
            dest_filename = f"{asset_id}.mp4"
            dest_path = os.path.join(MEDIA_DIR, dest_filename)

            # Copy file to media root
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
                tags=f"asmr,satisfying,{folder_name}",
                category="broll",
                folder=folder_name,
                status="ready",
            )
            db.add(asset)
            imported += 1

            if imported % 10 == 0:
                db.commit()
                log.info(f"  Progress: {imported} imported")

    db.commit()
    db.close()

    log.info(f"Done! Imported: {imported}")


if __name__ == "__main__":
    main()
