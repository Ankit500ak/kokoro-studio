import os
import re
import subprocess
import json
import random
import platform
import logging
import shutil
import uuid
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Session
from ..core.models import RenderJob, RenderOutput, GeneratedAudio, VideoAsset
from ..core.config import settings
from .timeline_builder import TimelineBuilder
from .caption_engine import CaptionASSGenerator
from .types import RenderTimeline, CaptionCue as TypesCaptionCue

log = logging.getLogger(__name__)


def _copy_to_safe_temp(source_path: str, temp_dir: str) -> str:
    """Copy file to temp dir with a safe UUID filename, return the safe path."""
    ext = os.path.splitext(source_path)[1]
    safe_name = f"{uuid.uuid4().hex}{ext}"
    safe_path = os.path.join(temp_dir, safe_name)
    shutil.copy2(source_path, safe_path)
    return safe_path


log = logging.getLogger(__name__)


class RenderService:
    """Execute the full render pipeline."""

    def __init__(self):
        self.timeline_builder = TimelineBuilder()
        self.render_dir = settings.STORAGE_DIR / "renders"
        self.render_dir.mkdir(parents=True, exist_ok=True)
        self._font_path = self._find_font()

    def _convert_captions_for_manager(self, captions: list[TypesCaptionCue]) -> list:
        """Convert types.CaptionCue to caption_manager.models.CaptionCue."""
        from .caption_manager.models import (
            CaptionCue as ManagerCaptionCue,
            CaptionWord as ManagerCaptionWord,
        )

        result = []
        for i, cue in enumerate(captions):
            words = [
                ManagerCaptionWord(
                    text=w.text,
                    start_ms=w.start_ms,
                    end_ms=w.end_ms,
                )
                for w in cue.words
            ]
            result.append(
                ManagerCaptionCue(
                    id=f"cue_{i}",
                    words=words,
                    start_ms=cue.start_ms,
                    end_ms=cue.end_ms,
                )
            )
        return result

    def _find_font(self) -> str:
        """Find a suitable bold font path cross-platform."""
        system = platform.system()
        candidates = []
        if system == "Windows":
            candidates = [
                "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/bahnschrift.ttf",
                "C:/Windows/Fonts/segoeui.ttf",
            ]
        elif system == "Darwin":
            candidates = [
                "/System/Library/Fonts/Helvetica.ttc",
                "/System/Library/Fonts/SFNSDisplay.ttf",
                "/Library/Fonts/Arial Bold.ttf",
            ]
        else:
            candidates = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
                "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            ]

        for path in candidates:
            if os.path.exists(path):
                return path

        # Fallback: let FFmpeg use its default font
        return ""

    def execute_render(self, job: RenderJob, db: Session):
        """Execute the full render pipeline for a job."""
        try:
            # Update status
            job.status = "rendering"
            job.started_at = datetime.utcnow()
            job.current_stage = "preparing"
            job.progress = 10
            db.commit()

            # Get audio
            audio = (
                db.query(GeneratedAudio)
                .filter(GeneratedAudio.id == job.generated_audio_id)
                .first()
            )
            if not audio:
                self._fail_job(job, "AUDIO_NOT_FOUND", "Audio not found", db)
                return

            # Set random seed for reproducibility
            if job.render_seed is None:
                job.render_seed = random.randint(1, 999999)

            # Build timeline
            job.current_stage = "analyzing_audio"
            job.progress = 20
            db.commit()

            timeline = self.timeline_builder.build_timeline(job, audio, db)

            # Store timeline data
            job.timeline_data = json.dumps(
                {
                    "duration_ms": timeline.duration_ms,
                    "video_count": len(timeline.video),
                    "caption_count": len(timeline.captions),
                }
            )

            # Generate captions using new architecture
            job.current_stage = "building_captions"
            job.progress = 35
            db.commit()

            # Get preset from timeline template
            preset = (
                timeline.template.get("preset", "storytelling")
                if timeline.template
                else "storytelling"
            )

            # Use new CaptionManager for precise timing
            from .caption_manager import CaptionManager, CaptionConfig, SyncMethod
            from .caption_manager.models import CaptionTiming

            timing = CaptionTiming(
                words_per_cue=3,
                lead_ms=0,
                tail_ms=50,
                min_gap_ms=50,
                silence_threshold_ms=250,
            )

            caption_config = CaptionConfig(
                preset=preset,
                timing=timing,
                sync_method=SyncMethod.WHISPER,
            )

            caption_manager = CaptionManager(caption_config)

            # Convert types.CaptionCue to caption_manager.models.CaptionCue
            manager_captions = self._convert_captions_for_manager(timeline.captions)

            # Generate captions from timeline data
            ass_content = caption_manager.get_caption_text(
                manager_captions,
                video_width=1080,
                video_height=1920,
            )

            ass_path = self.render_dir / f"{job.id}.ass"
            with open(ass_path, "w", encoding="utf-8") as f:
                f.write(ass_content)

            # Render video with thumbnail in one pass
            job.current_stage = "rendering"
            job.progress = 55
            db.commit()

            output_filename = f"{job.id}.mp4"
            thumbnail_filename = f"{job.id}_thumb.jpg"
            output_path = self.render_dir / output_filename
            thumbnail_path = self.render_dir / thumbnail_filename

            success = self._render_with_ffmpeg(
                timeline, str(ass_path), str(output_path), str(thumbnail_path), job, db
            )

            if not success:
                detail = getattr(self, "last_ffmpeg_error", None) or ""
                detail = " ".join(detail.split())[:400]
                self._fail_job(
                    job,
                    "RENDER_FAILED",
                    f"FFmpeg rendering failed{': ' + detail if detail else ''}",
                    db,
                )
                return

            # Validate output inline (no separate ffprobe call)
            job.current_stage = "validating_output"
            job.progress = 90
            db.commit()

            if not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
                self._fail_job(job, "VALIDATION_FAILED", "Output file invalid", db)
                return

            # Get file size
            file_size = os.path.getsize(output_path)

            # Create output record
            output = RenderOutput(
                id=str(os.urandom(16).hex()),
                render_job_id=job.id,
                video_filename=output_filename,
                thumbnail_filename=thumbnail_filename
                if os.path.exists(thumbnail_path)
                else None,
                duration=self._effective_duration(timeline, job),
                width=1080,
                height=1920,
                file_size=file_size,
                codec="h264",
            )
            db.add(output)

            # Mark job complete
            job.status = "completed"
            job.progress = 100
            job.current_stage = "completed"
            job.completed_at = datetime.utcnow()
            db.commit()

        except Exception as e:
            self._fail_job(job, "INTERNAL_ERROR", str(e), db)

    @staticmethod
    def _effective_duration(timeline: RenderTimeline, job: RenderJob) -> float:
        """Capped output duration in seconds.

        Legacy Shorts renders stay capped at 119s; long-form jobs lift the cap
        via RenderJob.target_duration (bounded 60-600 by the API schema).
        """
        audio_duration = timeline.duration_ms / 1000
        job_cap = getattr(job, "target_duration", None)
        cap = float(job_cap) if job_cap else settings.RENDER_DEFAULT_MAX_DURATION
        cap = min(cap, settings.RENDER_MAX_DURATION)
        return min(audio_duration, cap)

    def _render_with_ffmpeg(
        self,
        timeline: RenderTimeline,
        ass_path: str,
        output_path: str,
        thumbnail_path: str,
        job: RenderJob,
        db: Session,
    ) -> bool:
        """Render the final video using FFmpeg with thumbnail in one pass."""
        self.last_ffmpeg_error = None
        try:
            # Create temp directory for safe filenames
            temp_dir = self.render_dir / "temp_ffmpeg"
            temp_dir.mkdir(parents=True, exist_ok=True)
            safe_video_paths = []

            try:
                # Build FFmpeg command
                cmd = ["ffmpeg", "-y"]

                # Add video inputs - copy to safe temp names
                valid_video_indices = []
                for i, segment in enumerate(timeline.video):
                    segment_path = str(
                        settings.STORAGE_DIR / "media" / segment.filename
                    )
                    if os.path.exists(segment_path):
                        # Copy to safe temp filename
                        safe_path = _copy_to_safe_temp(segment_path, str(temp_dir))
                        safe_video_paths.append(safe_path)
                        start_sec = segment.source_start_ms / 1000
                        duration_sec = (
                            segment.source_end_ms - segment.source_start_ms
                        ) / 1000
                        cmd.extend(
                            [
                                "-ss",
                                str(start_sec),
                                "-t",
                                str(duration_sec),
                                "-i",
                                safe_path,
                            ]
                        )
                        valid_video_indices.append(i)

                n_video = len(valid_video_indices)

                # Add audio input (always last input) - copy to safe temp
                audio_path = str(settings.AUDIO_DIR / timeline.audio.filename)
                if os.path.exists(audio_path):
                    safe_audio_path = _copy_to_safe_temp(audio_path, str(temp_dir))
                    safe_video_paths.append(safe_audio_path)
                    cmd.extend(["-i", safe_audio_path])
                else:
                    log.error(f"Audio file not found: {audio_path}")
                    return False

                # Build filter complex
                filter_parts = []

                if n_video > 0:
                    # Scale and normalize all video inputs to 1080x1920
                    for idx, i in enumerate(valid_video_indices):
                        filter_parts.append(
                            f"[{idx}:v]scale=1080:1920:force_original_aspect_ratio=decrease,"
                            f"pad=1080:1920:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30[v{idx}]"
                        )

                    # Concatenate video segments
                    concat_input = "".join(f"[v{i}]" for i in range(n_video))
                    filter_parts.append(
                        f"{concat_input}concat=n={n_video}:v=1:a=0[vconcat]"
                    )
                    current_video = "vconcat"
                else:
                    # No video clips available - generate a black canvas as background
                    duration_sec = timeline.duration_ms / 1000
                    filter_parts.append(
                        f"color=c=black:s=1080x1920:d={duration_sec}:r=30[bg]"
                    )
                    current_video = "bg"

                # Add title overlay if present
                if timeline.title:
                    title_text = timeline.title.text
                    # Escape all FFmpeg drawtext special characters
                    for ch in ["\\", "'", '"', ":", "%", "$", "[", "]", ";"]:
                        title_text = title_text.replace(ch, f"\\{ch}")
                    title_text = title_text.replace("\n", " ")
                    font_filter = (
                        f":fontfile='{self._font_path}'" if self._font_path else ""
                    )
                    filter_parts.append(
                        f"[{current_video}]drawtext=text='{title_text}':"
                        f"fontcolor={timeline.title.color}:fontsize=64"
                        f"{font_filter}:"
                        f"x=(w-text_w)/2:y=100:"
                        f"borderw=4:bordercolor=black[vtitle]"
                    )
                    current_video = "vtitle"

                # Escape ASS path for FFmpeg filter - handle Windows paths
                ass_escaped = (
                    ass_path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
                )
                filter_parts.append(f"[{current_video}]ass='{ass_escaped}'[vout]")

                # Map outputs
                filter_complex = ";".join(filter_parts)

                # Calculate total duration: long-form jobs lift the legacy
                # 119s Shorts cap via job.target_duration (60-600s).
                total_duration = self._effective_duration(timeline, job)
                log.info(
                    f"[Render] Video duration: {total_duration:.1f}s "
                    f"(audio {timeline.duration_ms / 1000:.1f}s)"
                )

                if total_duration > settings.RENDER_DEFAULT_MAX_DURATION:
                    # Long video: rate-limit to keep the file under Telegram's
                    # bot upload limit (~45MB budget incl. 128k audio).
                    video_kbps = max(
                        500,
                        int(
                            settings.RENDER_TELEGRAM_MAX_MB * 8192 / total_duration
                            - 128
                        ),
                    )
                    encode_args = [
                        "-b:v",
                        f"{video_kbps}k",
                        "-maxrate",
                        f"{int(video_kbps * 1.3)}k",
                        "-bufsize",
                        f"{video_kbps * 2}k",
                        "-preset",
                        "veryfast",
                    ]
                    log.info(
                        f"[Render] Long video: targeting {video_kbps}k video bitrate "
                        f"(~{settings.RENDER_TELEGRAM_MAX_MB:.0f}MB budget)"
                    )
                else:
                    encode_args = ["-crf", "23", "-preset", "ultrafast"]

                cmd.extend(
                    [
                        "-filter_complex",
                        filter_complex,
                        "-map",
                        "[vout]",
                        "-map",
                        f"{n_video}:a",
                        "-c:v",
                        "libx264",
                        *encode_args,
                        "-c:a",
                        "aac",
                        "-b:a",
                        "128k",
                        "-t",
                        str(total_duration),  # Explicit duration instead of -shortest
                        "-movflags",
                        "+faststart",
                        output_path,
                    ]
                )

                # Execute FFmpeg with longer timeout (scale with video duration).
                # Long rate-limited encodes at 1080x1920 run much slower than
                # realtime-capable ultrafast shorts, so allow 2 minutes per
                # minute of video on top of a 10 minute floor.
                video_duration_min = total_duration / 60
                timeout_seconds = max(600, int(600 + video_duration_min * 120))
                log.info(
                    f"[Render] FFmpeg timeout set to {timeout_seconds}s for {total_duration:.1f}s video"
                )
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout_seconds,
                )

                if result.returncode != 0:
                    # Progress spam crowds the tail; keep the full stderr for
                    # post-mortem (the real fatal line is usually mid-stream).
                    stderr_log = self.render_dir / f"{job.id}.ffmpeg.log"
                    try:
                        with open(stderr_log, "w", encoding="utf-8") as f:
                            f.write(result.stderr or "")
                        log.error(f"[Render] Full FFmpeg stderr: {stderr_log}")
                    except OSError:
                        pass
                    self.last_ffmpeg_error = (result.stderr or "")[-1500:]
                    log.error(f"FFmpeg stderr: {result.stderr[-500:]}")
                    return False

                # Generate thumbnail in a quick separate call (1 second)
                try:
                    thumb_cmd = [
                        "ffmpeg",
                        "-y",
                        "-i",
                        output_path,
                        "-ss",
                        "00:00:01",
                        "-vframes",
                        "1",
                        "-vf",
                        "scale=1080:1920",
                        thumbnail_path,
                    ]
                    subprocess.run(thumb_cmd, capture_output=True, timeout=15)
                except Exception:
                    pass  # Thumbnail is optional

                return os.path.exists(output_path)

            finally:
                # Clean up temp files
                for safe_path in safe_video_paths:
                    try:
                        if os.path.exists(safe_path):
                            os.remove(safe_path)
                    except OSError:
                        pass

        except (subprocess.TimeoutExpired, Exception) as e:
            self.last_ffmpeg_error = str(e)
            log.error(f"FFmpeg error: {e}")
            return False

    def _fail_job(
        self, job: RenderJob, error_code: str, error_message: str, db: Session
    ):
        """Mark a job as failed and clean up partial files."""
        job.status = "failed"
        job.error_code = error_code
        job.error_message = error_message
        job.completed_at = datetime.utcnow()
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            log.exception(f"Failed to update job {job.id} status")

        for ext in [".mp4", ".ass", "_thumb.jpg"]:
            partial = self.render_dir / f"{job.id}{ext}"
            if partial.exists():
                try:
                    os.remove(partial)
                except OSError:
                    pass


render_service = RenderService()
