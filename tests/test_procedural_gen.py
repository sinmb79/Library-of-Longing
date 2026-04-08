from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

from scripts.audio_sourcing.procedural_gen import (
    DEFAULT_SAMPLE_RATE,
    fan,
    hum,
    room_tone,
    wind,
    write_procedural_wav,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _loop_edge_difference(audio: np.ndarray, sample_rate: int) -> float:
    edge_samples = max(1, sample_rate // 20)
    return float(np.mean(np.abs(audio[:edge_samples] - audio[-edge_samples:])))


def _dominant_frequency(audio: np.ndarray, sample_rate: int) -> float:
    mono = audio.mean(axis=1)
    spectrum = np.fft.rfft(mono)
    frequencies = np.fft.rfftfreq(len(mono), d=1.0 / sample_rate)
    magnitudes = np.abs(spectrum)
    magnitudes[0] = 0.0
    return float(frequencies[int(np.argmax(magnitudes))])


def test_generators_return_stereo_loopable_audio() -> None:
    generators = [
        room_tone(duration=3.0, seed=1),
        fan(duration=3.0, seed=2),
        wind(duration=3.0, seed=3),
        hum(duration=3.0, seed=4),
    ]

    for audio in generators:
        assert audio.shape == (3 * DEFAULT_SAMPLE_RATE, 2)
        assert audio.dtype == np.float32
        assert np.max(np.abs(audio)) <= 0.995
        assert _loop_edge_difference(audio, DEFAULT_SAMPLE_RATE) < 0.12


def test_hum_tracks_requested_base_frequency() -> None:
    audio = hum(duration=4.0, base_freq=60.0, amplitude=0.18, seed=7)

    dominant_frequency = _dominant_frequency(audio, DEFAULT_SAMPLE_RATE)

    assert 58.0 <= dominant_frequency <= 62.0


def test_write_procedural_wav_writes_48khz_stereo(tmp_path: Path) -> None:
    output_path = write_procedural_wav("fan", tmp_path / "fan_loop.wav", duration=2.5, seed=9)

    data, sample_rate = sf.read(output_path)

    assert output_path.exists()
    assert output_path.suffix == ".wav"
    assert sample_rate == DEFAULT_SAMPLE_RATE
    assert data.ndim == 2
    assert data.shape[1] == 2
    assert abs(len(data) - int(2.5 * DEFAULT_SAMPLE_RATE)) <= 8


def test_cli_generates_requested_sound(tmp_path: Path) -> None:
    output_path = tmp_path / "hum_loop.wav"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/audio_sourcing/procedural_gen.py",
            "--type",
            "hum",
            "--duration",
            "2",
            "--output",
            str(output_path),
            "--seed",
            "11",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert output_path.exists()
    assert str(output_path) in result.stdout
