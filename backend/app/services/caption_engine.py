from typing import List, Optional
import re
from .types import WordTimestamp, CaptionWord, CaptionCue


# Preset timing configurations optimized for different speech styles
PRESET_TIMING = {
    "shorts": {
        "min_duration_ms": 150,
        "max_duration_ms": 600,
        "speed_multiplier": 1.2,
        "pause_after_punctuation_ms": 100,
        "words_per_caption": 3,
        "font_size": 80,
        "primary_color": "&H00FFFFFF",   # White
        "secondary_color": "&H0000FFFF", # Yellow (for karaoke highlight)
        "outline_color": "&H00000000",   # Black outline
        "back_color": "&H80000000",      # Semi-transparent shadow
    },
    "storytelling": {
        "min_duration_ms": 250,
        "max_duration_ms": 800,
        "speed_multiplier": 1.0,
        "pause_after_punctuation_ms": 180,
        "words_per_caption": 3,
        "font_size": 82,
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H0000FFFF",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
    },
    "mystery": {
        "min_duration_ms": 280,
        "max_duration_ms": 900,
        "speed_multiplier": 0.90,
        "pause_after_punctuation_ms": 250,
        "words_per_caption": 3,
        "font_size": 72,
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H00000000",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
    },
    "horror": {
        "min_duration_ms": 250,
        "max_duration_ms": 800,
        "speed_multiplier": 0.85,
        "pause_after_punctuation_ms": 280,
        "words_per_caption": 2,
        "font_size": 72,
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H00000000",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
    },
    "romantic": {
        "min_duration_ms": 250,
        "max_duration_ms": 650,
        "speed_multiplier": 0.95,
        "pause_after_punctuation_ms": 200,
        "words_per_caption": 3,
        "font_size": 74,
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H00000000",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
    },
    "documentary": {
        "min_duration_ms": 250,
        "max_duration_ms": 650,
        "speed_multiplier": 0.95,
        "pause_after_punctuation_ms": 150,
        "words_per_caption": 3,
        "font_size": 76,
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H00000000",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
    },
    "educational": {
        "min_duration_ms": 200,
        "max_duration_ms": 550,
        "speed_multiplier": 1.0,
        "pause_after_punctuation_ms": 120,
        "words_per_caption": 3,
        "font_size": 76,
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H00000000",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
    },
    "news": {
        "min_duration_ms": 160,
        "max_duration_ms": 500,
        "speed_multiplier": 1.05,
        "pause_after_punctuation_ms": 100,
        "words_per_caption": 3,
        "font_size": 74,
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H00000000",
        "outline_color": "&H00000000",
        "back_color": "&H80000000",
    },
}


# Sentence-ending punctuation
_SENTENCE_END = {'.', '!', '?', '...'}
# Clause-ending punctuation
_CLAUSE_END = {',', ';', ':', '—', '—'}
# All pause punctuation
_ALL_PUNCT = _SENTENCE_END | _CLAUSE_END


class CaptionEngine:
    """Segment word timestamps into caption cues for display.
    
    Groups words by natural sentence/pause boundaries for smoother pacing.
    """

    def __init__(
        self,
        preset: str = "storytelling",
        speed: float = 1.0,
        max_words: int = 1,
        max_lines: int = 1,
    ):
        self.preset = preset
        self.speed = speed
        self.max_words = max_words
        self.max_lines = max_lines
        
        timing = PRESET_TIMING.get(preset, PRESET_TIMING["storytelling"])
        self.min_duration_ms = timing["min_duration_ms"]
        self.max_duration_ms = timing["max_duration_ms"]
        self.speed_multiplier = timing["speed_multiplier"]
        self.pause_after_punctuation_ms = timing["pause_after_punctuation_ms"]
        self.words_per_caption = timing["words_per_caption"]
        self.font_size = timing["font_size"]
        self.primary_color = timing["primary_color"]
        self.secondary_color = timing["secondary_color"]
        self.outline_color = timing["outline_color"]
        self.back_color = timing["back_color"]

    def generate_cues(self, words: List[WordTimestamp]) -> List[CaptionCue]:
        """Generate caption cues from word timestamps. STRICTLY max 3 words per cue."""
        if not words:
            return []

        MAX_WORDS = 3  # STRICT LIMIT
        
        # Step 1: Group words into captions (exactly 3 words)
        groups = []
        current_group = []
        
        for word in words:
            current_group.append(word)
            
            text = word.text.rstrip()
            ends_sentence = any(text.endswith(p) for p in _SENTENCE_END)
            
            # Split at exactly 3 words or sentence end
            if len(current_group) >= MAX_WORDS or ends_sentence:
                groups.append(current_group[:MAX_WORDS])  # Ensure max 3
                current_group = []
        
        if current_group and len(current_group) <= MAX_WORDS:
            groups.append(current_group)
        
        # Step 2: Build cues with precise timing
        cues = []
        for group in groups:
            if not group:
                continue
            # STRICT: Only take first 3 words
            group = group[:MAX_WORDS]
            cue = self._build_cue(group)
            cues.append(cue)
        
        # Step 3: Remove duplicate cues (same text within 100ms)
        unique_cues = []
        for cue in cues:
            if not unique_cues:
                unique_cues.append(cue)
                continue
            prev = unique_cues[-1]
            curr_text = self.format_cue_text(cue)
            prev_text = self.format_cue_text(prev)
            time_diff = abs(cue.start_ms - prev.start_ms)
            if curr_text != prev_text or time_diff > 100:
                unique_cues.append(cue)
        
        # Step 4: Ensure no overlaps
        unique_cues = self._ensure_no_overlap(unique_cues)
        
        # Step 5: FINAL STRICT ENFORCEMENT - max 3 words per cue
        for cue in unique_cues:
            cue.words = cue.words[:MAX_WORDS]
        
        return unique_cues

    def _ensure_no_overlap(self, cues: List[CaptionCue]) -> List[CaptionCue]:
        """Ensure captions don't overlap each other."""
        if len(cues) <= 1:
            return cues
        
        result = [cues[0]]
        for i in range(1, len(cues)):
            prev = result[-1]
            curr = cues[i]
            
            # If current starts before previous ends, push it forward
            if curr.start_ms < prev.end_ms:
                curr.start_ms = prev.end_ms + 10  # 10ms gap
            
            result.append(curr)
        
        return result

    def _split_by_silence(self, words: List[WordTimestamp]) -> List[List[WordTimestamp]]:
        """Split words into phrases based on silence gaps.
        
        Detects gaps > 250ms as silence/pause points and splits there.
        This ensures captions pause precisely during silence.
        """
        if not words:
            return []
        
        SILENCE_THRESHOLD_MS = 250  # Gap > 250ms = silence
        
        phrases = []
        current_phrase = [words[0]]
        
        for i in range(1, len(words)):
            gap = words[i].start_ms - words[i-1].end_ms
            
            if gap >= SILENCE_THRESHOLD_MS:
                # Large gap = silence, start new phrase
                if current_phrase:
                    phrases.append(current_phrase)
                current_phrase = [words[i]]
            else:
                current_phrase.append(words[i])
        
        if current_phrase:
            phrases.append(current_phrase)
        
        return phrases

    def _apply_speed_to_words(self, words: List[WordTimestamp]) -> List[WordTimestamp]:
        """Adjust word timestamps based on voice speed multiplier.
        
        When speed > 1.0, audio plays faster so captions must appear sooner.
        When speed < 1.0, audio plays slower so captions must appear later.
        """
        if self.speed == 1.0:
            return words

        adjusted = []
        for word in words:
            # Speed affects timing: faster speed = shorter durations
            new_start = word.start_ms / self.speed
            new_end = word.end_ms / self.speed
            adjusted.append(WordTimestamp(
                text=word.text,
                start_ms=new_start,
                end_ms=new_end,
                confidence=word.confidence,
            ))
        return adjusted

    def _group_by_boundaries(self, words: List[WordTimestamp]) -> List[List[WordTimestamp]]:
        """Group words at natural sentence/pause boundaries."""
        groups = []
        current_group = []

        for i, word in enumerate(words):
            current_group.append(word)
            text = word.text.rstrip()
            ends_sentence = any(text.endswith(p) for p in _SENTENCE_END)
            ends_clause = any(text.endswith(p) for p in _CLAUSE_END)

            # Check if next word starts a new sentence (capital letter after period)
            next_starts_sentence = False
            if i + 1 < len(words):
                next_text = words[i + 1].text.strip()
                if next_text and next_text[0].isupper() and any(text.endswith(p) for p in {'.', '!', '?', '...'}):
                    next_starts_sentence = True

            # Split at sentence end
            if ends_sentence or next_starts_sentence:
                if current_group:
                    groups.append(current_group)
                    current_group = []
            # Split at clause end if group is getting long
            elif ends_clause and len(current_group) >= self.words_per_caption:
                groups.append(current_group)
                current_group = []

        if current_group:
            groups.append(current_group)

        return groups

    def _merge_and_split(self, groups: List[List[WordTimestamp]]) -> List[List[WordTimestamp]]:
        """Merge very short groups and split overly long ones.
        
        STRICT RULE: Never exceed words_per_caption words per cue.
        """
        result = []

        for group in groups:
            word_count = len(group)

            # If group is very short (1 word, <100ms), try to merge with next
            if word_count == 1 and result:
                prev = result[-1]
                if len(prev) < self.words_per_caption:
                    result[-1] = prev + group
                    continue

            # If group is too long, split it into chunks of words_per_caption
            if word_count > self.words_per_caption:
                # Split into exact chunks of words_per_caption size
                for i in range(0, word_count, self.words_per_caption):
                    chunk = group[i:i + self.words_per_caption]
                    if chunk:
                        result.append(chunk)
            else:
                result.append(group)

        return result

    def _build_cue(self, group: List[WordTimestamp]) -> CaptionCue:
        """Build a caption cue with precise timing matching audio exactly."""
        caption_words = []
        for word in group:
            # Skip standalone punctuation tokens
            if re.match(r'^[.!?;,:\-—]+$', word.text.strip()):
                continue
            cleaned = self._clean_text(word.text)
            if cleaned:
                caption_words.append(CaptionWord(
                    text=cleaned,
                    start_ms=word.start_ms,
                    end_ms=word.end_ms,
                ))

        if not caption_words:
            # Fallback: use first word even if it's punctuation
            caption_words.append(CaptionWord(
                text=self._clean_text(group[0].text),
                start_ms=group[0].start_ms,
                end_ms=group[0].end_ms,
            ))

        # EXACT timing: caption appears exactly when first word is spoken
        # and ends exactly when last word ends - NO lead time, NO extra buffer
        start_ms = group[0].start_ms
        end_ms = group[-1].end_ms

        return CaptionCue(
            start_ms=start_ms,
            end_ms=end_ms,
            words=caption_words,
        )

    def _smooth_cues(self, cues: List[CaptionCue]) -> List[CaptionCue]:
        """Ensure smooth transitions between cues with precise timing."""
        if len(cues) <= 1:
            return cues

        smoothed = [cues[0]]
        for i in range(1, len(cues)):
            prev = smoothed[-1]
            curr = cues[i]

            # Ensure no overlap - captions must be sequential
            if curr.start_ms < prev.end_ms:
                curr.start_ms = prev.end_ms

            # Ensure minimal gap (50ms) between captions for visual separation
            min_gap = 50
            if curr.start_ms < prev.end_ms + min_gap:
                curr.start_ms = prev.end_ms + min_gap

            smoothed.append(curr)

        return smoothed

    def _clean_text(self, text: str) -> str:
        text = text.replace('\\n', ' ').replace('\\b', ' ').replace('\\t', ' ')
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def format_cue_text(self, cue: CaptionCue) -> str:
        return " ".join(self._clean_text(w.text) for w in cue.words)


class CaptionASSGenerator:
    """Generate ASS subtitle file with phrase-level display.

    Shows phrases (2-3 words) centered on screen with high contrast text.
    Each phrase appears in sync with the audio timing.
    """

    def __init__(
        self,
        preset: str = "storytelling",
        font_name: str = "Arial Black",
        font_size: Optional[int] = None,
        primary_color: str = "&H00FFFFFF",  # White
        secondary_color: str = "&H00000000",  # Black
        outline_color: str = "&H00000000",  # Pure black outline
        back_color: str = "&H80000000",  # Semi-transparent black shadow
        outline_width: int = 6,
        shadow: int = 2,
        margin_v: int = 50,
    ):
        self.preset = preset
        self.font_name = font_name
        
        # Get colors and font size from preset config
        timing = PRESET_TIMING.get(preset, PRESET_TIMING["storytelling"])
        self.font_size = font_size if font_size is not None else timing["font_size"]
        self.primary_color = timing.get("primary_color", primary_color)
        self.secondary_color = timing.get("secondary_color", secondary_color)
        self.outline_color = timing.get("outline_color", outline_color)
        self.back_color = timing.get("back_color", back_color)
        self.outline_width = outline_width
        self.shadow = shadow
        self.margin_v = margin_v

    def generate_ass(self, cues: List[CaptionCue], video_width: int = 1080, video_height: int = 1920) -> str:
        play_res_x = video_width
        play_res_y = video_height

        header = f"""[Script Info]
Title: Kokoro Studio Captions
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial Black,{self.font_size},{self.primary_color},{self.secondary_color},{self.outline_color},{self.back_color},1,0,0,0,100,100,3,0,1,{self.outline_width},{self.shadow},5,0,0,{self.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        events = []
        for cue in cues:
            display_words = cue.words[:3]
            if not display_words:
                continue
                
            start = self._format_time(cue.start_ms)
            end = self._format_time(cue.end_ms)
            
            # Build word-by-word text with karaoke timing
            total_ms = cue.end_ms - cue.start_ms
            word_parts = []
            for i, word in enumerate(display_words):
                word_start_ms = word.start_ms - cue.start_ms
                word_end_ms = word.end_ms - cue.start_ms
                word_duration_cs = int((word_end_ms - word_start_ms) / 10)
                
                # Add karaoke tag for word highlighting
                # \kf = fill from left to right
                word_parts.append(f"{{\\kf{word_duration_cs}}}{word.text}")
            
            text = " ".join(word_parts)
            events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

        return header + "\n".join(events) + "\n"

    def _clean_text(self, text: str) -> str:
        """Clean text by removing escape characters and normalizing whitespace."""
        text = text.replace('\\n', ' ').replace('\\b', ' ').replace('\\t', ' ')
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _format_time(self, ms: float) -> str:
        total_seconds = ms / 1000
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        centiseconds = int((ms % 1000) / 10)
        return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

    def _format_cue_text(self, cue: CaptionCue) -> str:
        """Format caption text by joining words with spaces (max 3 words)."""
        if not cue.words:
            return ""
        # Only use first 3 words
        words = cue.words[:3]
        return " ".join(self._clean_text(w.text) for w in words)

    def _format_cue_text_from_words(self, words: list) -> str:
        """Format caption text from a list of CaptionWord objects (max 3 words)."""
        if not words:
            return ""
        words = words[:3]
        return " ".join(self._clean_text(w.text) for w in words)


# Keep backward compatibility - generate_cues method
def generate_cues(words: List[WordTimestamp], preset: str = "storytelling", speed: float = 1.0) -> List[CaptionCue]:
    """Generate caption cues from word timestamps.
    
    Args:
        words: List of WordTimestamp objects from TTS pipeline
        preset: Caption preset (shorts, storytelling, mystery, etc.)
        speed: Voice speed multiplier
    
    Returns:
        List of CaptionCue objects with proper timing
    """
    engine = CaptionEngine(preset=preset, speed=speed)
    return engine.generate_cues(words)


# Keep backward compatibility - generate_ass method  
def generate_ass(cues: List[CaptionCue], video_width: int = 1080, video_height: int = 1920, preset: str = "storytelling") -> str:
    """Generate ASS subtitle file from caption cues.
    
    Args:
        cues: List of CaptionCue objects
        video_width: Video width in pixels
        video_height: Video height in pixels
        preset: Caption preset for styling
    
    Returns:
        ASS format subtitle string
    """
    generator = CaptionASSGenerator(preset=preset)
    return generator.generate_ass(cues, video_width, video_height)