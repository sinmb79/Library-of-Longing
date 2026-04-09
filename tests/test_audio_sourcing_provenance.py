from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

from scripts.audio_sourcing.library import populate_scene_audio_sources


def _build_scene(scene_path: Path) -> Path:
    scene = {
        "scene": {"id": "001", "slug": "provenance-test"},
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
                "room_tone": {
                    "source": "./audio_sources/grandma_porch/room_tone.wav",
                    "volume": 0.2,
                    "sourcing": {"tier": "procedural", "type": "room_tone", "params": {"duration": 5}},
                },
                "continuous": {
                    "source": "./audio_sources/grandma_porch/fan_loop.wav",
                    "volume": 0.3,
                    "sourcing": {"tier": "procedural", "type": "fan", "params": {"duration": 5}},
                },
                "periodic": {
                    "sources": [
                        "./audio_sources/grandma_porch/cicada_near.mp3",
                        "./audio_sources/grandma_porch/cicada_far.mp3",
                    ],
                    "interval": [20, 30],
                    "volume": 0.5,
                    "sourcing": {
                        "tier": "freesound_cc0",
                        "queries": ["summer cicada chorus", "distant cicada chorus"],
                        "min_duration": 10,
                        "max_duration": 60,
                    },
                },
                "rare_events": {
                    "sources": [
                        "./audio_sources/grandma_porch/sparrow.mp3",
                        "./audio_sources/grandma_porch/ice_glass.wav",
                    ],
                    "interval": [120, 240],
                    "volume": 0.4,
                    "sourcing": {
                        "tier": "stable_audio",
                        "prompt": "isolated detail",
                    },
                },
            }
        },
        "video": {"target_duration_hours": 1, "film_grain": 15, "vignette": True, "time_lapse": False},
        "metadata": {
            "title": {"ko": "테스트", "en": "Test"},
            "description": {"ko": "설명", "en": "Description"},
            "tags": ["test"],
            "storyline": {"ko": "이야기", "en": "Story"},
            "culture": "KR",
            "season": "summer",
        },
    }
    scene_path.write_text(yaml.safe_dump(scene, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return scene_path


def _write_valid_wav(path: Path, seconds: float = 0.25, sample_rate: int = 48_000) -> Path:
    t = np.linspace(0.0, seconds, int(sample_rate * seconds), endpoint=False, dtype=np.float32)
    mono = 0.1 * np.sin(2.0 * np.pi * 220.0 * t)
    stereo = np.column_stack([mono, mono]).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, stereo, sample_rate, subtype="PCM_24")
    return path


def _write_sidecar(path: Path, payload: dict) -> Path:
    sidecar = path.with_suffix(".json")
    sidecar.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return sidecar


def _write_generated_audio(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".mp3":
        path.write_bytes(b"generated-mp3")
        return path
    return _write_valid_wav(path)


def test_local_existing_requires_sidecar(monkeypatch, tmp_path: Path) -> None:
    scene_path = _build_scene(tmp_path / "scene.yaml")
    existing = tmp_path / "audio_sources" / "grandma_porch" / "room_tone.wav"
    _write_valid_wav(existing)

    called: list[str] = []

    def _write_proc(sound_type: str, output_path: Path, **kwargs):
        called.append(sound_type)
        return _write_valid_wav(output_path)

    monkeypatch.setattr("scripts.audio_sourcing.library.write_procedural_wav", _write_proc)
    monkeypatch.setattr("scripts.audio_sourcing.library.search_cc0", lambda query, **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.list_catalog", lambda **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.search_archive", lambda query, **kwargs: [])
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.generate_sfx",
        lambda prompt, duration, seed, output_path, **kwargs: _write_generated_audio(output_path),
    )

    manifest_path = populate_scene_audio_sources(scene_path, manifest_path=tmp_path / "audio_sources" / "MANIFEST.json", seed=5)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["sources"]["audio_sources/grandma_porch/room_tone.wav"]["tier"] == "procedural"
    assert called == ["room_tone", "fan"]


def test_local_existing_promotes_with_valid_sidecar(monkeypatch, tmp_path: Path) -> None:
    scene_path = _build_scene(tmp_path / "scene.yaml")
    existing = tmp_path / "audio_sources" / "grandma_porch" / "room_tone.wav"
    _write_valid_wav(existing)
    _write_sidecar(
        existing,
        {
            "provider": "procedural",
            "generator": "room_tone",
            "license": "Procedural",
            "origin_url": "",
            "author": "",
        },
    )

    called: list[str] = []

    def _write_proc(sound_type: str, output_path: Path, **kwargs):
        called.append(sound_type)
        return _write_valid_wav(output_path)

    monkeypatch.setattr("scripts.audio_sourcing.library.write_procedural_wav", _write_proc)
    monkeypatch.setattr("scripts.audio_sourcing.library.search_cc0", lambda query, **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.list_catalog", lambda **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.search_archive", lambda query, **kwargs: [])
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.generate_sfx",
        lambda prompt, duration, seed, output_path, **kwargs: _write_generated_audio(output_path),
    )

    manifest_path = populate_scene_audio_sources(scene_path, manifest_path=tmp_path / "audio_sources" / "MANIFEST.json", seed=7)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest["sources"]["audio_sources/grandma_porch/room_tone.wav"]

    assert entry["tier"] == "local_existing"
    assert entry["license"] == "Procedural"
    assert entry["generator"] == "room_tone"
    assert called == ["fan"]


def test_corrupt_sidecar_triggers_reacquisition(monkeypatch, tmp_path: Path) -> None:
    scene_path = _build_scene(tmp_path / "scene.yaml")
    existing = tmp_path / "audio_sources" / "grandma_porch" / "room_tone.wav"
    _write_valid_wav(existing)
    existing.with_suffix(".json").write_text("{not-json", encoding="utf-8")

    called: list[str] = []

    def _write_proc(sound_type: str, output_path: Path, **kwargs):
        called.append(sound_type)
        return _write_valid_wav(output_path)

    monkeypatch.setattr("scripts.audio_sourcing.library.write_procedural_wav", _write_proc)
    monkeypatch.setattr("scripts.audio_sourcing.library.search_cc0", lambda query, **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.list_catalog", lambda **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.search_archive", lambda query, **kwargs: [])
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.generate_sfx",
        lambda prompt, duration, seed, output_path, **kwargs: _write_generated_audio(output_path),
    )

    manifest_path = populate_scene_audio_sources(scene_path, manifest_path=tmp_path / "audio_sources" / "MANIFEST.json", seed=9)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["sources"]["audio_sources/grandma_porch/room_tone.wav"]["tier"] == "procedural"
    assert called == ["room_tone", "fan"]


def test_sidecar_missing_license_field_triggers_reacquisition(monkeypatch, tmp_path: Path) -> None:
    scene_path = _build_scene(tmp_path / "scene.yaml")
    existing = tmp_path / "audio_sources" / "grandma_porch" / "room_tone.wav"
    _write_valid_wav(existing)
    _write_sidecar(existing, {"provider": "procedural", "generator": "room_tone"})

    called: list[str] = []

    def _write_proc(sound_type: str, output_path: Path, **kwargs):
        called.append(sound_type)
        return _write_valid_wav(output_path)

    monkeypatch.setattr("scripts.audio_sourcing.library.write_procedural_wav", _write_proc)
    monkeypatch.setattr("scripts.audio_sourcing.library.search_cc0", lambda query, **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.list_catalog", lambda **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.search_archive", lambda query, **kwargs: [])
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.generate_sfx",
        lambda prompt, duration, seed, output_path, **kwargs: _write_generated_audio(output_path),
    )

    manifest_path = populate_scene_audio_sources(scene_path, manifest_path=tmp_path / "audio_sources" / "MANIFEST.json", seed=11)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["sources"]["audio_sources/grandma_porch/room_tone.wav"]["tier"] == "procedural"
    assert called == ["room_tone", "fan"]


def test_legacy_stub_file_gets_rejected(monkeypatch, tmp_path: Path) -> None:
    scene_path = _build_scene(tmp_path / "scene.yaml")
    existing = tmp_path / "audio_sources" / "grandma_porch" / "room_tone.wav"
    existing.parent.mkdir(parents=True, exist_ok=True)
    existing.write_bytes(b"bad")

    called: list[str] = []

    def _write_proc(sound_type: str, output_path: Path, **kwargs):
        called.append(sound_type)
        return _write_valid_wav(output_path)

    monkeypatch.setattr("scripts.audio_sourcing.library.write_procedural_wav", _write_proc)
    monkeypatch.setattr("scripts.audio_sourcing.library.search_cc0", lambda query, **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.list_catalog", lambda **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.search_archive", lambda query, **kwargs: [])
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.generate_sfx",
        lambda prompt, duration, seed, output_path, **kwargs: _write_generated_audio(output_path),
    )

    manifest_path = populate_scene_audio_sources(scene_path, manifest_path=tmp_path / "audio_sources" / "MANIFEST.json", seed=13)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["sources"]["audio_sources/grandma_porch/room_tone.wav"]["tier"] == "procedural"
    assert called == ["room_tone", "fan"]


def test_manifest_records_real_provenance_not_placeholder(monkeypatch, tmp_path: Path) -> None:
    scene_path = _build_scene(tmp_path / "scene.yaml")

    monkeypatch.setattr(
        "scripts.audio_sourcing.library.write_procedural_wav",
        lambda sound_type, output_path, **kwargs: _write_valid_wav(output_path),
    )
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.search_cc0",
        lambda query, **kwargs: [
            {
                "sound_id": 824924,
                "name": "Cicadas W breeze",
                "author": "Colin.LeBlanc.Sound",
                "license": "Creative Commons 0",
                "url": "https://freesound.org/s/824924/",
                "duration": 20.0,
            }
        ],
    )
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.download_sound",
        lambda sound_id, output_path, **kwargs: output_path.parent.mkdir(parents=True, exist_ok=True) or output_path.write_bytes(b"freesound-bytes") or output_path,
    )
    monkeypatch.setattr("scripts.audio_sourcing.library.list_catalog", lambda **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.search_archive", lambda query, **kwargs: [])
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.generate_sfx",
        lambda prompt, duration, seed, output_path, **kwargs: _write_generated_audio(output_path),
    )

    manifest_path = populate_scene_audio_sources(scene_path, manifest_path=tmp_path / "audio_sources" / "MANIFEST.json", seed=17, force=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entry = manifest["sources"]["audio_sources/grandma_porch/cicada_near.mp3"]

    assert entry["tier"] == "freesound_cc0"
    assert entry["license"] == "Creative Commons 0"
    assert entry["origin_url"] == "https://freesound.org/s/824924/"
    assert entry["author"] == "Colin.LeBlanc.Sound"
    assert entry["license"] != "Local File"
