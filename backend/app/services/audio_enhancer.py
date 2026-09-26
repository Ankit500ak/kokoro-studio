"""
Natural Voice Enhancement Pipeline
===================================
Focus on ONE thing: making TTS sound like a real human talking.

Key principles:
1. Less is more - subtle processing sounds natural
2. Preserve the original voice character
3. Fix artifacts, don't add effects
4. Smooth transitions between chunks
"""

import torch
import numpy as np
import logging

log = logging.getLogger(__name__)

SAMPLE_RATE = 24000


class AudioEnhancer:
    def __init__(self, sample_rate: int = SAMPLE_RATE):
        self.sr = sample_rate

    def enhance(self, audio: torch.Tensor, preset: str = "storytelling", enhancement_level: str = "balanced") -> torch.Tensor:
        """Minimal, focused enhancement for natural voice."""
        if audio.numel() == 0:
            return audio

        # Remove DC offset
        audio = audio - audio.mean()

        # Gentle soft clipping (prevents harsh digital distortion)
        audio = torch.tanh(audio * 0.95) / torch.tanh(torch.tensor(0.95))

        # Gentle dynamic compression (evens out volume)
        audio = self._gentle_compress(audio)

        # Normalize to consistent level
        audio = self._normalize(audio)

        # Final safety clip
        audio = torch.clamp(audio, -1.0, 1.0)

        return audio

    def _gentle_compress(self, audio: torch.Tensor) -> torch.Tensor:
        """Very gentle compression - just enough to even out dynamics."""
        if audio.numel() == 0:
            return audio

        # Simple soft-knee compression using tanh
        # This naturally compresses loud parts without artifacts
        abs_audio = audio.abs()
        
        # Find the peak
        peak = abs_audio.max()
        if peak < 0.01:
            return audio

        # Only compress if signal is loud
        threshold = 0.6
        mask = abs_audio > threshold
        
        if mask.any():
            # Soft compression: reduce gain above threshold
            gain = torch.ones_like(abs_audio)
            excess = abs_audio[mask] - threshold
            # Very gentle 2:1 ratio
            compressed = threshold + excess * 0.5
            gain[mask] = compressed / abs_audio[mask]
            gain = torch.clamp(gain, 0.5, 1.0)
            audio = audio * gain

        return audio

    def _normalize(self, audio: torch.Tensor) -> torch.Tensor:
        """Normalize to consistent volume level."""
        peak = audio.abs().max()
        if peak < 0.01:
            return audio

        # Target: -3dB peak (0.707)
        target = 0.7
        gain = target / peak
        # Limit gain to avoid boosting noise
        gain = min(gain, 3.0)
        
        return audio * gain


# Singleton
audio_enhancer = AudioEnhancer()
