"""
Multi-Pass Voice Generation System
===================================
Generates multiple audio variations and selects the best one based on
quality metrics. This produces more natural, expressive output.

Strategy:
  1. Generate N variations with slightly different parameters
  2. Score each variation on quality metrics
  3. Select the best one (or blend top 2 for smoother result)
"""

import torch
import numpy as np
import logging
from typing import Optional, Callable
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class GenerationVariation:
    """A single generated audio variation with metadata."""
    audio: torch.Tensor
    speed: float
    quality_score: float
    variation_index: int


@dataclass
class QualityMetrics:
    """Quality metrics for audio evaluation."""
    spectral_clarity: float    # How clear/focused the spectrum is (0-1)
    dynamic_range: float       # Ratio of loud to quiet parts (0-1)
    naturalness: float         # How natural the audio sounds (0-1)
    consistency: float         # How consistent the energy is (0-1)
    overall: float             # Weighted overall score (0-1)


class MultiPassGenerator:
    """
    Generate multiple audio variations and select the best one.

    Uses quality metrics to automatically pick the most natural-sounding
    variation from a set of candidates.
    """

    def __init__(self, sample_rate: int = 24000):
        self.sr = sample_rate

    def generate_and_select(
        self,
        generation_fn: Callable[[float], torch.Tensor],
        num_variations: int = 3,
        speed_range: float = 0.05,
        base_speed: float = 1.0,
        blend_top: bool = True,
        blend_weight: float = 0.3,
    ) -> torch.Tensor:
        """
        Generate multiple variations and return the best one.

        Args:
            generation_fn: Function that takes speed and returns audio tensor
            num_variations: Number of variations to generate
            speed_range: +/- range for speed variations
            base_speed: Base speed for generation
            blend_top: If True, blend top 2 variations for smoother result
            blend_weight: Weight for blending (0-1, higher = more blending)

        Returns:
            Best (or blended) audio tensor
        """
        if num_variations <= 1:
            return generation_fn(base_speed)

        variations = []

        for i in range(num_variations):
            # Vary speed slightly for each variation
            speed_offset = np.linspace(-speed_range, speed_range, num_variations)[i]
            varied_speed = base_speed + speed_offset

            try:
                audio = generation_fn(varied_speed)
                if audio.numel() == 0:
                    continue

                # Score this variation
                metrics = self._compute_quality_metrics(audio)
                variations.append(GenerationVariation(
                    audio=audio,
                    speed=varied_speed,
                    quality_score=metrics.overall,
                    variation_index=i,
                ))
            except Exception as e:
                log.warning(f"[MultiPass] Variation {i} failed: {e}")
                continue

        if not variations:
            # Fallback: just generate with base speed
            return generation_fn(base_speed)

        # Sort by quality score (best first)
        variations.sort(key=lambda v: v.quality_score, reverse=True)

        best = variations[0]
        log.info(f"[MultiPass] Best variation: #{best.variation_index} "
                 f"speed={best.speed:.3f} score={best.quality_score:.3f}")

        # Blend top 2 for smoother result
        if blend_top and len(variations) >= 2:
            second = variations[1]
            # Only blend if scores are close
            if second.quality_score > best.quality_score * 0.9:
                blended = self._blend_audio(best.audio, second.audio, blend_weight)
                blend_score = self._compute_quality_metrics(blended)
                log.info(f"[MultiPass] Blended score: {blend_score.overall:.3f}")

                # Use blend if it's better or comparable
                if blend_score.overall >= best.quality_score * 0.95:
                    return blended

        return best.audio

    def _compute_quality_metrics(self, audio: torch.Tensor) -> QualityMetrics:
        """Compute quality metrics for an audio tensor."""
        if audio.numel() < 100:
            return QualityMetrics(0, 0, 0, 0, 0)

        # 1. Spectral clarity (focused energy = clearer voice)
        spectral_clarity = self._measure_spectral_clarity(audio)

        # 2. Dynamic range (good variation between loud and quiet)
        dynamic_range = self._measure_dynamic_range(audio)

        # 3. Naturalness (smooth, not robotic)
        naturalness = self._measure_naturalness(audio)

        # 4. Consistency (stable energy, no sudden drops)
        consistency = self._measure_consistency(audio)

        # Weighted overall score
        overall = (
            spectral_clarity * 0.25 +
            dynamic_range * 0.20 +
            naturalness * 0.35 +
            consistency * 0.20
        )

        return QualityMetrics(
            spectral_clarity=spectral_clarity,
            dynamic_range=dynamic_range,
            naturalness=naturalness,
            consistency=consistency,
            overall=overall,
        )

    def _measure_spectral_clarity(self, audio: torch.Tensor) -> float:
        """Measure how clear/focused the spectrum is."""
        # Use autocorrelation to measure spectral focus
        n = min(len(audio), self.sr * 5)  # Max 5 seconds
        signal = audio[:n].numpy()

        # Compute autocorrelation
        autocorr = np.correlate(signal, signal, mode='full')
        autocorr = autocorr[len(autocorr) // 2:]
        autocorr = autocorr / (autocorr[0] + 1e-10)

        # Sharp peaks in autocorrelation = clear spectrum
        # Find peaks
        peaks = []
        for i in range(1, min(len(autocorr) - 1, 1000)):
            if autocorr[i] > autocorr[i-1] and autocorr[i] > autocorr[i+1]:
                peaks.append(autocorr[i])

        if not peaks:
            return 0.5

        # Higher peak values = clearer spectrum
        avg_peak = np.mean(peaks)
        return min(1.0, avg_peak * 2)

    def _measure_dynamic_range(self, audio: torch.Tensor) -> float:
        """Measure dynamic range (ratio of loud to quiet parts)."""
        # Split into windows and compute energy
        window_size = 1024
        energies = []
        for i in range(0, len(audio) - window_size, window_size):
            chunk = audio[i:i + window_size]
            energy = chunk.pow(2).mean().sqrt().item()
            energies.append(energy)

        if not energies:
            return 0.5

        energies = np.array(energies)
        peak = energies.max()
        rms = energies.mean()

        if rms < 1e-10:
            return 0.5

        # Good dynamic range: peak/rms between 1.5 and 4.0
        ratio = peak / rms
        # Normalize to 0-1
        dr = min(1.0, max(0.0, (ratio - 1.0) / 3.0))
        return dr

    def _measure_naturalness(self, audio: torch.Tensor) -> float:
        """Measure how natural (non-robotic) the audio sounds."""
        n = min(len(audio), self.sr * 5)
        signal = audio[:n].numpy()

        # 1. Check for periodicity (robotic = too periodic)
        # Short-time energy variation
        window = 512
        hop = 256
        energies = []
        for i in range(0, n - window, hop):
            chunk = signal[i:i + window]
            energy = np.sqrt(np.mean(chunk ** 2))
            energies.append(energy)

        if len(energies) < 10:
            return 0.5

        energies = np.array(energies)

        # 2. Measure energy variation coefficient
        mean_e = energies.mean()
        std_e = energies.std()
        cv = std_e / (mean_e + 1e-10)  # Coefficient of variation

        # Natural speech has moderate variation (CV between 0.3 and 0.8)
        if 0.3 <= cv <= 0.8:
            naturalness_cv = 1.0
        elif cv < 0.3:
            naturalness_cv = cv / 0.3  # Too flat = robotic
        else:
            naturalness_cv = max(0.5, 1.0 - (cv - 0.8) * 2)  # Too variable

        # 3. Check spectral flatness (natural speech has formants = not flat)
        # Simple spectral flatness via geometric/arithmetic mean
        spectrum = np.abs(np.fft.rfft(signal))
        spectrum = spectrum[spectrum > 0]
        if len(spectrum) > 0:
            log_spectrum = np.log(spectrum)
            geometric_mean = np.exp(log_spectrum.mean())
            arithmetic_mean = spectrum.mean()
            spectral_flatness = geometric_mean / (arithmetic_mean + 1e-10)
            # Natural speech has lower flatness (has formants)
            naturalness_spectral = max(0, 1.0 - spectral_flatness)
        else:
            naturalness_spectral = 0.5

        # Combine
        return (naturalness_cv * 0.5 + naturalness_spectral * 0.5)

    def _measure_consistency(self, audio: torch.Tensor) -> float:
        """Measure energy consistency (no sudden drops/spikes)."""
        window = 1024
        hop = 512
        energies = []

        for i in range(0, len(audio) - window, hop):
            chunk = audio[i:i + window]
            energy = chunk.pow(2).mean().sqrt().item()
            energies.append(energy)

        if len(energies) < 5:
            return 0.5

        energies = np.array(energies)

        # Check for sudden drops (ratio between consecutive windows)
        ratios = []
        for i in range(1, len(energies)):
            if energies[i-1] > 0.01:
                ratios.append(energies[i] / energies[i-1])

        if not ratios:
            return 0.5

        ratios = np.array(ratios)
        # Good consistency: most ratios close to 1.0
        deviation = np.abs(np.log(ratios + 1e-10))
        consistency = max(0, 1.0 - deviation.mean() * 2)

        return consistency

    def _blend_audio(self, audio1: torch.Tensor, audio2: torch.Tensor, weight: float) -> torch.Tensor:
        """Blend two audio tensors with crossfade."""
        # Ensure same length
        min_len = min(len(audio1), len(audio2))
        audio1 = audio1[:min_len]
        audio2 = audio2[:min_len]

        # Crossfade blend
        fade_len = min(int(self.sr * 0.05), min_len // 4)  # 50ms crossfade

        if fade_len < 2:
            return audio1 * (1 - weight) + audio2 * weight

        # Create fade curves
        fade_out = torch.linspace(1, 0, fade_len)
        fade_in = torch.linspace(0, 1, fade_len)

        # Apply crossfade in the middle
        mid = min_len // 2
        start = mid - fade_len // 2
        end = start + fade_len

        if start < 0 or end > min_len:
            return audio1 * (1 - weight) + audio2 * weight

        result = audio1.clone() * (1 - weight) + audio2.clone() * weight

        # Smooth the blend region
        result[start:end] = (
            audio1[start:end] * fade_out * (1 - weight) +
            audio2[start:end] * fade_in * weight +
            result[start:end] * 0.5
        )

        return result


# Singleton
multi_pass_generator = MultiPassGenerator()
