from __future__ import annotations

from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
import yaml

from scripts.audio_mixer import mix_scene_audio


def _write_tone(path: Path, *, frequency: float, seconds: float, sample_rate: int = 48_000) -> None:
    t = np.linspace(0, seconds, int(sample_rate * seconds), endpoint=False)
    mono = 0.2 * np.sin(2 * np.pi * frequency * t, dtype=np.float64)
    stereo = np.column_stack([mono, mono]).astype(np.float32)
    sf.write(path, stereo, sample_rate, subtype="PCM_24")


def _build_scene(tmp_path: Path) -> Path:
    audio_dir = tmp_path / "audio_sources"
    audio_dir.mkdir()

    _write_tone(audio_dir / "room.wav", frequency=90.0, seconds=2.0)
    _write_tone(audio_dir / "fan.wav", frequency=180.0, seconds=1.5)
    _write_tone(audio_dir / "cicada_a.wav", frequency=720.0, seconds=0.25)
    _write_tone(audio_dir / "cicada_b.wav", frequency=810.0, seconds=0.2)
    _write_tone(audio_dir / "bird.wav", frequency=1200.0, seconds=0.15)
    _write_tone(audio_dir / "glass.wav", frequency=980.0, seconds=0.1)

    scene = {
        "scene": {"id": "test", "slug": "demo-scene"},
        "visual": {
            "prompt": "demo prompt",
            "negative_prompt": "demo negative",
            "style": "ghibli",
            "resolution": [3840, 2160],
            "loop_duration_sec": 8,
            "motion_prompt": "demo motion",
        },
        "audio": {
            "layers": {
                "room_tone": {"source": "./audio_sources/room.wav", "volume": 0.2},
                "continuous": {"source": "./audio_sources/fan.wav", "volume": 0.3},
                "periodic": {
                    "sources": ["./audio_sources/cicada_a.wav", "./audio_sources/cicada_b.wav"],
                    "interval": [1, 2],
                    "volume": 0.5,
                },
                "rare_events": {
                    "sources": ["./audio_sources/bird.wav", "./audio_sources/glass.wav"],
                    "interval": [3, 4],
                    "volume": 0.45,
                },
            }
        },
        "video": {"target_duration_hours": 10, "film_grain": 15, "vignette": True, "time_lapse": False},
        "metadata": {
            "title": {"ko": "테스트", "en": "Test"},
            "description": {"ko": "설명", "en": "Description"},
            "tags": ["test"],
            "storyline": {"ko": "이야기", "en": "Story"},
            "culture": "KR",
            "season": "summer",
        },
    }

    scene_path = tmp_path / "scene.yaml"
    scene_path.write_text(yaml.safe_dump(scene, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return scene_path


def test_mix_scene_audio_is_reproducible_and_stereo(tmp_path: Path) -> None:
    scene_path = _build_scene(tmp_path)
    out_a = tmp_path / "mix_a.wav"
    out_b = tmp_path / "mix_b.wav"
    out_c = tmp_path / "mix_c.wav"

    mix_scene_audio(scene_path, out_a, duration_sec=12, seed=7)
    mix_scene_audio(scene_path, out_b, duration_sec=12, seed=7)
    mix_scene_audio(scene_path, out_c, duration_sec=12, seed=9)

    assert out_a.read_bytes() == out_b.read_bytes()
    assert out_a.read_bytes() != out_c.read_bytes()

    data, sample_rate = sf.read(out_a)
    meter = pyln.Meter(sample_rate)
    loudness = meter.integrated_loudness(data)

    assert sample_rate == 48_000
    assert data.ndim == 2
    assert data.shape[1] == 2
    assert abs(len(data) - 12 * sample_rate) <= sample_rate * 0.05
    assert np.max(np.abs(data)) <= 0.995
    assert -14.8 <= loudness <= -13.2
    assert not np.allclose(data[:, 0], data[:, 1])

    edge_diff = np.mean(np.abs(data[: sample_rate // 10] - data[-sample_rate // 10 :]))
    assert edge_diff < 0.12
