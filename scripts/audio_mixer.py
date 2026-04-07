from __future__ import annotations

import argparse
import math
import tempfile
from pathlib import Path
from typing import Iterable

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
import yaml

try:
    from scripts.scene_config import load_scene_config
except ImportError:
    from scene_config import load_scene_config


DEFAULT_SAMPLE_RATE = 48_000
DEFAULT_TARGET_LUFS = -14.0
DEFAULT_PEAK_LIMIT = 0.995


def _ensure_stereo(audio: np.ndarray) -> np.ndarray:
    if audio.ndim == 1:
        return np.column_stack([audio, audio])
    if audio.shape[1] == 1:
        return np.repeat(audio, 2, axis=1)
    return audio[:, :2]


def _resample_channel(channel: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate:
        return channel.astype(np.float32)
    target_length = max(1, int(round(len(channel) * target_rate / source_rate)))
    source_positions = np.linspace(0.0, 1.0, num=len(channel), endpoint=False)
    target_positions = np.linspace(0.0, 1.0, num=target_length, endpoint=False)
    return np.interp(target_positions, source_positions, channel).astype(np.float32)


def _load_audio(path: Path, target_rate: int = DEFAULT_SAMPLE_RATE) -> np.ndarray:
    data, source_rate = sf.read(path, always_2d=True)
    stereo = _ensure_stereo(np.asarray(data, dtype=np.float32))
    left = _resample_channel(stereo[:, 0], source_rate, target_rate)
    right = _resample_channel(stereo[:, 1], source_rate, target_rate)
    return np.column_stack([left, right]).astype(np.float32)


def _loop_to_length(audio: np.ndarray, target_samples: int) -> np.ndarray:
    if len(audio) == 0:
        raise ValueError("Audio source has no samples.")
    repeats = int(math.ceil(target_samples / len(audio)))
    tiled = np.tile(audio, (repeats, 1))
    return tiled[:target_samples].copy()


def _pan_event(audio: np.ndarray, pan: float) -> np.ndarray:
    mono = audio.mean(axis=1)
    angle = (pan + 1.0) * math.pi / 4.0
    left_gain = math.cos(angle)
    right_gain = math.sin(angle)
    return np.column_stack([mono * left_gain, mono * right_gain]).astype(np.float32)


def _place_events(
    mix: np.ndarray,
    source_paths: Iterable[str],
    *,
    interval: list[int],
    volume: float,
    rng: np.random.Generator,
    sample_rate: int,
) -> np.ndarray:
    current = 0.0
    available = [Path(item) for item in source_paths]
    while current < len(mix) / sample_rate:
        current += float(rng.uniform(interval[0], interval[1]))
        start = int(current * sample_rate)
        if start >= len(mix):
            break
        source = available[int(rng.integers(0, len(available)))]
        event = _load_audio(source, sample_rate)
        event = _pan_event(event, pan=float(rng.uniform(-0.8, 0.8)))
        event *= volume * float(rng.uniform(0.85, 1.15))
        end = min(len(mix), start + len(event))
        mix[start:end] += event[: end - start]
    return mix


def _apply_loop_crossfade(audio: np.ndarray, fade_samples: int) -> np.ndarray:
    if fade_samples <= 0 or fade_samples * 2 >= len(audio):
        return audio
    head = audio[:fade_samples].copy()
    tail = audio[-fade_samples:].copy()
    fade_out = np.linspace(1.0, 0.0, fade_samples, endpoint=True, dtype=np.float32)[:, None]
    fade_in = np.linspace(0.0, 1.0, fade_samples, endpoint=True, dtype=np.float32)[:, None]
    blended = (tail * fade_out) + (head * fade_in)
    audio[:fade_samples] = blended
    audio[-fade_samples:] = blended
    return audio


def _limit_peak(audio: np.ndarray, peak_limit: float = DEFAULT_PEAK_LIMIT) -> np.ndarray:
    peak = float(np.max(np.abs(audio)))
    if peak > peak_limit and peak > 0:
        audio = audio * (peak_limit / peak)
    return audio


def _match_loudness(audio: np.ndarray, sample_rate: int, target_lufs: float = DEFAULT_TARGET_LUFS) -> np.ndarray:
    meter = pyln.Meter(sample_rate)
    measured = meter.integrated_loudness(audio)
    if np.isfinite(measured):
        gain = 10 ** ((target_lufs - measured) / 20.0)
        audio = audio * np.float32(gain)
    audio = _limit_peak(audio)
    measured_after = meter.integrated_loudness(audio)
    if np.isfinite(measured_after):
        fine_gain = 10 ** ((target_lufs - measured_after) / 20.0)
        audio = audio * np.float32(fine_gain)
    return _limit_peak(audio)


def render_scene_audio(scene_config: dict, duration_sec: int, seed: int, sample_rate: int = DEFAULT_SAMPLE_RATE) -> np.ndarray:
    target_samples = int(duration_sec * sample_rate)
    layers = scene_config["audio"]["layers"]
    rng = np.random.default_rng(seed)

    mix = np.zeros((target_samples, 2), dtype=np.float32)
    mix += _loop_to_length(_load_audio(Path(layers["room_tone"]["source_path"]), sample_rate), target_samples) * float(
        layers["room_tone"]["volume"]
    )
    mix += _loop_to_length(
        _load_audio(Path(layers["continuous"]["source_path"]), sample_rate), target_samples
    ) * float(layers["continuous"]["volume"])

    mix = _place_events(
        mix,
        layers["periodic"]["source_paths"],
        interval=layers["periodic"]["interval"],
        volume=float(layers["periodic"]["volume"]),
        rng=rng,
        sample_rate=sample_rate,
    )
    mix = _place_events(
        mix,
        layers["rare_events"]["source_paths"],
        interval=layers["rare_events"]["interval"],
        volume=float(layers["rare_events"]["volume"]),
        rng=rng,
        sample_rate=sample_rate,
    )

    max_fade_samples = max(1, (len(mix) // 2) - 1)
    requested_fade_samples = int(max(scene_config["visual"]["loop_duration_sec"], 1) * sample_rate)
    fade_samples = min(requested_fade_samples, len(mix) // 4, max_fade_samples)
    mix = _apply_loop_crossfade(mix, fade_samples=fade_samples)
    return _match_loudness(mix, sample_rate)


def mix_scene_audio(
    scene_path: Path,
    output_path: Path,
    *,
    duration_sec: int | None = None,
    seed: int = 0,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
) -> Path:
    scene_config = load_scene_config(scene_path)
    target_duration = duration_sec or int(scene_config["video"]["target_duration_hours"] * 3600)
    audio = render_scene_audio(scene_config, target_duration, seed=seed, sample_rate=sample_rate)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(output_path, audio, sample_rate, subtype="PCM_24")
    return output_path


def _write_demo_tone(path: Path, frequency: float, seconds: float, sample_rate: int) -> None:
    t = np.linspace(0.0, seconds, int(sample_rate * seconds), endpoint=False, dtype=np.float32)
    mono = 0.2 * np.sin(2.0 * np.pi * frequency * t)
    stereo = np.column_stack([mono, mono]).astype(np.float32)
    sf.write(path, stereo, sample_rate, subtype="PCM_24")


def create_demo_scene(temp_root: Path) -> Path:
    audio_dir = temp_root / "audio_sources"
    audio_dir.mkdir(parents=True, exist_ok=True)
    _write_demo_tone(audio_dir / "room.wav", 90.0, 2.0, DEFAULT_SAMPLE_RATE)
    _write_demo_tone(audio_dir / "fan.wav", 180.0, 1.5, DEFAULT_SAMPLE_RATE)
    _write_demo_tone(audio_dir / "cicada_a.wav", 720.0, 0.25, DEFAULT_SAMPLE_RATE)
    _write_demo_tone(audio_dir / "cicada_b.wav", 810.0, 0.2, DEFAULT_SAMPLE_RATE)
    _write_demo_tone(audio_dir / "bird.wav", 1200.0, 0.15, DEFAULT_SAMPLE_RATE)
    _write_demo_tone(audio_dir / "glass.wav", 980.0, 0.1, DEFAULT_SAMPLE_RATE)

    scene = {
        "scene": {"id": "demo", "slug": "demo-scene"},
        "visual": {
            "prompt": "demo prompt",
            "negative_prompt": "demo negative",
            "style": "ghibli",
            "resolution": [3840, 2160],
            "loop_duration_sec": 6,
            "motion_prompt": "demo motion",
        },
        "audio": {
            "layers": {
                "room_tone": {"source": "./audio_sources/room.wav", "volume": 0.2},
                "continuous": {"source": "./audio_sources/fan.wav", "volume": 0.32},
                "periodic": {
                    "sources": ["./audio_sources/cicada_a.wav", "./audio_sources/cicada_b.wav"],
                    "interval": [1, 2],
                    "volume": 0.5,
                },
                "rare_events": {
                    "sources": ["./audio_sources/bird.wav", "./audio_sources/glass.wav"],
                    "interval": [3, 4],
                    "volume": 0.42,
                },
            }
        },
        "video": {"target_duration_hours": 1, "film_grain": 15, "vignette": True, "time_lapse": False},
        "metadata": {
            "title": {"ko": "데모", "en": "Demo"},
            "description": {"ko": "데모 설명", "en": "Demo description"},
            "tags": ["demo"],
            "storyline": {"ko": "데모 이야기", "en": "Demo story"},
            "culture": "KR",
            "season": "summer",
        },
    }
    scene_path = temp_root / "scene.yaml"
    scene_path.write_text(yaml.safe_dump(scene, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return scene_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Mix ambient audio from a Library of Longing scene config.")
    parser.add_argument("--scene", type=Path, help="Path to a scene YAML file.")
    parser.add_argument("--output", type=Path, required=True, help="Output WAV path.")
    parser.add_argument("--duration-sec", type=int, default=None, help="Override target duration in seconds.")
    parser.add_argument("--seed", type=int, default=0, help="Random seed for event placement.")
    parser.add_argument("--demo", action="store_true", help="Generate a self-contained demo scene and audio inputs.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.demo:
        with tempfile.TemporaryDirectory(prefix="library-of-longing-demo-") as temp_dir:
            scene_path = create_demo_scene(Path(temp_dir))
            result = mix_scene_audio(scene_path, args.output, duration_sec=args.duration_sec or 12, seed=args.seed)
            print(result)
        return

    if args.scene is None:
        raise SystemExit("--scene is required unless --demo is used.")

    result = mix_scene_audio(args.scene, args.output, duration_sec=args.duration_sec, seed=args.seed)
    print(result)


if __name__ == "__main__":
    main()
