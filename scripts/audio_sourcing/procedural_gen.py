from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Callable

import numpy as np
import soundfile as sf

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.audio_mixer import DEFAULT_PEAK_LIMIT, DEFAULT_SAMPLE_RATE, _apply_loop_crossfade, _limit_peak


GeneratorFn = Callable[..., np.ndarray]


def _time_axis(duration: float, sample_rate: int) -> np.ndarray:
    return np.linspace(0.0, float(duration), int(sample_rate * duration), endpoint=False, dtype=np.float32)


def _safe_normalize(audio: np.ndarray, peak_limit: float = DEFAULT_PEAK_LIMIT) -> np.ndarray:
    peak = float(np.max(np.abs(audio)))
    if peak > 0:
        audio = audio / np.float32(peak / peak_limit)
    return _limit_peak(audio.astype(np.float32), peak_limit=peak_limit).astype(np.float32)


def _fft_filtered_noise(
    sample_count: int,
    *,
    sample_rate: int,
    rng: np.random.Generator,
    low_hz: float | None = None,
    high_hz: float | None = None,
    pink: bool = False,
) -> np.ndarray:
    spectrum = rng.normal(size=(sample_count // 2) + 1) + 1j * rng.normal(size=(sample_count // 2) + 1)
    frequencies = np.fft.rfftfreq(sample_count, d=1.0 / sample_rate)
    if pink:
        weights = np.ones_like(frequencies, dtype=np.float64)
        weights[1:] = 1.0 / np.sqrt(frequencies[1:])
        spectrum *= weights
    mask = np.ones_like(frequencies, dtype=bool)
    if low_hz is not None:
        mask &= frequencies >= float(low_hz)
    if high_hz is not None:
        mask &= frequencies <= float(high_hz)
    spectrum[~mask] = 0.0
    noise = np.fft.irfft(spectrum, n=sample_count).real
    return noise.astype(np.float32)


def _stereoize(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    return np.column_stack([left, right]).astype(np.float32)


def _finish_loop(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    fade_samples = min(max(sample_rate // 8, 1), max(1, len(audio) // 8))
    audio = _apply_loop_crossfade(audio.astype(np.float32), fade_samples=fade_samples)
    seam_lock_samples = min(max(sample_rate // 20, 1), max(1, len(audio) // 20))
    audio[-seam_lock_samples:] = audio[:seam_lock_samples]
    return _safe_normalize(audio)


def room_tone(
    duration: float,
    *,
    base_freq: float = 60.0,
    bandwidth: float = 200.0,
    lfo_rate: float = 0.1,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    seed: int = 0,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    sample_count = int(sample_rate * duration)
    t = _time_axis(duration, sample_rate)

    low_hz = max(5.0, base_freq)
    high_hz = max(low_hz + 10.0, base_freq + bandwidth)
    left_noise = _fft_filtered_noise(sample_count, sample_rate=sample_rate, rng=rng, low_hz=low_hz, high_hz=high_hz, pink=True)
    right_noise = _fft_filtered_noise(sample_count, sample_rate=sample_rate, rng=rng, low_hz=low_hz * 0.9, high_hz=high_hz * 1.05, pink=True)

    left_lfo = 0.72 + 0.18 * np.sin((2.0 * np.pi * lfo_rate * t) + 0.0, dtype=np.float32)
    right_lfo = 0.72 + 0.18 * np.sin((2.0 * np.pi * lfo_rate * t) + 0.9, dtype=np.float32)
    bed = _stereoize(left_noise * left_lfo, right_noise * right_lfo)
    return _finish_loop(bed * 0.55, sample_rate)


def fan(
    duration: float,
    *,
    base_freq: float = 120.0,
    harmonics: int = 3,
    wobble: float = 0.02,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    seed: int = 0,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = _time_axis(duration, sample_rate)
    wobble_phase = (2.0 * np.pi * 0.17 * t).astype(np.float32)
    wobble_curve = 1.0 + (wobble * np.sin(wobble_phase, dtype=np.float32))

    left = np.zeros_like(t, dtype=np.float32)
    right = np.zeros_like(t, dtype=np.float32)
    for index in range(1, harmonics + 1):
        harmonic_freq = base_freq * index
        amplitude = 0.22 / index
        detune = 1.0 + (0.0025 * index)
        left += amplitude * np.sin(2.0 * np.pi * harmonic_freq * wobble_curve * t, dtype=np.float32)
        right += amplitude * np.sin(2.0 * np.pi * harmonic_freq * wobble_curve * detune * t + (0.11 * index), dtype=np.float32)

    noise_left = _fft_filtered_noise(len(t), sample_rate=sample_rate, rng=rng, low_hz=70.0, high_hz=2_000.0, pink=True) * 0.08
    noise_right = _fft_filtered_noise(len(t), sample_rate=sample_rate, rng=rng, low_hz=90.0, high_hz=2_200.0, pink=True) * 0.08
    audio = _stereoize(left + noise_left, right + noise_right)
    return _finish_loop(audio * 0.7, sample_rate)


def wind(
    duration: float,
    *,
    intensity: float = 0.5,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    seed: int = 0,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = _time_axis(duration, sample_rate)
    low_hz = 120.0
    high_hz = 4_800.0 + (2_000.0 * float(intensity))
    left_noise = _fft_filtered_noise(len(t), sample_rate=sample_rate, rng=rng, low_hz=low_hz, high_hz=high_hz, pink=False)
    right_noise = _fft_filtered_noise(len(t), sample_rate=sample_rate, rng=rng, low_hz=low_hz * 1.1, high_hz=high_hz * 0.9, pink=False)

    envelope = (
        0.35
        + (0.25 * np.sin(2.0 * np.pi * 0.06 * t, dtype=np.float32))
        + (0.15 * np.sin(2.0 * np.pi * 0.11 * t + 0.7, dtype=np.float32))
        + (0.08 * np.sin(2.0 * np.pi * 0.23 * t + 1.4, dtype=np.float32))
    )
    envelope = np.clip(envelope * (0.7 + (0.8 * float(intensity))), 0.08, 1.0).astype(np.float32)

    left = left_noise * envelope
    right = np.roll(right_noise, sample_rate // 200) * envelope[::-1]
    audio = _stereoize(left, right)
    return _finish_loop(audio * 0.45, sample_rate)


def hum(
    duration: float,
    *,
    base_freq: float = 60.0,
    amplitude: float = 0.1,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    seed: int = 0,
) -> np.ndarray:
    rng = np.random.default_rng(seed)
    t = _time_axis(duration, sample_rate)
    left = np.zeros_like(t, dtype=np.float32)
    right = np.zeros_like(t, dtype=np.float32)
    for index, harmonic_scale in enumerate((1.0, 0.35, 0.2), start=1):
        harmonic_freq = base_freq * index
        left += (amplitude * harmonic_scale) * np.sin(2.0 * np.pi * harmonic_freq * t, dtype=np.float32)
        right += (amplitude * harmonic_scale) * np.sin(2.0 * np.pi * harmonic_freq * t + (0.03 * index), dtype=np.float32)

    drift = 1.0 + 0.01 * np.sin(2.0 * np.pi * 0.09 * t, dtype=np.float32)
    left *= drift
    right *= drift[::-1]

    hiss_left = _fft_filtered_noise(len(t), sample_rate=sample_rate, rng=rng, low_hz=20.0, high_hz=500.0, pink=True) * 0.01
    hiss_right = _fft_filtered_noise(len(t), sample_rate=sample_rate, rng=rng, low_hz=20.0, high_hz=600.0, pink=True) * 0.01
    audio = _stereoize(left + hiss_left, right + hiss_right)
    return _finish_loop(audio, sample_rate)


GENERATORS: dict[str, GeneratorFn] = {
    "room_tone": room_tone,
    "fan": fan,
    "wind": wind,
    "hum": hum,
}


def generate_procedural_audio(
    sound_type: str,
    *,
    duration: float,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    seed: int = 0,
    **kwargs: Any,
) -> np.ndarray:
    if sound_type not in GENERATORS:
        raise ValueError(f"Unsupported procedural sound type: {sound_type}")
    return GENERATORS[sound_type](duration=duration, sample_rate=sample_rate, seed=seed, **kwargs)


def write_procedural_wav(
    sound_type: str,
    output_path: Path,
    *,
    duration: float,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    seed: int = 0,
    **kwargs: Any,
) -> Path:
    audio = generate_procedural_audio(sound_type, duration=duration, sample_rate=sample_rate, seed=seed, **kwargs)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, audio, sample_rate, subtype="PCM_24")
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate loopable procedural ambience layers.")
    parser.add_argument("--type", choices=sorted(GENERATORS.keys()), required=True, help="Procedural sound type.")
    parser.add_argument("--duration", type=float, required=True, help="Output duration in seconds.")
    parser.add_argument("--output", type=Path, required=True, help="Destination WAV path.")
    parser.add_argument("--seed", type=int, default=0, help="Random seed.")
    parser.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE, help="Output sample rate.")
    parser.add_argument("--base-freq", type=float, default=None, help="Base frequency override for room_tone/fan/hum.")
    parser.add_argument("--bandwidth", type=float, default=200.0, help="Bandwidth for room_tone.")
    parser.add_argument("--lfo-rate", type=float, default=0.1, help="LFO rate for room_tone.")
    parser.add_argument("--harmonics", type=int, default=3, help="Harmonic count for fan.")
    parser.add_argument("--wobble", type=float, default=0.02, help="Pitch wobble amount for fan.")
    parser.add_argument("--intensity", type=float, default=0.5, help="Intensity for wind.")
    parser.add_argument("--amplitude", type=float, default=0.1, help="Base amplitude for hum.")
    return parser


def _build_generator_kwargs(args: argparse.Namespace) -> dict[str, Any]:
    sound_type = args.type
    kwargs: dict[str, Any] = {}
    if sound_type == "room_tone":
        kwargs["base_freq"] = args.base_freq if args.base_freq is not None else 60.0
        kwargs["bandwidth"] = args.bandwidth
        kwargs["lfo_rate"] = args.lfo_rate
    elif sound_type == "fan":
        kwargs["base_freq"] = args.base_freq if args.base_freq is not None else 120.0
        kwargs["harmonics"] = args.harmonics
        kwargs["wobble"] = args.wobble
    elif sound_type == "wind":
        kwargs["intensity"] = args.intensity
    elif sound_type == "hum":
        kwargs["base_freq"] = args.base_freq if args.base_freq is not None else 60.0
        kwargs["amplitude"] = args.amplitude
    return kwargs


def main() -> None:
    args = build_parser().parse_args()
    output_path = write_procedural_wav(
        args.type,
        args.output,
        duration=args.duration,
        sample_rate=args.sample_rate,
        seed=args.seed,
        **_build_generator_kwargs(args),
    )
    print(output_path)


if __name__ == "__main__":
    main()
