"""
Caption Cache
=============

Caching system for processed captions to improve performance.

This cache handles:
1. In-memory caching with TTL
2. Audio hash-based cache keys
3. Cache invalidation
4. Cache statistics
"""

import time
import hashlib
import logging
from typing import List, Optional, Dict
from .models import (
    CaptionCue,
    CaptionSegment,
    CaptionCacheEntry,
)

log = logging.getLogger(__name__)


class CaptionCache:
    """
    Cache for processed captions.
    
    Uses audio content hash as cache key to avoid
    re-processing the same audio files.
    """
    
    DEFAULT_TTL = 3600  # 1 hour
    
    def __init__(self, ttl_seconds: int = DEFAULT_TTL):
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, CaptionCacheEntry] = {}
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
        }
    
    def get(
        self,
        audio_path: str,
        text: str,
    ) -> Optional[List[CaptionCue]]:
        """
        Get cached captions for audio/text combination.
        
        Args:
            audio_path: Path to audio file
            text: Original text
            
        Returns:
            Cached cues if found and valid, None otherwise
        """
        cache_key = self._generate_key(audio_path, text)
        
        entry = self._cache.get(cache_key)
        if entry is None:
            self._stats["misses"] += 1
            return None
        
        # Check if entry has expired
        if time.time() - entry.created_at > entry.ttl_seconds:
            del self._cache[cache_key]
            self._stats["evictions"] += 1
            self._stats["misses"] += 1
            return None
        
        self._stats["hits"] += 1
        return entry.cues
    
    def set(
        self,
        audio_path: str,
        text: str,
        cues: List[CaptionCue],
        segments: Optional[List[CaptionSegment]] = None,
        ttl_seconds: Optional[int] = None,
    ):
        """
        Cache captions for audio/text combination.
        
        Args:
            audio_path: Path to audio file
            text: Original text
            cues: Caption cues to cache
            segments: Optional segments to cache
            ttl_seconds: Optional custom TTL
        """
        cache_key = self._generate_key(audio_path, text)
        
        entry = CaptionCacheEntry(
            audio_hash=cache_key,
            text=text,
            cues=cues,
            segments=segments or [],
            created_at=time.time(),
            ttl_seconds=ttl_seconds or self.ttl_seconds,
        )
        
        self._cache[cache_key] = entry
        
        # Evict old entries if cache is too large
        self._evict_old_entries()
    
    def invalidate(self, audio_path: str, text: str) -> bool:
        """
        Invalidate cached captions for audio/text combination.
        
        Returns:
            True if entry was found and removed, False otherwise
        """
        cache_key = self._generate_key(audio_path, text)
        
        if cache_key in self._cache:
            del self._cache[cache_key]
            return True
        
        return False
    
    def clear(self):
        """Clear all cached entries."""
        self._cache.clear()
        log.info("Caption cache cleared")
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        total_requests = self._stats["hits"] + self._stats["misses"]
        hit_rate = (
            self._stats["hits"] / total_requests
            if total_requests > 0
            else 0
        )
        
        return {
            **self._stats,
            "total_entries": len(self._cache),
            "hit_rate": hit_rate,
        }
    
    def _generate_key(self, audio_path: str, text: str) -> str:
        """Generate cache key from audio path and text."""
        # Use audio file content hash if file exists
        try:
            with open(audio_path, "rb") as f:
                audio_content = f.read(1024)  # Read first 1KB for speed
            audio_hash = hashlib.md5(audio_content).hexdigest()
        except (FileNotFoundError, IOError):
            # Fallback to path-based hash
            audio_hash = hashlib.md5(audio_path.encode()).hexdigest()
        
        # Combine with text hash
        text_hash = hashlib.md5(text.encode()).hexdigest()
        
        return f"{audio_hash}_{text_hash}"
    
    def _evict_old_entries(self):
        """Evict expired entries if cache is too large."""
        max_entries = 100
        
        if len(self._cache) <= max_entries:
            return
        
        # Find and remove expired entries
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if current_time - entry.created_at > entry.ttl_seconds
        ]
        
        for key in expired_keys:
            del self._cache[key]
            self._stats["evictions"] += 1
        
        # If still too large, remove oldest entries
        if len(self._cache) > max_entries:
            sorted_entries = sorted(
                self._cache.items(),
                key=lambda x: x[1].created_at
            )
            
            entries_to_remove = len(self._cache) - max_entries
            for key, _ in sorted_entries[:entries_to_remove]:
                del self._cache[key]
                self._stats["evictions"] += 1
