"""Unit tests for the caption quality validator (caption_manager)."""

from app.services.caption_manager.models import CaptionCue, CaptionWord
from app.services.caption_manager.validator import CaptionValidator


def make_cue(cue_id, text, start_ms, end_ms, confidence=1.0):
    words = [
        CaptionWord(text=w, start_ms=start_ms, end_ms=end_ms, confidence=confidence)
        for w in text.split()
    ]
    return CaptionCue(id=cue_id, words=words, start_ms=start_ms, end_ms=end_ms)


def test_valid_captions_pass():
    cues = [
        make_cue("1", "Hello world", 0, 1000),
        make_cue("2", "This is fine", 1100, 2100),
    ]
    result = CaptionValidator().validate(cues)
    assert result.is_valid
    assert result.errors == []
    assert result.stats["total_cues"] == 2
    assert result.stats["total_words"] == 5


def test_empty_caption_list_is_valid_with_warning():
    result = CaptionValidator().validate([])
    assert result.is_valid
    assert any("No captions" in w for w in result.warnings)


def test_overlapping_cues_are_an_error():
    cues = [
        make_cue("1", "Hello world", 0, 1000),
        make_cue("2", "Overlapping cue", 500, 1500),
    ]
    result = CaptionValidator().validate(cues)
    assert not result.is_valid
    assert any("overlap" in e for e in result.errors)


def test_empty_caption_text_is_an_error():
    cues = [CaptionCue(id="1", words=[], start_ms=0, end_ms=1000)]
    result = CaptionValidator().validate(cues)
    assert not result.is_valid
    assert any("Empty caption" in e for e in result.errors)


def test_negative_start_is_an_error():
    cues = [make_cue("1", "Too early", -100, 900)]
    result = CaptionValidator().validate(cues)
    assert not result.is_valid
    assert any("Negative start" in e for e in result.errors)


def test_low_confidence_warns_but_stays_valid():
    cues = [make_cue("1", "Mumbled words here", 0, 1000, confidence=0.3)]
    result = CaptionValidator().validate(cues)
    assert result.is_valid
    assert any("Low confidence" in w for w in result.warnings)
