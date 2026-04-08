from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf
import yaml

from scripts.audio_sourcing.library import populate_scene_audio_sources


def _build_scene(scene_path: Path) -> Path:
    scene = {
        "scene": {"id": "001", "slug": "library-test"},
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
                "room_tone": {"source": "./audio_sources/grandma_porch/room_tone.wav", "volume": 0.2},
                "continuous": {"source": "./audio_sources/grandma_porch/fan_loop.wav", "volume": 0.3},
                "periodic": {
                    "sources": [
                        "./audio_sources/grandma_porch/cicada_near.wav",
                        "./audio_sources/grandma_porch/cicada_far.wav",
                    ],
                    "interval": [20, 30],
                    "volume": 0.5,
                },
                "rare_events": {
                    "sources": [
                        "./audio_sources/grandma_porch/sparrow.wav",
                        "./audio_sources/grandma_porch/ice_glass.wav",
                    ],
                    "interval": [120, 240],
                    "volume": 0.4,
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


def _write_bytes(path: Path, payload: bytes = b"audio") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def _write_valid_wav(path: Path, seconds: float = 0.25, sample_rate: int = 48_000) -> Path:
    t = np.linspace(0.0, seconds, int(sample_rate * seconds), endpoint=False, dtype=np.float32)
    mono = 0.1 * np.sin(2.0 * np.pi * 220.0 * t, dtype=np.float32)
    stereo = np.column_stack([mono, mono]).astype(np.float32)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, stereo, sample_rate, subtype="PCM_24")
    return path


def test_populate_scene_audio_sources_uses_all_acquisition_tiers(monkeypatch, tmp_path: Path) -> None:
    scene_path = _build_scene(tmp_path / "scene.yaml")
    manifest_path = tmp_path / "audio_sources" / "MANIFEST.json"

    monkeypatch.setattr(
        "scripts.audio_sourcing.library.write_procedural_wav",
        lambda sound_type, output_path, **kwargs: _write_bytes(output_path, payload=f"proc:{sound_type}".encode()),
    )
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.search_cc0",
        lambda query, **kwargs: (
            [
                {
                    "sound_id": 824924,
                    "name": "Cicadas W breeze",
                    "author": "Colin.LeBlanc.Sound",
                    "license": "Creative Commons 0",
                    "url": "https://freesound.org/s/824924/",
                    "duration": 20.0,
                }
            ]
            if "near" in query
            else []
        ),
    )
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.download_sound",
        lambda sound_id, output_path, **kwargs: _write_bytes(output_path, payload=b"freesound"),
    )
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.list_catalog",
        lambda **kwargs: [
            {
                "title": "Sparrow Song",
                "category": "birds",
                "page_url": "https://www.nps.gov/subjects/sound/sparrow.htm",
                "license": "US Public Domain",
            }
        ],
    )
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.download_nps",
        lambda entry, output_dir, *, output_filename=None, **kwargs: _write_bytes(output_dir / output_filename, payload=b"nps"),
    )
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.search_archive",
        lambda query, **kwargs: (
            [{"identifier": "archive-cicada", "title": "Archive Cicada", "creator": "Archivist"}]
            if "cicada" in query
            else []
        ),
    )
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.download_archive_audio_files",
        lambda item_id, output_dir, **kwargs: [_write_bytes(output_dir / "cicada_far.wav", payload=b"archive")],
    )
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.generate_sfx",
        lambda prompt, duration, seed, output_path, **kwargs: _write_bytes(output_path, payload=b"stable"),
    )

    written_manifest = populate_scene_audio_sources(scene_path, manifest_path=manifest_path, seed=11)

    manifest = json.loads(written_manifest.read_text(encoding="utf-8"))
    sources = manifest["sources"]

    assert written_manifest == manifest_path
    assert sources["audio_sources/grandma_porch/room_tone.wav"]["tier"] == "procedural"
    assert sources["audio_sources/grandma_porch/fan_loop.wav"]["tier"] == "procedural"
    assert sources["audio_sources/grandma_porch/cicada_near.wav"]["tier"] == "freesound_cc0"
    assert sources["audio_sources/grandma_porch/cicada_far.wav"]["tier"] == "archive_pd"
    assert sources["audio_sources/grandma_porch/sparrow.wav"]["tier"] == "nps_pd"
    assert sources["audio_sources/grandma_porch/ice_glass.wav"]["tier"] == "stable_audio"

def test_populate_scene_audio_sources_skips_existing_files(monkeypatch, tmp_path: Path) -> None:
    scene_path = _build_scene(tmp_path / "scene.yaml")
    existing = tmp_path / "audio_sources" / "grandma_porch" / "room_tone.wav"
    _write_valid_wav(existing)

    called: list[str] = []

    def _write_proc(sound_type: str, output_path: Path, **kwargs):
        called.append(sound_type)
        return _write_bytes(output_path, payload=b"generated")

    monkeypatch.setattr("scripts.audio_sourcing.library.write_procedural_wav", _write_proc)
    monkeypatch.setattr("scripts.audio_sourcing.library.search_cc0", lambda query, **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.list_catalog", lambda **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.search_archive", lambda query, **kwargs: [])
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.generate_sfx",
        lambda prompt, duration, seed, output_path, **kwargs: _write_bytes(output_path, payload=b"stable"),
    )

    manifest_path = populate_scene_audio_sources(scene_path, manifest_path=tmp_path / "audio_sources" / "MANIFEST.json", seed=5)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["sources"]["audio_sources/grandma_porch/room_tone.wav"]["tier"] == "local_existing"
    assert "room_tone" not in called


def test_populate_scene_audio_sources_replaces_invalid_placeholder_files(monkeypatch, tmp_path: Path) -> None:
    scene_path = _build_scene(tmp_path / "scene.yaml")
    placeholder = tmp_path / "audio_sources" / "grandma_porch" / "room_tone.wav"
    _write_bytes(placeholder, payload=b"bad")

    called: list[str] = []

    def _write_proc(sound_type: str, output_path: Path, **kwargs):
        called.append(sound_type)
        return _write_bytes(output_path, payload=b"real-room")

    monkeypatch.setattr("scripts.audio_sourcing.library.write_procedural_wav", _write_proc)
    monkeypatch.setattr("scripts.audio_sourcing.library.search_cc0", lambda query, **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.list_catalog", lambda **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.search_archive", lambda query, **kwargs: [])
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.generate_sfx",
        lambda prompt, duration, seed, output_path, **kwargs: _write_bytes(output_path, payload=b"stable"),
    )

    manifest_path = populate_scene_audio_sources(scene_path, manifest_path=tmp_path / "audio_sources" / "MANIFEST.json", seed=6)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest["sources"]["audio_sources/grandma_porch/room_tone.wav"]["tier"] == "procedural"
    assert "room_tone" in called


def test_populate_scene_audio_sources_falls_back_when_archive_item_is_rejected(monkeypatch, tmp_path: Path) -> None:
    scene_path = _build_scene(tmp_path / "scene.yaml")
    manifest_path = tmp_path / "audio_sources" / "MANIFEST.json"

    monkeypatch.setattr(
        "scripts.audio_sourcing.library.write_procedural_wav",
        lambda sound_type, output_path, **kwargs: _write_bytes(output_path, payload=f"proc:{sound_type}".encode()),
    )
    monkeypatch.setattr("scripts.audio_sourcing.library.search_cc0", lambda query, **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.list_catalog", lambda **kwargs: [])
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.search_archive",
        lambda query, **kwargs: [{"identifier": "restricted-item", "title": "Restricted", "creator": "Archivist"}],
    )
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.download_archive_audio_files",
        lambda item_id, output_dir, **kwargs: (_ for _ in ()).throw(ValueError("not an open license")),
    )
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.generate_sfx",
        lambda prompt, duration, seed, output_path, **kwargs: _write_bytes(output_path, payload=b"stable"),
    )

    written_manifest = populate_scene_audio_sources(scene_path, manifest_path=manifest_path, seed=3)
    manifest = json.loads(written_manifest.read_text(encoding="utf-8"))

    assert manifest["sources"]["audio_sources/grandma_porch/cicada_near.wav"]["tier"] == "stable_audio"


def test_populate_scene_audio_sources_prefers_stable_for_specific_sfx(monkeypatch, tmp_path: Path) -> None:
    scene_path = _build_scene(tmp_path / "scene.yaml")
    manifest_path = tmp_path / "audio_sources" / "MANIFEST.json"

    monkeypatch.setattr(
        "scripts.audio_sourcing.library.write_procedural_wav",
        lambda sound_type, output_path, **kwargs: _write_bytes(output_path, payload=f"proc:{sound_type}".encode()),
    )
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.search_cc0",
        lambda query, **kwargs: [{"sound_id": 1, "name": "should-not-use", "author": "x", "license": "Creative Commons 0", "url": "https://freesound.org/s/1/", "duration": 3.0}],
    )
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.download_sound",
        lambda sound_id, output_path, **kwargs: _write_bytes(output_path, payload=b"freesound"),
    )
    monkeypatch.setattr("scripts.audio_sourcing.library.list_catalog", lambda **kwargs: [])
    monkeypatch.setattr("scripts.audio_sourcing.library.search_archive", lambda query, **kwargs: [])
    monkeypatch.setattr(
        "scripts.audio_sourcing.library.generate_sfx",
        lambda prompt, duration, seed, output_path, **kwargs: _write_bytes(output_path, payload=b"stable"),
    )

    written_manifest = populate_scene_audio_sources(scene_path, manifest_path=manifest_path, seed=9)
    manifest = json.loads(written_manifest.read_text(encoding="utf-8"))

    assert manifest["sources"]["audio_sources/grandma_porch/ice_glass.wav"]["tier"] == "stable_audio"
