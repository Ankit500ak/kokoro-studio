import random
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict
from sqlalchemy.orm import Session
from ..core.models import VideoAsset
from .types import SelectedClip

log = logging.getLogger(__name__)


class ClipSelector:
    """Select B-roll video clips to match audio duration.

    Strategy: use 5-30 second clips with variety across folders.
    Mix clips from different folders to avoid repetition and copyright.
    """

    def __init__(self):
        self.min_clip_duration_ms = 3000    # 3 seconds minimum per clip
        self.max_clip_duration_ms = 30000   # 30 seconds maximum per clip
        self.max_per_folder_ms = 40000      # 40 seconds max per folder
        self.min_total_ms = 5000            # 5 seconds minimum
        self.max_total_ms = 119000          # 119 seconds max (2 min Shorts)

    def select_clips(
        self,
        db: Session,
        target_duration_ms: float,
        exclude_ids: Optional[List[str]] = None,
        seed: Optional[int] = None,
        folder_filter: Optional[List[str]] = None,
    ) -> List[SelectedClip]:
        """Select clips to fill the target duration.

        Rules:
        - Short clips (5-25 seconds) for variety and copyright safety
        - Max 30 seconds from each folder
        - Never exceed 5 minutes total
        - Mix different folders for variety
        - Never repeat the same clip twice
        """
        rng = random.Random(seed)

        query = db.query(VideoAsset).filter(
            VideoAsset.status == "ready",
            VideoAsset.duration.isnot(None),
            VideoAsset.duration >= 2.0,
        )
        if exclude_ids:
            query = query.filter(~VideoAsset.id.in_(exclude_ids))
        if folder_filter:
            query = query.filter(VideoAsset.folder.in_(folder_filter))

        assets = query.order_by(VideoAsset.usage_count.asc()).all()
        if not assets:
            log.warning("ClipSelector: no ready assets found")
            return []

        # Group by folder
        folder_map: Dict[str, list] = {}
        for a in assets:
            folder = a.folder or "unknown"
            folder_map.setdefault(folder, []).append(a)

        log.info(f"ClipSelector: {len(assets)} assets in {len(folder_map)} folders: {list(folder_map.keys())}")

        # When filtering to a single folder, remove the per-folder limit
        # Otherwise, scale per-folder limit based on target duration
        if folder_filter and len(folder_filter) == 1:
            effective_max_per_folder = target_duration_ms
        else:
            # Allow more per-folder for longer videos (up to 2 min per folder)
            effective_max_per_folder = min(target_duration_ms * 0.4, 120000)

        # Use actual target duration with minimum bound
        target_ms = max(self.min_total_ms, target_duration_ms)

        # Shuffle folder order for variety
        folder_names = list(folder_map.keys())
        rng.shuffle(folder_names)

        selected = []
        current_ms = 0.0
        folder_used_ms: Dict[str, float] = {f: 0.0 for f in folder_names}
        last_asset_id = None
        max_attempts = len(assets) * 5  # More attempts to find diverse clips
        attempts = 0

        while current_ms < target_ms and attempts < max_attempts:
            attempts += 1

            # Pick a folder that still has capacity
            available_folders = [
                f for f in folder_names
                if folder_used_ms[f] < effective_max_per_folder
            ]
            if not available_folders:
                break

            folder = rng.choice(available_folders)
            candidates = [
                a for a in folder_map[folder]
                if a.id != last_asset_id
            ]
            if not candidates:
                candidates = folder_map[folder]

            weights = [1.0 / (a.usage_count + 1) for a in candidates]
            total_weight = sum(weights)
            probabilities = [w / total_weight for w in weights]

            asset = rng.choices(candidates, weights=probabilities, k=1)[0]

            asset_duration_ms = asset.duration * 1000
            remaining_ms = target_ms - current_ms
            folder_remaining_ms = effective_max_per_folder - folder_used_ms[folder]

            # Prefer shorter clips for variety (3-6 seconds)
            ideal_clip_ms = rng.uniform(self.min_clip_duration_ms, self.max_clip_duration_ms)
            clip_duration_ms = min(ideal_clip_ms, asset_duration_ms, remaining_ms, folder_remaining_ms)

            if clip_duration_ms < self.min_clip_duration_ms:
                clip_duration_ms = min(self.min_clip_duration_ms, asset_duration_ms)
                clip_duration_ms = min(clip_duration_ms, remaining_ms, folder_remaining_ms)

            if clip_duration_ms <= 0:
                continue

            if asset_duration_ms > clip_duration_ms:
                max_start = asset_duration_ms - clip_duration_ms
                source_start = rng.uniform(0, max_start)
            else:
                source_start = 0

            source_end = source_start + clip_duration_ms

            selected.append(SelectedClip(
                asset_id=asset.id,
                filename=asset.filename,
                source_start_ms=source_start,
                source_end_ms=source_end,
                timeline_start_ms=current_ms,
                timeline_end_ms=current_ms + clip_duration_ms,
            ))

            asset.usage_count += 1
            asset.last_used_at = datetime.now(timezone.utc)

            current_ms += clip_duration_ms
            folder_used_ms[folder] += clip_duration_ms
            last_asset_id = asset.id

        folder_summary = {f: f"{v/1000:.1f}s" for f, v in folder_used_ms.items() if v > 0}
        log.info(f"ClipSelector: selected {len(selected)} clips, total {current_ms/1000:.1f}s")
        log.info(f"ClipSelector: per folder: {folder_summary}")

        try:
            db.commit()
        except Exception as e:
            db.rollback()
            log.exception("Failed to update clip usage counts")

        return selected
